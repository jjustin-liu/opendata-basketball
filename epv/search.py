"""Observed dribble-onset forecasts; these are NOT causal search-action values.

One strictly pre-dribble snapshot per touch. Future touch/event fields are labels
only. Every displayed estimate excludes the replay game, including player effects.
"""

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import log_loss, mean_squared_error
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from .features import EPV_GEOMETRY_FEATURES

ROOT = Path(__file__).resolve().parents[1]
FEATURES = list(EPV_GEOMETRY_FEATURES)
CLASSES = ["pullup", "rim", "other_shot", "pass", "turnover", "foul", "retain", "other"]
SHOTS = {"pullup", "rim", "other_shot"}


def branch(kind, event):
    if kind != "shot":
        return kind
    style = event.get("complexShotType")
    if style in {"stepback", "dribblePullUp", "postFadeaway", "shakeAndRaise"}:
        return "pullup"
    if style in {"layup", "dunk", "lob", "tip", "hook", "floater"}:
        return "rim"
    return "other_shot"


def next_event(touch, dribble_frame, events):
    # The attempted pass is its own branch even if it subsequently turns over;
    # turnovers BEFORE a pass/shot are the separate turnover branch.
    future = [
        (at, priority, kind, e)
        for at, priority, kind, e in events
        if dribble_frame <= at <= dribble_frame + 50
    ]
    if future:
        at, _, kind, event = min(future, key=lambda x: (x[0], x[1]))
        return branch(kind, event), event, (at - dribble_frame) / 25
    return (
        ("retain" if touch["endFrame"] >= dribble_frame + 50 else "other"),
        None,
        np.nan,
    )


def examples(root=ROOT):
    states = pd.read_pickle(root / "artifacts/states.pkl")
    aliases = {
        int(r["player_id"]): int(r["canonical_player_id"])
        for r in csv.DictReader(
            (root / "data/player_id_aliases.csv").read_text().splitlines()
        )
    }
    groups = {pid: g.sort_values("frame") for pid, g in states.groupby("possessionId")}
    rows, audit = [], Counter()
    types = Counter()
    for path in sorted((root / "data/matches").glob("*/*_dynamic_events.json")):
        data = json.loads(path.read_text())
        touches = {t["id"]: t for t in data["touches"]}
        first = {}
        for d in sorted(data["dribbles"], key=lambda d: d["frame"]):
            first.setdefault(d.get("touchId"), d)
        events = defaultdict(list)
        for key, kind, priority in [
            ("passes", "pass", 0),
            ("shots", "shot", 1),
            ("turnovers", "turnover", 2),
            ("fouls", "foul", 3),
        ]:
            for e in data[key]:
                events[e.get("touchId")].append(
                    (e.get("startFrame", e.get("frame")), priority, kind, e)
                )
        types.update(s.get("complexShotType") or "unknown" for s in data["shots"])
        for tid, dribble in first.items():
            audit["dribble_touches"] += 1
            touch = touches.get(tid)
            if touch is None or touch["possessionId"] not in groups:
                audit["no_touch_or_tracking"] += 1
                continue
            g = groups[touch["possessionId"]]
            before = g[
                (g.frame < dribble["frame"])
                & (g.frame >= dribble["frame"] - 5)
                & (g.frame >= touch["startFrame"])
            ]
            if before.empty:
                audit["no_strict_prior_state"] += 1
                continue
            r = before.iloc[-1]
            player = aliases.get(touch["playerId"], touch["playerId"])
            if r.shooter != player or r.handler_rim_distance > 32 or r.shot_clock < 2.2:
                audit["wrong_holder_or_outside_scope"] += 1
                continue
            outcome, event, delay = next_event(touch, dribble["frame"], events[tid])
            row = {k: r[k] for k in FEATURES}
            row.update(
                gameId=int(r.gameId),
                possessionId=r.possessionId,
                touchId=tid,
                frame=int(r.frame),
                actionFrame=dribble["frame"],
                player=int(player),
                points=float(r.points),
                outcome=outcome,
                releaseDistance=np.nan,
                releaseSeparation=np.nan,
                releaseSeconds=np.nan,
            )
            if outcome in SHOTS:
                row.update(
                    releaseDistance=event.get("distance"),
                    releaseSeparation=event.get("closestDefDist"),
                    releaseSeconds=delay + (dribble["frame"] - r.frame) / 25,
                )
            rows.append(row)
    table = pd.DataFrame(rows)
    audit["accepted"] = len(table)
    return (
        table,
        states,
        {
            "exclusions": dict(audit),
            "shotTypes": dict(types),
            "outcomes": table.outcome.value_counts().to_dict(),
        },
    )


