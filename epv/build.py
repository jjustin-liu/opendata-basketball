"""Build features, train leave-one-game-out models, export held-out play replays.

Run: .venv/bin/python -m epv.build
"""

from __future__ import annotations
import argparse
from bisect import bisect_right
from collections import defaultdict, Counter
import csv
import gzip
import json
from pathlib import Path
import time
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import (
    HistGradientBoostingRegressor,
    HistGradientBoostingClassifier,
)
from sklearn.metrics import mean_squared_error, brier_score_loss, log_loss
from threadpoolctl import threadpool_limits
from .passing import (
    load_passes,
    fit_pass_model,
    export_options,
    PASS_FEATURES,
    TIMING_DESCRIPTION,
)
from .pass_timing import load_timing, TimingModel, evaluate_timing
from .features import FEATURES, BASE_FEATURES, EPV_GEOMETRY_FEATURES, spatial_features
from .shooting import (
    ShotModel,
    load_shots,
    enrich_states,
    attach_predictions,
    EPV_SHOT_FEATURES,
    ARC_FT,
    CORNER_FT,
)

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache/epv"
OUT = ROOT / "viewer/data"
TARGETS = ["points", "turnover2", "turnover_rest"]
EXTRACTION_VERSION = 2


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, separators=(",", ":"), allow_nan=False))


def remaining_targets(frame, clock, rewards, turnovers):
    points = sum(value for at, value in rewards if at > frame)
    future = [gc for at, gc in turnovers if at > frame]
    return points, int(any(0 <= clock - gc <= 2 for gc in future)), int(bool(future))


