"""Pooled shot-making model; shooter identity is descriptive only.

Fitted on observed shot events, including fouled misses. Applying it to a live
ballhandler is an approximate shooting scenario, not an identified action value.
"""

import csv
import json
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import SplineTransformer, StandardScaler

SHOT_FEATURES = ["shot_distance", "shot_defender", "shot_abs_y", "shot_clock"]
EPV_SHOT_FEATURES = [
    "shot_make_probability",
    "shot_field_goal_value",
    "shot_player_adjustment",
]
ARC_FT = 6.75 / 0.3048
CORNER_FT = 6.60 / 0.3048
PRIOR_PRECISION = 8.0


def shot_region(distance, three):
    return np.where(three, "three", np.where(np.asarray(distance) < 8, "rim", "two"))


def location_is_three(distance, abs_y):
    return (np.asarray(distance) > ARC_FT) | (np.asarray(abs_y) > CORNER_FT)


def load_shots(root):
    aliases = {
        int(r["player_id"]): int(r["canonical_player_id"])
        for r in csv.DictReader((root / "data/player_id_aliases.csv").open())
    }
    rows = []
    for path in sorted((root / "data/matches").glob("*/*_dynamic_events.json")):
        for s in json.loads(path.read_text())["shots"]:
            if any(
                s[k] is None
                for k in ["distance", "closestDefDist", "location", "shotClock"]
            ):
                continue
            rows.append(
                {
                    "gameId": s["gameId"],
                    "shotId": s["id"],
                    "shooter": aliases.get(s["shooterId"], s["shooterId"]),
                    "shot_distance": s["distance"],
                    "shot_defender": s["closestDefDist"],
                    "shot_abs_y": abs(s["location"][1]),
                    "shot_clock": s["shotClock"],
                    "three": s["three"],
                    "made": int(s["outcome"]),
                    "vendorQuality": s.get("shotQuality"),
                    "fouled": s["fouled"],
                }
            )
    shots = pd.DataFrame(rows)
    shots["region"] = shot_region(shots.shot_distance, shots.three)
    return shots


@dataclass
class ShotModel:
    pooled: object
    effects: dict
    counts: dict
    training_games: tuple

    @classmethod
    def fit(cls, shots):
        # Smooth low-dimensional geometry, strongly regularized. No outcomes,
        # blocked/contest labels, shotType or release duration enter as features.
        model = make_pipeline(
            SplineTransformer(n_knots=4, degree=2, extrapolation="constant"),
            StandardScaler(),
            LogisticRegression(C=0.15, max_iter=1000),
        )
        model.fit(shots[SHOT_FEATURES], shots.made)
        # Counts are descriptive evidence only; identity never changes quality.
        effects = {}
        counts = {
            (int(player), str(region)): len(group)
            for (player, region), group in shots.groupby(["shooter", "region"])
        }
        return cls(
            model, effects, counts, tuple(sorted(int(g) for g in shots.gameId.unique()))
        )

    def predict(self, states):
        pooled = np.clip(
            self.pooled.predict_proba(states[SHOT_FEATURES])[:, 1], 1e-5, 1 - 1e-5
        )
        keys = list(zip(states.shooter.astype(int), states.region))
        offsets = np.zeros(len(keys))
        counts = np.array([self.counts.get(key, 0) for key in keys])
        personal = pooled.copy()
        return pooled, personal, offsets, counts


def enrich_states(table, payloads):
    """Recover the already-inferred holder and location; no future action labels."""
    holders = []
    holder_x = []
    holder_y = []
    ys = []
    for row in table.itertuples():
        fr = payloads[row.gameId]["plays"][row.possessionId]["frames"][row.frameIndex]
        holder = next(p for p in fr["offense"] if p[0] == fr["geometry"]["handler"])
        holders.append(holder[0])
        holder_x.append(holder[1])
        holder_y.append(holder[2])
        ys.append(abs(holder[2]))
    out = table.copy()
    out["shooter"] = holders
    out["holder_x"] = holder_x
    out["holder_y"] = holder_y
    out.loc[
        out.history_available == 0,
        ["handler_speed", "handler_toward_rim", "defender_closing_speed"],
    ] = np.nan
    out["shot_distance"] = out.handler_rim_distance
    out["shot_defender"] = out.nearest_defender
    out["shot_abs_y"] = ys
    out["three"] = location_is_three(out.shot_distance, out.shot_abs_y)
    out["region"] = shot_region(out.shot_distance, out.three)
    return out


def attach_predictions(states, model):
    pooled, personal, offsets, counts = model.predict(states)
    supported = states.shot_distance.to_numpy() <= 32
    out = states.copy()
    out["shot_make_probability"] = np.where(supported, personal, np.nan)
    out["shot_field_goal_value"] = np.where(
        supported, personal * np.where(states.three, 3, 2), np.nan
    )
    out["shot_player_adjustment"] = offsets
    out["shot_pooled_probability"] = np.where(supported, pooled, np.nan)
    out["shot_training_attempts"] = counts
    return out