def fit(table):
    weights = (
        1 / table.groupby("possessionId").possessionId.transform("size").to_numpy()
    )
    weights *= len(weights) / weights.sum()

    def pipe(model):
        return make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), model)

    classifier = pipe(LogisticRegression(C=0.1, max_iter=800))
    classifier.fit(
        table[FEATURES], table.outcome, logisticregression__sample_weight=weights
    )
    value = pipe(Ridge(alpha=100))
    value.fit(table[FEATURES], table.points, ridge__sample_weight=weights)
    releases = table[table.outcome.isin(SHOTS)].dropna(
        subset=["releaseDistance", "releaseSeparation", "releaseSeconds"]
    )
    release = pipe(Ridge(alpha=100))
    release.fit(
        releases[FEATURES],
        releases[["releaseDistance", "releaseSeparation", "releaseSeconds"]],
    )
    return classifier, value, release


def predict(models, rows):
    c, v, r = models
    probabilities = np.zeros((len(rows), len(CLASSES)))
    raw = c.predict_proba(rows[FEATURES])
    for i, label in enumerate(c[-1].classes_):
        probabilities[:, CLASSES.index(label)] = raw[:, i]
    return (
        probabilities,
        np.maximum(0, v.predict(rows[FEATURES])),
        np.maximum(0, r.predict(rows[FEATURES])),
    )


def effects(train, oof_prob, oof_value):
    result = {}
    for player, indexes in train.groupby("player").indices.items():
        g = train.iloc[indexes]
        n = len(g)
        games = g.gameId.nunique()
        # Counts refer to independent touch anchors, not repeated replay frames.
        use = n >= 20 and games >= 2
        truth = np.eye(len(CLASSES))[[CLASSES.index(v) for v in g.outcome]]
        weight = n / (n + 80) if use else 0
        result[int(player)] = {
            "n": n,
            "games": int(games),
            "weight": weight,
            "prob": weight * (truth - oof_prob[indexes]).mean(axis=0),
            "value": float(weight * (g.points.to_numpy() - oof_value[indexes]).mean()),
        }
    return result


def adjusted(prob, value, rows, personal):
    p = prob.copy()
    v = value.copy()
    for i, player in enumerate(rows.player):
        effect = personal.get(int(player))
        if effect:
            p[i] = np.maximum(0.0001, p[i] + effect["prob"])
            p[i] /= p[i].sum()
            v[i] = max(0, v[i] + effect["value"])
    return p, v


def metrics(rows, prob, value):
    labels = [CLASSES.index(o) for o in rows.outcome]
    weights = 1 / rows.groupby("possessionId").possessionId.transform("size").to_numpy()
    return {
        "logLoss": float(
            log_loss(
                labels, prob, labels=list(range(len(CLASSES))), sample_weight=weights
            )
        ),
        "pointsRmse": float(
            np.sqrt(mean_squared_error(rows.points, value, sample_weight=weights))
        ),
    }