def prepare_game(match):
    gid = match["id"]
    folder = ROOT / f"data/matches/{gid}"
    events = json.loads((folder / f"{gid}_dynamic_events.json").read_text())
    meta = json.loads((folder / f"{gid}_game_data.json").read_text())
    aliases = {
        int(r["player_id"]): int(r["canonical_player_id"])
        for r in csv.DictReader((ROOT / "data/player_id_aliases.csv").open())
    }
    canon = lambda pid: aliases.get(pid, pid)
    possessions = {p["id"]: p for p in events["possessions"]}
    chances = sorted(
        [c for c in events["chances"] if c["startFrame"] < c["endFrame"]],
        key=lambda c: c["startFrame"],
    )
    starts = [c["startFrame"] for c in chances]
    rewards = defaultdict(list)
    turns = defaultdict(list)
    annotations = defaultdict(list)
    flight = defaultdict(list)
    scores = Counter()
    audit = Counter()
    for s in events["shots"]:
        value = (3 if s["three"] else 2) * bool(s["outcome"])
        scores[s["offTeamId"]] += value
        p = possessions.get(s["possessionId"])
        if p and p["offTeamId"] == s["offTeamId"]:
            rewards[p["id"]].append((s["endFrame"], value))
            flight[p["id"]].append(
                (s["startFrame"], s["endFrame"] or s["startFrame"] + 50)
            )
        annotations[s["possessionId"]].append(
            {
                "frame": s["startFrame"],
                "type": "shot",
                "label": f"{'Made' if s['outcome'] else 'Missed'} {'3PT' if s['three'] else '2PT'}"
                + (" · foul" if s["fouled"] else ""),
                "player": canon(s["shooterId"]),
            }
        )
    for ft in events["free_throws"]:
        scores[ft["offTeamId"]] += bool(ft["outcome"])
        p = possessions.get(ft["possessionId"])
        if p and p["offTeamId"] == ft["offTeamId"]:
            rewards[p["id"]].append((ft["frame"], int(bool(ft["outcome"]))))
        elif ft["outcome"]:
            audit["opponent_free_throw_points_excluded"] += 1
        annotations[ft["possessionId"]].append(
            {
                "frame": ft["frame"],
                "type": "free_throw",
                "label": "FT made" if ft["outcome"] else "FT missed",
                "player": canon(ft["shooterId"]),
            }
        )
    for t in events["turnovers"]:
        p = possessions.get(t["possessionId"])
        if p and p["offTeamId"] == t["offTeamId"]:
            turns[p["id"]].append((t["frame"], t["gameClock"]))
        annotations[t["possessionId"]].append(
            {
                "frame": t["frame"],
                "type": "turnover",
                "label": "Turnover",
                "player": canon(t["turnedOverId"]),
            }
        )
    for f in events["fouls"]:
        # Offensive-foul labels are in the foul table; avoid counting duplicate TOs.
        if "off" in str(f["foulType"]).lower():
            p = possessions.get(f["possessionId"])
            if p and f["foulerTeamId"] == p["offTeamId"]:
                if not any(abs(at - f["frame"]) <= 25 for at, _ in turns[p["id"]]):
                    turns[p["id"]].append((f["frame"], f["gameClock"]))
                    audit["offensive_fouls_added"] += 1
                annotations[p["id"]].append(
                    {
                        "frame": f["frame"],
                        "type": "turnover",
                        "label": "Offensive foul",
                        "player": canon(f["foulerId"]),
                    }
                )
    for p in events["passes"]:
        flight[p["possessionId"]].append(
            (p["startFrame"], p["endFrame"] or p["startFrame"] + 25)
        )
        annotations[p["possessionId"]].append(
            {
                "frame": p["startFrame"],
                "type": "pass",
                "label": "Pass" if p["complete"] else "Incomplete pass",
                "player": canon(p["passerId"]),
            }
        )
    for r in events["rebounds"]:
        annotations[r["possessionId"]].append(
            {"frame": r["frame"], "type": "rebound", "label": "Rebound"}
        )
    for side in ["home", "away"]:
        assert scores[match[f"{side}_team"]["id"]] == match[f"{side}_score"], (
            f"Score mismatch {gid} {side}"
        )
    plays = {}
    rows = []
    previous = None
    previous_pid = None
    tracking = ROOT / f".cache/tracking/{gid}_tracking_data.jsonl.gz"
    if not tracking.exists():
        raise FileNotFoundError("Run python3 scripts/download_tracking.py first")
    with gzip.open(tracking, "rt") as stream:
        for line in stream:
            raw = json.loads(line)
            idx = raw["frameIdx"]
            if idx % 5:
                continue
            ci = bisect_right(starts, idx) - 1
            if ci < 0:
                continue
            chance = chances[ci]
            pid = chance["possessionId"]
            p = possessions.get(pid)
            if idx >= chance["endFrame"] or not p or raw["period"] != p["period"]:
                continue
            if (
                raw["gameClockStopped"]
                or not raw["ball"]
                or len(raw["homePlayers"]) != 5
                or len(raw["awayPlayers"]) != 5
            ):
                continue
            # Tracking is camera-oriented, unlike normalized event locations.
            sign = 1 if p["leftHoop"] else -1

            def player(a):
                return [
                    canon(a["playerId"]),
                    round(a["xyz"][0] * sign, 3),
                    round(a["xyz"][1] * sign, 3),
                    int(a["isDetected"]),
                    round(a["predError"], 3),
                    a["jersey"],
                ]

            home_off = p["offTeamId"] == meta["homeTeam"]["teamId"]
            b = raw["ball"]
            fr = {
                "frame": idx,
                "period": raw["period"],
                "gameClock": round(raw["gameClock"], 2),
                "shotClock": raw["shotClock"],
                "offense": [
                    player(a) for a in raw["homePlayers" if home_off else "awayPlayers"]
                ],
                "defense": [
                    player(a) for a in raw["awayPlayers" if home_off else "homePlayers"]
                ],
                "ball": [
                    round(b["xyz"][0] * sign, 3),
                    round(b["xyz"][1] * sign, 3),
                    round(b["xyz"][2], 3),
                    int(b["isDetected"]),
                    round(b["predError"], 3),
                ],
            }
            play = plays.setdefault(
                pid,
                {
                    "id": pid,
                    "gameId": gid,
                    "offTeamId": p["offTeamId"],
                    "period": p["period"],
                    "startClock": round(p["startGameClock"], 1),
                    "points": sum(v for _, v in rewards[pid]),
                    "turnover": bool(turns[pid]),
                    "events": sorted(annotations[pid], key=lambda a: a["frame"]),
                    "frames": [],
                },
            )
            calc = spatial_features(fr, previous if previous_pid == pid else None)
            supported = (
                bool(chance["usable"])
                and calc is not None
                and raw["shotClock"] is not None
            )
            in_flight = any(a <= idx <= b for a, b in flight[pid])
            fr["reason"] = (
                "Ball in flight"
                if in_flight
                else (
                    "Low-quality chance"
                    if not chance["usable"]
                    else "Ball control uncertain"
                )
            )
            if supported and not in_flight:
                features, geometry = calc
                fr["geometry"] = geometry
                fr["reason"] = None
                row = {
                    "gameId": gid,
                    "possessionId": pid,
                    "frame": idx,
                    "frameIndex": len(play["frames"]),
                    "train": idx % 10 == 0,
                    **features,
                }
                row.update(
                    dict(
                        zip(
                            TARGETS,
                            remaining_targets(
                                idx, raw["gameClock"], rewards[pid], turns[pid]
                            ),
                        )
                    )
                )
                rows.append(row)
                audit["supported_frames"] += 1
            else:
                audit[fr["reason"] or "unsupported"] += 1
            play["frames"].append(fr)
            previous = fr
            previous_pid = pid
    players = {
        str(canon(a["playerId"])): {
            "name": a["firstName"] + " " + a["lastName"],
            "jersey": a["jersey"],
            "teamId": team["teamId"],
        }
        for team in [meta["homeTeam"], meta["awayTeam"]]
        for a in team["players"]
    }
    audit["possessions_with_replay"] = len(plays)
    audit["score_reconciled_team_games"] = 2
    payload = {
        "extractionVersion": EXTRACTION_VERSION,
        "match": match,
        "players": players,
        "plays": plays,
        "audit": dict(audit),
    }
    CACHE.mkdir(parents=True, exist_ok=True)
    joblib.dump((pd.DataFrame(rows), payload), CACHE / f"{gid}.joblib", compress=3)
    print(f"{gid}: {len(plays)} plays, {len(rows)} prediction states", flush=True)
    return pd.DataFrame(rows), payload


