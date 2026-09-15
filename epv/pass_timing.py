"""Game-held-out release-to-catch duration from pre-release tracking only."""

import csv
import json
from bisect import bisect_left
from dataclasses import dataclass

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

from .passing import pass_features, velocities

TIMING_FEATURES = [
    "distance",
    "distance_squared",
    "receiver_along",
    "receiver_across",
    "receiver_speed",
    "passer_speed",
    "passer_pressure",
    "receiver_pressure",
    "lane_clearance",
    "history",
]


def timing_features(frame, previous, passer, receiver):
    basic = pass_features(frame, passer, receiver)
    if basic is None:
        return None
    off = {p[0]: np.array(p[1:3]) for p in frame["offense"]}
    direction = (off[receiver] - off[passer]) / basic["distance"]
    velocity = velocities(frame, previous)
    rv = velocity.get(receiver, np.zeros(2))
    pv = velocity.get(passer, np.zeros(2))
    return dict(
        zip(
            TIMING_FEATURES,
            [
                basic["distance"],
                basic["distance"] ** 2 / 100,
                float(rv @ direction),
                abs(float(rv[0] * direction[1] - rv[1] * direction[0])),
                float(np.linalg.norm(rv)),
                float(np.linalg.norm(pv)),
                basic["passer_pressure"],
                basic["receiver_pressure"],
                basic["lane_clearance"],
                float(receiver in velocity),
            ],
        )
    )


def load_timing(root):
    aliases = {
        int(r["player_id"]): int(r["canonical_player_id"])
        for r in csv.DictReader((root / "data/player_id_aliases.csv").open())
    }
    rows = []
    for path in sorted((root / "data/matches").glob("*/*_dynamic_events.json")):
        gid = int(path.parent.name)
        _, payload = joblib.load(root / f".cache/epv/{gid}.joblib")
        for event in json.loads(path.read_text())["passes"]:
            if (
                event["complete"] is not True
                or event["inbounds"]
                or event["receiverId"] == event["passerId"]
                or not event.get("endFrame")
            ):
                continue
            play = payload["plays"].get(event["possessionId"])
            if not play:
                continue
            frames = play["frames"]
            indices = [f["frame"] for f in frames]
            i = bisect_left(indices, event["startFrame"]) - 1
            if i < 0 or event["startFrame"] - indices[i] > 5:
                continue
            duration = (event["endFrame"] - event["startFrame"]) / 25
            if not 0.04 <= duration <= 3:
                continue
            passer = aliases.get(event["passerId"], event["passerId"])
            receiver = aliases.get(event["receiverId"], event["receiverId"])
            feats = timing_features(
                frames[i], frames[i - 1] if i else None, passer, receiver
            )
            if feats is not None:
                rows.append(
                    {
                        **feats,
                        "gameId": gid,
                        "passId": event["id"],
                        "duration": duration,
                    }
                )
    return pd.DataFrame(rows)


@dataclass
class TimingModel:
    mean: np.ndarray
    scale: np.ndarray
    coef: np.ndarray
    intercept: float
    training_games: tuple

    @classmethod
    def fit(cls, table):
        scaler = StandardScaler().fit(table[TIMING_FEATURES])
        model = Ridge(alpha=20).fit(
            scaler.transform(table[TIMING_FEATURES]), table.duration
        )
        return cls(
            scaler.mean_,
            scaler.scale_,
            model.coef_,
            float(model.intercept_),
            tuple(sorted(int(g) for g in table.gameId.unique())),
        )

    def predict(self, table):
        x = (
            table[TIMING_FEATURES].to_numpy()
            if isinstance(table, pd.DataFrame)
            else np.asarray(table)
        )
        return np.clip(
            ((x - self.mean) / self.scale) @ self.coef + self.intercept, 0.04, 3
        )

    def duration(self, features):
        return float(self.predict(np.array([features[k] for k in TIMING_FEATURES])))


def evaluate_timing(table):
    records = []
    for gid in sorted(table.gameId.unique()):
        train = table[table.gameId != gid]
        test = table[table.gameId == gid]
        model = TimingModel.fit(train)
        pred = model.predict(test)
        # Release-to-catch excludes the separate assumed release delay.
        distance = test.distance.to_numpy()
        total = 0.12 + distance / 40
        for _ in range(3):
            total = (
                0.12
                + np.sqrt(
                    np.maximum(
                        0,
                        distance**2
                        + 2 * distance * test.receiver_along.to_numpy() * total
                        + test.receiver_speed.to_numpy() ** 2 * total**2,
                    )
                )
                / 40
            )
        baseline = total - 0.12
        record = {
            "gameId": int(gid),
            "passes": len(test),
            "trainingGameIds": list(model.training_games),
        }
        for name, values in [("learned", pred), ("fixed40", baseline)]:
            error = values - test.duration.to_numpy()
            record[name] = {
                "mae": float(np.abs(error).mean()),
                "rmse": float(np.sqrt((error**2).mean())),
                "bias": float(error.mean()),
            }
        records.append(record)
    return {
        "passes": len(table),
        "perGame": records,
        "summary": {
            name: {
                metric: float(np.mean([r[name][metric] for r in records]))
                for metric in ["mae", "rmse", "bias"]
            }
            for name in ["learned", "fixed40"]
        },
        "target": "Release-to-catch seconds on completed non-inbound passes; strictly prior 5 Hz tracking, at most 0.2 seconds old. No post-release features.",
        "releaseDelay": 0.12,
        "limitations": "Completed-pass timing only; pass type and decision delay are unknown. 0.12 seconds to release remains an explicit assumption. Receiver and defender movement still use constant velocity.",
    }
