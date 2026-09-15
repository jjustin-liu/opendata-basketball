"""Shot annotations and conditional second-chance value on a live missed FG."""

import csv
import json
from bisect import bisect_right
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, mean_squared_error
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from .features import HOOP
from .shooting import ShotModel, load_shots

COLUMNS = [
    "shot_distance",
    "shot_abs_y",
    "off_nearest_rim",
    "def_nearest_rim",
    "off_within_8",
    "def_within_8",
    "off_within_15",
    "def_within_15",
    "off_near_defender",
]


def geometry(frame, shooter):
    if len(frame["offense"]) != 5 or len(frame["defense"]) != 5:
        return None
    player = next((p for p in frame["offense"] if p[0] == shooter), None)
    if player is None:
        return None
    off = np.array([p[1:3] for p in frame["offense"]])
    defense = np.array([p[1:3] for p in frame["defense"]])
    od = np.linalg.norm(off - HOOP, axis=1)
    dd = np.linalg.norm(defense - HOOP, axis=1)
    nearest = np.linalg.norm(off[:, None, :] - defense[None, :, :], axis=2).min(axis=1)
    return dict(
        zip(
            COLUMNS,
            [
                float(np.linalg.norm(np.array(player[1:3]) - HOOP)),
                abs(player[2]),
                float(od.min()),
                float(dd.min()),
                int((od < 8).sum()),
                int((dd < 8).sum()),
                int((od < 15).sum()),
                int((dd < 15).sum()),
                int(((od < 15) & (nearest < 3)).sum()),
            ],
        )
    )


def load_examples(root):
    aliases = {
        int(r["player_id"]): int(r["canonical_player_id"])
        for r in csv.DictReader((root / "data/player_id_aliases.csv").open())
    }
    contexts = {}
    rows = []
    for path in sorted((root / "data/matches").glob("*/*_dynamic_events.json")):
        gid = int(path.parent.name)
        events = json.loads(path.read_text())
        _, payload = joblib.load(root / f".cache/epv/{gid}.joblib")
        rebounds = {
            r["shotId"]: r for r in events["rebounds"] if r["fgReb"] and r["rebounded"]
        }
        for shot in events["shots"]:
            play = payload["plays"].get(shot["possessionId"])
            if not play:
                continue
            frames = play["frames"]
            i = bisect_right([f["frame"] for f in frames], shot["startFrame"]) - 1
            if i < 0 or shot["startFrame"] - frames[i]["frame"] > 5:
                continue
            shooter = aliases.get(shot["shooterId"], shot["shooterId"])
            features = geometry(frames[i], shooter)
            if features is None:
                continue
            contexts[shot["id"]] = {
                **features,
                "gameId": gid,
                "shotId": shot["id"],
                "possessionId": shot["possessionId"],
                "frame": shot["startFrame"],
                "endFrame": shot["endFrame"],
                "shooter": shooter,
            }
            reb = rebounds.get(shot["id"])
            if (
                shot["outcome"]
                or shot["fouled"]
                or reb is None
                or reb["frame"] <= shot["startFrame"]
            ):
                continue
            offensive = reb["teamId"] == shot["offTeamId"] and not reb["defensive"]
            points = 0
            if offensive:
                points = sum(
                    (3 if s["three"] else 2)
                    for s in events["shots"]
                    if s["possessionId"] == shot["possessionId"]
                    and s["offTeamId"] == shot["offTeamId"]
                    and s["endFrame"] > reb["frame"]
                    and s["outcome"]
                )
                points += sum(
                    int(ft["outcome"])
                    for ft in events["free_throws"]
                    if ft["possessionId"] == shot["possessionId"]
                    and ft["offTeamId"] == shot["offTeamId"]
                    and ft["frame"] > reb["frame"]
                )
            rows.append(
                {
                    **features,
                    "gameId": gid,
                    "shotId": shot["id"],
                    "offensiveRebound": int(offensive),
                    "points": points,
                }
            )
    return pd.DataFrame(rows), contexts


def fit(table):
    model = make_pipeline(StandardScaler(), LogisticRegression(C=0.1, max_iter=1000))
    model.fit(table[COLUMNS], table.offensiveRebound)
    value = float(table.loc[table.offensiveRebound == 1, "points"].mean())
    return model, value