def estimator(target):
    common = dict(
        max_iter=100,
        max_leaf_nodes=7,
        min_samples_leaf=100,
        learning_rate=0.06,
        l2_regularization=20,
        early_stopping=False,
        random_state=42,
    )
    return (
        HistGradientBoostingRegressor(**common)
        if target == "points"
        else HistGradientBoostingClassifier(**common)
    )


def prediction(model, x, target):
    return (
        np.maximum(0, model.predict(x))
        if target == "points"
        else model.predict_proba(x)[:, 1]
    )


def coherent_risks(short, remaining):
    """Least-squares projection onto 0 <= short <= remaining <= 1."""
    short = np.clip(np.asarray(short, dtype=float), 0, 1)
    remaining = np.clip(np.asarray(remaining, dtype=float), 0, 1)
    violation = short > remaining
    midpoint = (short + remaining) / 2
    return np.where(violation, midpoint, short), np.where(
        violation, midpoint, remaining
    )


def score(y, p, target, w):
    if target == "points":
        return {"rmse": float(np.sqrt(mean_squared_error(y, p, sample_weight=w)))}
    return {
        "brier": float(brier_score_loss(y, p, sample_weight=w)),
        "logLoss": float(
            log_loss(y, np.clip(p, 1e-6, 1 - 1e-6), sample_weight=w, labels=[0, 1])
        ),
        "predicted": float(np.average(p, weights=w)),
        "observed": float(np.average(y, weights=w)),
    }