def main():
    table, states, audit = examples()
    report = {
        "audit": audit,
        "features": FEATURES,
        "folds": [],
        "definition": "Forecast of observed first-dribble choices from a strictly prior snapshot. Next event within 2 seconds on the same touch; pass precedes any ensuing interception, shot precedes its foul. Points include all subsequent offensive possession scoring. Selection into dribbling is observational, not a causal comparison with shooting or passing. Release geometry is conditional on a shot occurring within the horizon. No named move availability is established.",
    }
    cache = {}
    gids = sorted(table.gameId.unique())

    def model(excluded):
        key = tuple(sorted(excluded))
        if key not in cache:
            cache[key] = fit(table[~table.gameId.isin(key)])
        return cache[key]

    manifest_path = ROOT / "viewer/data/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    for gid in gids:
        train = table[table.gameId != gid].reset_index(drop=True)
        test = table[table.gameId == gid].reset_index(drop=True)
        op = np.zeros((len(train), len(CLASSES)))
        ov = np.zeros(len(train))
        for inner in sorted(train.gameId.unique()):
            indices = np.flatnonzero(train.gameId.to_numpy() == inner)
            op[indices], ov[indices], _ = predict(
                model([gid, inner]), train.iloc[indices]
            )
        personal = effects(train, op, ov)
        m = model([gid])
        p, v, release = predict(m, test)
        ap, av = adjusted(p, v, test, personal)
        weights = (
            1 / train.groupby("possessionId").possessionId.transform("size").to_numpy()
        )
        basep = np.array(
            [weights[train.outcome.to_numpy() == c].sum() for c in CLASSES]
        )
        basep /= basep.sum()
        basev = np.average(train.points, weights=weights)
        # Error band calibrated solely from other-game predictions within training.
        radius = float(np.quantile(np.abs(train.points.to_numpy() - ov), 0.8))
        fold = {
            "gameId": int(gid),
            "touches": len(test),
            "trainingGames": [int(g) for g in sorted(train.gameId.unique())],
            "testTouchesWithPlayerEffect": sum(
                personal.get(int(p), {}).get("weight", 0) > 0 for p in test.player
            ),
            "constant": metrics(
                test, np.tile(basep, (len(test), 1)), np.full(len(test), basev)
            ),
            "context": metrics(test, p, v),
            "player": metrics(test, ap, av),
            "pooledErrorBandRadius": radius,
            "pooledErrorBandCoverage": float(
                np.mean(abs(test.points.to_numpy() - v) <= radius)
            ),
            "playersWithEffects": sum(e["weight"] > 0 for e in personal.values()),
        }
        mask = (
            test.outcome.isin(SHOTS)
            & test.releaseDistance.notna()
            & test.releaseSeparation.notna()
        )
        for i, col in enumerate(
            ["releaseDistance", "releaseSeparation", "releaseSeconds"]
        ):
            fold[col + "Mae"] = float(
                np.mean(abs(test.loc[mask, col].to_numpy() - release[mask, i]))
            )
            fold[col + "BaselineMae"] = float(
                np.mean(
                    abs(
                        test.loc[mask, col].to_numpy()
                        - train.loc[train.outcome.isin(SHOTS), col].mean()
                    )
                )
            )
        report["folds"].append(fold)
        game = next(g for g in manifest["games"] if g["match"]["id"] == gid)
        # Only publish states in the same geometric/time scope as training.
        candidates = states[
            (states.gameId == gid)
            & (states.handler_rim_distance <= 32)
            & (states.shot_clock >= 2.2)
        ].copy()
        candidates["player"] = candidates.shooter.astype(int)
        pp, vv, rr = predict(m, candidates)
        aa, bb = adjusted(pp, vv, candidates, personal)
        lookup = {}
        for i, row in enumerate(candidates.itertuples()):
            e = personal.get(row.player, {"n": 0, "games": 0, "weight": 0})
            # Broad empirical pooled outcome range; not precision of the mean.
            lookup[(row.possessionId, row.frame)] = {
                "events": {c: round(float(aa[i, j]), 5) for j, c in enumerate(CLASSES)},
                "points": round(float(bb[i]), 3),
                "pooledPoints": round(float(vv[i]), 3),
                "pooledOutcomeRange": [
                    round(max(0, float(vv[i]) - radius), 2),
                    round(float(vv[i]) + radius, 2),
                ],
                "release": {
                    c: round(float(rr[i, j]), 2)
                    for j, c in enumerate(["distance", "separation", "seconds"])
                },
                "playerTouches": e["n"],
                "playerGames": e["games"],
                "playerWeight": round(e["weight"], 3),
            }
        for entry in game["plays"]:
            path = ROOT / f"viewer/data/plays/{entry['id']}.json"
            play = json.loads(path.read_text())
            for f in play["frames"]:
                f.pop("search", None)
                if (play["id"], f["frame"]) in lookup:
                    f["search"] = lookup[(play["id"], f["frame"])]
            path.write_text(json.dumps(play, separators=(",", ":"), allow_nan=False))
        print("Search holdout", gid, fold, flush=True)
    report["summary"] = {
        modelname: {
            metric: float(np.mean([f[modelname][metric] for f in report["folds"]]))
            for metric in ["logLoss", "pointsRmse"]
        }
        for modelname in ["constant", "context", "player"]
    }
    report["summary"]["release"] = {
        k: float(np.mean([f[k] for f in report["folds"]]))
        for k in report["folds"][0]
        if k.endswith("Mae")
    }
    report["summary"]["pooledErrorBandCoverage"] = float(
        np.mean([f["pooledErrorBandCoverage"] for f in report["folds"]])
    )
    rng = np.random.default_rng(42)
    report["summary"]["gameBootstrap95"] = {}
    for metric in ["logLoss", "pointsRmse"]:
        delta = np.array(
            [f["context"][metric] - f["constant"][metric] for f in report["folds"]]
        )
        boot = delta[rng.integers(0, len(delta), (10000, len(delta)))].mean(axis=1)
        report["summary"]["gameBootstrap95"][metric] = np.quantile(
            boot, [0.025, 0.975]
        ).tolist()
    manifest["metrics"]["search"] = report
    manifest_path.write_text(
        json.dumps(manifest, separators=(",", ":"), allow_nan=False)
    )
    (ROOT / "artifacts/search_validation.json").write_text(
        json.dumps(report, indent=2, allow_nan=False)
    )
    (ROOT / "artifacts/metrics.json").write_text(
        json.dumps(manifest["metrics"], separators=(",", ":"), allow_nan=False)
    )
    table.to_pickle(ROOT / "artifacts/search_examples.pkl")
    print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    with threadpool_limits(limits=2):
        main()