def main():
    root = Path(__file__).resolve().parents[1]
    table, contexts = load_examples(root)
    shots = load_shots(root)
    manifest_path = root / "viewer/data/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    folds = []
    for game in manifest["games"]:
        gid = game["match"]["id"]
        train = table[table.gameId != gid]
        test = table[table.gameId == gid]
        model, continuation = fit(train)
        prob = model.predict_proba(test[COLUMNS])[:, 1]
        folds.append(
            {
                "gameId": gid,
                "misses": len(test),
                "offensiveRebounds": int(test.offensiveRebound.sum()),
                "brier": float(brier_score_loss(test.offensiveRebound, prob)),
                "baselineBrier": float(
                    brier_score_loss(
                        test.offensiveRebound,
                        np.full(len(test), train.offensiveRebound.mean()),
                    )
                ),
                "pointsRmse": float(
                    np.sqrt(mean_squared_error(test.points, prob * continuation))
                ),
                "baselinePointsRmse": float(
                    np.sqrt(
                        mean_squared_error(
                            test.points, np.full(len(test), train.points.mean())
                        )
                    )
                ),
                "pointsAfterOffensiveRebound": continuation,
            }
        )
        sm = ShotModel.fit(shots[shots.gameId != gid])
        ss = shots[shots.gameId == gid]
        _pooled, personal, _offsets, _counts = sm.predict(ss)
        quality = {
            row.shotId: {
                "makeProbability": round(float(p), 5),
                "fieldGoalValue": round(float(p * (3 if row.three else 2)), 4),
                "pointsIfMade": 3 if row.three else 2,
                "vendorQuality": round(float(row.vendorQuality), 2)
                if pd.notna(getattr(row, "vendorQuality", None))
                else None,
            }
            for row, p in zip(ss.itertuples(), personal)
        }
        for entry in game["plays"]:
            path = root / f"viewer/data/plays/{entry['id']}.json"
            play = json.loads(path.read_text())
            candidates = []
            for frame in play["frames"]:
                shot = frame.get("shot")
                if not shot:
                    continue
                # Restore previews exported with the retired fixed wind-up adjustment.
                shot.update(shot.pop("instantaneous", {}))
                shot.pop("windupSeconds", None)
                shot.pop("releaseDefenderFeet", None)
                features = geometry(frame, shot["shooter"])
                if features is not None:
                    candidates.append((shot, features))
            if candidates:
                probabilities = model.predict_proba(
                    pd.DataFrame([features for _, features in candidates])[COLUMNS]
                )[:, 1]
                for (shot, _), probability in zip(candidates, probabilities):
                    contribution = (
                        (1 - shot["makeProbability"]) * probability * continuation
                    )
                    shot["offensiveReboundProbability"] = round(float(probability), 5)
                    shot["secondChancePerMiss"] = round(
                        float(probability * continuation), 4
                    )
                    shot["secondChancePerShot"] = round(float(contribution), 4)
                    shot["shotPlusSecondChance"] = round(
                        float(shot["fieldGoalValue"] + contribution), 4
                    )
            for event in play["events"]:
                if event["type"] != "shot":
                    continue
                context = next(
                    (
                        c
                        for c in contexts.values()
                        if c["gameId"] == gid
                        and c["possessionId"] == play["id"]
                        and c["frame"] == event["frame"]
                        and c["shooter"] == event.get("player")
                    ),
                    None,
                )
                if context is None:
                    continue
                p = float(model.predict_proba(pd.DataFrame([context])[COLUMNS])[0, 1])
                q = quality.get(context["shotId"])
                event["shotForecast"] = {
                    "shotId": context["shotId"],
                    "endFrame": context["endFrame"],
                    "quality": q,
                    "offensiveReboundProbability": round(p, 5),
                    "secondChancePerMiss": round(p * continuation, 4),
                    "pointsAfterOffensiveRebound": round(continuation, 4),
                    "secondChancePerShot": round(
                        (1 - q["makeProbability"]) * p * continuation, 4
                    )
                    if q
                    else None,
                }
            path.write_text(json.dumps(play, separators=(",", ":"), allow_nan=False))
        print("Annotated shots", gid, flush=True)
    report = {
        "misses": len(table),
        "offensiveRebounds": int(table.offensiveRebound.sum()),
        "perGame": folds,
        "summary": {
            key: float(np.mean([f[key] for f in folds]))
            for key in ["brier", "baselineBrier", "pointsRmse", "baselinePointsRmse"]
        },
        "definition": "Expected future offensive points per live missed field goal with a resolved rebound = P(offensive rebound | release geometry, live miss) × training-game mean remaining points after an offensive rebound. Fouled shots and unresolved/dead-ball rebounds excluded from training. Locations of both teams affect rebound probability; conditional continuation value is pooled, not location-specific. No ball-bounce, box-out orientation, or post-release tracking inputs. Applying to a shot assumes a live miss; per-shot contribution also multiplies by miss probability. Not added to full EPV, which already includes continuation.",
    }
    manifest["metrics"]["secondChance"] = report
    manifest_path.write_text(
        json.dumps(manifest, separators=(",", ":"), allow_nan=False)
    )
    (root / "artifacts/metrics.json").write_text(
        json.dumps(manifest["metrics"], separators=(",", ":"), allow_nan=False)
    )
    bundle = joblib.load(root / "artifacts/models.joblib")
    bundle["secondChanceModel"], bundle["secondChanceContinuation"] = fit(table)
    bundle["secondChanceFeatures"] = COLUMNS
    joblib.dump(bundle, root / "artifacts/models.joblib")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    with threadpool_limits(limits=2):
        main()