def weights(df):
    w = 1 / df.groupby("possessionId")["frame"].transform("size").to_numpy()
    return w / w.mean()


def train_and_export(table, payloads):
    table = enrich_states(table, payloads)
    shots = load_shots(ROOT)
    passes, pass_audit = load_passes(ROOT)
    timings = load_timing(ROOT)
    timing_metrics = evaluate_timing(timings)
    pass_validation = []
    shot_metrics = []
    shot_cache = {}
    shot_oof = []

    def shot_model(excluded):
        key = tuple(sorted(excluded))
        if key not in shot_cache:
            shot_cache[key] = ShotModel.fit(shots[~shots.gameId.isin(key)])
        return shot_cache[key]

    OUT.mkdir(parents=True, exist_ok=True)
    (ROOT / "artifacts").mkdir(exist_ok=True)
    all_metrics = []
    predictions = {}
    model_names = ["constant", "clock_location", "geometry"]
    for gid in sorted(table.gameId.unique()):
        test = attach_predictions(table[table.gameId == gid], shot_model([gid]))
        parts = []
        for inner_gid in sorted(table.gameId.unique()):
            if inner_gid == gid:
                continue
            inner = table[(table.gameId == inner_gid) & table.train]
            # Each EPV training row's shooting inputs exclude BOTH its own game
            # and the outer test game. This prevents target-encoding leakage.
            model = shot_model([gid, inner_gid])
            assert (
                gid not in model.training_games
                and inner_gid not in model.training_games
            )
            parts.append(attach_predictions(inner, model))
        train = pd.concat(parts, ignore_index=True)
        shot_test = shots[shots.gameId == gid]
        pooled, personal, _, _ = shot_model([gid]).predict(shot_test)
        shot_constant = np.full(len(shot_test), shots[shots.gameId != gid].made.mean())
        shot_oof.append(
            (
                shot_test,
                {"constant": shot_constant, "pooled": pooled, "personalized": personal},
            )
        )
        for name, prob in [
            ("constant", shot_constant),
            ("pooled", pooled),
            ("personalized", personal),
        ]:
            shot_metrics.append(
                {
                    "gameId": int(gid),
                    "model": name,
                    "attempts": len(shot_test),
                    **score(shot_test.made, prob, "shot", np.ones(len(shot_test))),
                }
            )
        assert gid not in set(train.gameId)
        assert set(train.possessionId).isdisjoint(test.possessionId)
        tw = weights(train)
        vw = weights(test)
        result = {}
        print(f"Training held-out game {gid}…", flush=True)
        for target in TARGETS:
            for name in model_names + (["shooting"] if target == "points" else []):
                if name == "constant":
                    pred = np.full(len(test), np.average(train[target], weights=tw))
                else:
                    columns = (
                        EPV_GEOMETRY_FEATURES + EPV_SHOT_FEATURES
                        if name == "shooting"
                        else (
                            (EPV_GEOMETRY_FEATURES if target == "points" else FEATURES)
                            if name == "geometry"
                            else BASE_FEATURES
                        )
                    )
                    model = estimator(target)
                    model.fit(train[columns], train[target], sample_weight=tw)
                    pred = prediction(model, test[columns], target)
                result[target + "_" + name] = pred
                if target == "points" and name == "shooting":
                    projected_epv_model = model
        from epv.rop_risk import conservative_rop
        for name in model_names:
            result["turnover2_" + name], result["turnover_rest_" + name] = (
                coherent_risks(
                    result["turnover2_" + name], result["turnover_rest_" + name]
                )
            )
            if name == "geometry":
                result["turnover_rest_raw"] = result["turnover_rest_geometry"].copy()
                result["turnover_rest_geometry"] = conservative_rop(
                    result["turnover_rest_raw"],
                    np.average(train.turnover_rest, weights=tw),
                    result["turnover2_geometry"],
                )
            for target in TARGETS:
                all_metrics.append(
                    {
                        "gameId": int(gid),
                        "trainingGameIds": sorted(
                            int(g) for g in train.gameId.unique()
                        ),
                        "target": target,
                        "model": name,
                        **score(test[target], result[target + "_" + name], target, vw),
                    }
                )
        all_metrics.append(
            {
                "gameId": int(gid),
                "trainingGameIds": sorted(int(g) for g in train.gameId.unique()),
                "target": "points",
                "model": "shooting",
                **score(test.points, result["points_shooting"], "points", vw),
            }
        )
        pass_train = passes[passes.gameId != gid]
        pass_test = passes[passes.gameId == gid]
        pass_model = fit_pass_model(pass_train)
        pass_prob = pass_model.predict_proba(pass_test[PASS_FEATURES])[:, 1]
        pass_validation.append(
            {
                "gameId": int(gid),
                "passes": len(pass_test),
                "turnovers": int(pass_test.turnover.sum()),
                "brier": float(brier_score_loss(pass_test.turnover, pass_prob)),
                "baselineBrier": float(
                    brier_score_loss(
                        pass_test.turnover,
                        np.full(len(pass_test), pass_train.turnover.mean()),
                    )
                ),
                "logLoss": float(
                    log_loss(pass_test.turnover, pass_prob, labels=[0, 1])
                ),
            }
        )
        print(f"Projecting pass options for {gid}…", flush=True)
        export_options(
            payloads[int(gid)],
            pass_model,
            projected_epv_model,
            shot_model([gid]),
            TimingModel.fit(timings[timings.gameId != gid]),
        )
        predictions[int(gid)] = (test, result)
    metrics = {
        "passing": {
            "audit": pass_audit,
            "trainingPasses": len(passes),
            "timing": TIMING_DESCRIPTION,
            "flightTiming": timing_metrics,
            "trainingTurnovers": int(passes.turnover.sum()),
            "perGame": pass_validation,
            "reconstructionAccuracy": pass_audit["completed_correct"]
            / pass_audit["completed_reconstructed"],
            "features": PASS_FEATURES,
            "limitations": "Experimental selected-pass model: failed receivers inferred from early flight; ambiguous passes excluded from BOTH classes. Reconstruction accuracy on completions does not establish accuracy on interceptions. No causal counterfactual validation. Catch uses constant velocity, 40 ft/s ball and 0.12 s release, max 1.5 s; no defender reaction or pass-type model. Values use shooting-aware EPV; turnover branch gives zero offensive points.",
        },
        "method": "Leave one whole game out; fixed hyperparameters; equal possession weights; no season priors.",
        "targets": {
            "points": "Expected remaining offensive points, including free throws and offensive rebounds.",
            "turnover2": "Any recorded turnover or offensive foul in the next 2 game-clock seconds, before this possession ends.",
            "turnover_rest": "Any recorded turnover or offensive foul before this possession ends.",
        },
        "riskPostprocessing": "Independent horizons projected onto short-term <= remaining probability before evaluation and display.",
        "perGame": all_metrics,
        "summary": {},
        "calibration": {},
        "features": FEATURES,
        "shootingFeatures": EPV_SHOT_FEATURES,
        "epvFeatures": EPV_GEOMETRY_FEATURES + EPV_SHOT_FEATURES,
        "baselineFeatures": BASE_FEATURES,
        "trainingStates": int(table.train.sum()),
        "predictionStates": len(table),
        "possessions": int(table.possessionId.nunique()),
        "games": len(payloads),
    }
    # Equal game contribution, each possession equal within a game.
    for target in TARGETS:
        metrics["summary"][target] = {}
        ys = np.concatenate([t[target].to_numpy() for t, r in predictions.values()])
        ws = np.concatenate([weights(t) / len(t) for t, r in predictions.values()])
        for name in model_names + (["shooting"] if target == "points" else []):
            ps = np.concatenate(
                [r[target + "_" + name] for t, r in predictions.values()]
            )
            metrics["summary"][target][name] = score(ys, ps, target, ws)
            if target != "points" and name == "geometry":
                bins = np.array([0, 0.025, 0.05, 0.1, 0.15, 0.2, 0.3, 0.5, 1.000001])
                out = []
                for lo, hi in zip(bins[:-1], bins[1:]):
                    mask = (ps >= lo) & (ps < hi)
                    if mask.any():
                        out.append(
                            {
                                "lo": float(lo),
                                "hi": float(hi),
                                "n": int(mask.sum()),
                                "predicted": float(
                                    np.average(ps[mask], weights=ws[mask])
                                ),
                                "observed": float(
                                    np.average(ys[mask], weights=ws[mask])
                                ),
                            }
                        )
                metrics["calibration"][target] = out
    sy = np.concatenate([t.made.to_numpy() for t, r in shot_oof])
    sw = np.concatenate([np.full(len(t), 1 / len(t)) for t, r in shot_oof])
    metrics["shooting"] = {
        "attempts": len(shots),
        "perGame": shot_metrics,
        "summary": {},
        "target": "Made field goal on an observed shot event, including fouled misses. Field-goal points exclude free throws and rebounds.",
        "skill": "Pooled shot quality only. Player effects are disabled; identity does not affect make probability.",
        "validation": "Outer test game excluded from all shooting fits. Each EPV training row uses a shot model excluding its own game AND the outer test game.",
        "scenario": "Applying release-context probabilities to the current holder is approximate; no body pose or release-delay model.",
    }
    for name in ["constant", "pooled", "personalized"]:
        prob = np.concatenate([r[name] for t, r in shot_oof])
        metrics["shooting"]["summary"][name] = score(sy, prob, "shot", sw)
    manifest = {
        "version": 2,
        "games": [],
        "metrics": metrics,
        "credit": "Tracking and events: SkillCorner Open Data, Liga ACB 2025–26.",
    }
    for gid, payload in payloads.items():
        test, result = predictions[gid]
        for i, row in enumerate(test.itertuples()):
            fr = payload["plays"][row.possessionId]["frames"][row.frameIndex]
            fr["epv"] = round(float(result["points_shooting"][i]), 4)
            fr["epvGeometry"] = round(float(result["points_geometry"][i]), 4)
            if np.isfinite(row.shot_make_probability):
                fr["shot"] = {
                    "makeProbability": round(row.shot_make_probability, 5),
                    "fieldGoalValue": round(row.shot_field_goal_value, 4),
                    "pooledProbability": round(row.shot_pooled_probability, 5),
                    "trainingAttempts": int(row.shot_training_attempts),
                    "region": row.region,
                    "pointsIfMade": 3 if row.three else 2,
                    "shooter": int(row.shooter),
                    "nearLine": bool(
                        abs(max(row.shot_distance - ARC_FT, row.shot_abs_y - CORNER_FT))
                        < 0.5
                    ),
                }
            else:
                fr.pop("shot", None)
            fr["turnover2"] = round(float(result["turnover2_geometry"][i]), 5)
            fr["turnoverRest"] = round(float(result["turnover_rest_geometry"][i]), 5)
            fr["turnoverRestRaw"] = round(float(result["turnover_rest_raw"][i]), 5)
        entries = []
        for pid, play in payload["plays"].items():
            valid = [f for f in play["frames"] if "epv" in f]
            if not valid:
                continue
            summary = {k: v for k, v in play.items() if k not in ["frames", "events"]}
            summary.update(
                {
                    "frames": len(play["frames"]),
                    "supportedFrames": len(valid),
                    "peakRisk": max(f["turnover2"] for f in valid),
                    "initialEpv": valid[0]["epv"],
                }
            )
            entries.append(summary)
            dump(OUT / f"plays/{pid}.json", play)
        manifest["games"].append(
            {
                "match": payload["match"],
                "players": payload["players"],
                "plays": entries,
                "audit": payload["audit"],
            }
        )
    dump(OUT / "manifest.json", manifest)
    dump(ROOT / "artifacts/metrics.json", metrics)
    table.to_pickle(ROOT / "artifacts/states.pkl")
    final = {}
    # All-game deployment model is trained with LOO shooting features as inputs.
    train = pd.concat(
        [test[test.train] for test, result in predictions.values()], ignore_index=True
    )
    w = weights(train)
    for target in TARGETS:
        cols = (
            EPV_GEOMETRY_FEATURES + EPV_SHOT_FEATURES
            if target == "points"
            else FEATURES
        )
        model = estimator(target)
        model.fit(train[cols], train[target], sample_weight=w)
        final[target] = model
    joblib.dump(
        {
            "models": final,
            "shotModel": ShotModel.fit(shots),
            "passModel": fit_pass_model(passes),
            "timingModel": TimingModel.fit(timings),
            "passFeatures": PASS_FEATURES,
            "features": FEATURES,
            "epvFeatures": EPV_GEOMETRY_FEATURES + EPV_SHOT_FEATURES,
            "targets": metrics["targets"],
            "riskPostprocessing": metrics["riskPostprocessing"],
        },
        ROOT / "artifacts/models.joblib",
    )
    print(
        json.dumps(
            {
                "epvAndRisk": metrics["summary"],
                "shooting": metrics["shooting"]["summary"],
            },
            indent=2,
        ),
        flush=True,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rebuild", action="store_true")
    args = parser.parse_args()
    matches = json.loads((ROOT / "data/matches.json").read_text())
    tables = []
    payloads = {}
    for match in matches:
        cache = CACHE / f"{match['id']}.joblib"
        cached = joblib.load(cache) if cache.exists() and not args.rebuild else None
        table, payload = (
            cached
            if cached is not None
            and cached[1].get("extractionVersion") == EXTRACTION_VERSION
            else prepare_game(match)
        )
        tables.append(table)
        payloads[match["id"]] = payload
    with threadpool_limits(limits=4):
        train_and_export(pd.concat(tables, ignore_index=True), payloads)
    from scripts.validate_catches import publish_report

    print("Catch forecast consistency", publish_report(), flush=True)
    from .second_chance import main as annotate_shots

    annotate_shots()
    from .search import main as annotate_search

    annotate_search()
    from .player_profiles import main as annotate_profiles

    annotate_profiles()
    from .shot_review import main as annotate_reviews

    annotate_reviews()
    from .vendor_surrogate import main as annotate_surrogate

    annotate_surrogate()
    from .foul_value import main as annotate_foul_value
    annotate_foul_value()
    from .catch_shoot import main as annotate_catch_shoot
    annotate_catch_shoot()
    from .steal_risk import main as annotate_steal_risk
    from .steal_probability import main as annotate_steal_probability
    annotate_steal_risk()
    annotate_steal_probability()
    annotate_steal_probability("block")
    from .action_defense import main as annotate_action_defense
    annotate_action_defense()
    import subprocess

    subprocess.run(["node", str(ROOT / "scripts/build_decision_audit.mjs")], check=True)
    for script in ("build_touch_history.mjs", "build_rebound_annotations.mjs"):
        subprocess.run(["node", str(ROOT / "scripts" / script)], cwd=ROOT, check=True)
    import sys
    # Exploitable-space fields: open-shot value grids, per-frame summaries, holes
    # (docs/space-field.md); replaces scripts/build_space_value.py.
    subprocess.run([sys.executable, "-m", "epv.space_field"], cwd=ROOT, check=True)
    subprocess.run([sys.executable, "-m", "epv.action_values"], cwd=ROOT, check=True)
    subprocess.run(["node", str(ROOT / "scripts/build_movement_candidates.mjs")], cwd=ROOT, check=True)
    subprocess.run([sys.executable, "-m", "epv.movement"], cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
