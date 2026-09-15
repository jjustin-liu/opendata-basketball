"""Experimental pass destinations, pre-release risk, and projected catch states.

Future ball coordinates are used ONLY to reconstruct training destinations.
The risk model and catch projection consume current/past coordinates only.
"""

import csv
import gzip
import json
import math
from collections import Counter

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .features import EPV_GEOMETRY_FEATURES, segment_clearance, spatial_features
from .shooting import (
    EPV_SHOT_FEATURES,
    attach_predictions,
    location_is_three,
    shot_region,
)

BASE_PASS_FEATURES = [
    "distance",
    "lane_clearance",
    "passer_pressure",
    "receiver_pressure",
    "lane_defenders",
    "receiver_sideline",
]

PASS_FEATURES = BASE_PASS_FEATURES + [
    "intercept_advantage",
    "reachable_defenders",
    "immediate_lane_reach",
]


def interception_features(a, b, defenders):
    """Direct-route reach diagnostic, not an interception probability.

    40 ft/s ball + 0.12 s release. Defenders have 2.5 ft reach and can
    cover ground at 12 ft/s after a 0.18 s reaction delay. Fixed assumptions,
    using positions at decision time only, fitted outcomes determine risk.
    """
    fraction = np.linspace(0.08, 0.95, 24)
    route = a + fraction[:, None] * (b - a)
    distance = np.linalg.norm(defenders[:, None, :] - route[None, :, :], axis=2)
    ball_time = 0.12 + fraction * np.linalg.norm(b - a) / 40
    defense_time = np.where(
        distance <= 2.5, 0, 0.18 + np.maximum(0, distance - 2.5) / 12
    )
    advantages = (ball_time - defense_time).max(axis=1)
    return {
        "intercept_advantage": float(advantages.max()),
        "reachable_defenders": int((advantages > 0).sum()),
        "immediate_lane_reach": int((distance.min(axis=1) <= 2.5).sum()),
    }


TIMING_DESCRIPTION = "Direct-route timing features assume a 40 ft/s pass, 0.12 s release, 2.5 ft defensive reach, and 12 ft/s movement after 0.18 s reaction. Reach warnings are physical diagnostics, not probabilities. The outcome model still learns from selected passes of mixed types; it is not calibrated for a forced straight pass. No bounce/lob route or defender intent model."


def route_diagnostic(features):
    return {
        "advantageSeconds": round(features["intercept_advantage"], 3),
        "reachableDefenders": int(features["reachable_defenders"]),
        "immediateReach": int(features["immediate_lane_reach"]),
    }


def pass_features(frame, passer, receiver):
    off = {p[0]: np.array(p[1:3], float) for p in frame["offense"]}
    if (
        passer not in off
        or receiver not in off
        or passer == receiver
        or len(frame["defense"]) != 5
    ):
        return None
    a, b = off[passer], off[receiver]
    d = np.array([p[1:3] for p in frame["defense"]], float)
    delta = b - a
    distance = float(np.linalg.norm(delta))
    if distance < 2:
        return None
    t = ((d - a) @ delta) / distance**2
    clearance = np.linalg.norm(d - (a + np.clip(t, 0, 1)[:, None] * delta), axis=1)
    features = dict(
        zip(
            BASE_PASS_FEATURES,
            [
                distance,
                segment_clearance(a, b, d),
                np.linalg.norm(d - a, axis=1).min(),
                np.linalg.norm(d - b, axis=1).min(),
                int(((t > 0) & (t < 1) & (clearance < 4)).sum()),
                24.606 - abs(b[1]),
            ],
        )
    )

    return {**features, **interception_features(a, b, d)}


def lane_weights(frame, passer, receiver):
    """Localize the player prior to the route; do not change physical speed."""
    off={p[0]:np.array(p[1:3],float) for p in frame['offense']}
    a,b=off[passer],off[receiver]
    d=np.array([p[1:3] for p in frame['defense']],float)
    delta=b-a
    t=np.clip(((d-a)@delta)/(delta@delta),0,1)
    clearance=np.linalg.norm(d-(a+t[:,None]*delta),axis=1)
    return np.exp(-clearance/4).tolist()


def infer_receiver(frame, passer, flight_ball):
    """Conservative early-flight ray; reject small motion or competing receivers."""
    source = next((p for p in frame["offense"] if p[0] == passer), None)
    if source is None:
        return None
    origin = np.array(frame["ball"][:2])
    ray = np.array(flight_ball[:2]) - origin
    length = np.linalg.norm(ray)
    if length < 3:
        return None
    candidates = []
    for p in frame["offense"]:
        if p[0] == passer:
            continue
        delta = np.array(p[1:3]) - origin
        dist = np.linalg.norm(delta)
        if dist < 2:
            continue
        angle = math.degrees(
            math.acos(float(np.clip(delta @ ray / (dist * length), -1, 1)))
        )
        candidates.append((angle, p[0]))
    candidates.sort()
    if (
        len(candidates) < 2
        or candidates[0][0] > 25
        or candidates[1][0] - candidates[0][0] < 10
    ):
        return None
    return candidates[0][1]


def load_passes(root):
    cache = root / ".cache/epv/pass_training_v3.joblib"
    if cache.exists():
        return joblib.load(cache)
    aliases = {
        int(r["player_id"]): int(r["canonical_player_id"])
        for r in csv.DictReader((root / "data/player_id_aliases.csv").open())
    }
    rows, audit = [], Counter()
    for path in sorted((root / "data/matches").glob("*/*_dynamic_events.json")):
        events = json.loads(path.read_text())
        gid = int(path.parent.name)
        meta = json.loads((path.parent / f"{gid}_game_data.json").read_text())
        possessions = {p["id"]: p for p in events["possessions"]}
        eligible = [
            p
            for p in events["passes"]
            if not p["inbounds"]
            and p.get("endFrame")
            and (p["complete"] is True or p["turnover"] is True)
            and p["passerId"] != p["receiverId"]
        ]
        needed = {
            i
            for p in eligible
            for i in (p["startFrame"] - 1, min(p["startFrame"] + 8, p["endFrame"] - 1))
        }
        snapshots = {}
        with gzip.open(
            root / f".cache/tracking/{gid}_tracking_data.jsonl.gz", "rt"
        ) as f:
            for line in f:
                raw = json.loads(line)
                if raw["frameIdx"] in needed:
                    snapshots[raw["frameIdx"]] = raw
        for p in eligible:
            outcome = int(bool(p["turnover"]))
            key = "failed" if outcome else "completed"
            audit[key + "_eligible"] += 1
            raw = snapshots.get(p["startFrame"] - 1)
            future = snapshots.get(min(p["startFrame"] + 8, p["endFrame"] - 1))
            possession = possessions.get(p["possessionId"])
            if (
                not raw
                or not future
                or not raw["ball"]
                or not future["ball"]
                or not possession
            ):
                continue
            sign = 1 if possession["leftHoop"] else -1
            home = p["offTeamId"] == meta["homeTeam"]["teamId"]

            def players(side, raw=raw, sign=sign):
                return [
                    [
                        aliases.get(a["playerId"], a["playerId"]),
                        a["xyz"][0] * sign,
                        a["xyz"][1] * sign,
                    ]
                    for a in raw[side]
                ]

            frame = {
                "offense": players("homePlayers" if home else "awayPlayers"),
                "defense": players("awayPlayers" if home else "homePlayers"),
                "ball": [raw["ball"]["xyz"][0] * sign, raw["ball"]["xyz"][1] * sign],
            }
            if len(frame["offense"]) != 5 or len(frame["defense"]) != 5:
                continue
            passer = aliases.get(p["passerId"], p["passerId"])
            inferred = infer_receiver(
                frame,
                passer,
                [future["ball"]["xyz"][0] * sign, future["ball"]["xyz"][1] * sign],
            )
            if inferred is None:
                continue
            audit[key + "_reconstructed"] += 1
            receiver = (
                inferred if outcome else aliases.get(p["receiverId"], p["receiverId"])
            )
            if not outcome:
                audit["completed_correct"] += int(inferred == receiver)
            feats = pass_features(frame, passer, receiver)
            if feats is not None:
                rows.append(
                    {
                        **feats,
                        "gameId": gid,
                        "passId": p["id"],
                        "turnover": outcome,
                        "inferredReceiver": inferred,
                        "receiver": receiver,
                        "defenderIds": [d[0] for d in frame["defense"]],
                        "defenderLaneWeights": lane_weights(frame, passer, receiver),
                    }
                )
        print("Pass reconstruction", gid, dict(audit), flush=True)
    table = pd.DataFrame(rows)
    joblib.dump((table, dict(audit)), cache)
    return table, dict(audit)


def fit_pass_model(table, columns=PASS_FEATURES):
    model = make_pipeline(StandardScaler(), LogisticRegression(C=0.1, max_iter=1000))
    model.fit(table[columns], table.turnover)
    return model


def velocities(frame, previous):
    result = {}
    dt = (frame["frame"] - previous["frame"]) / 25 if previous else 0
    if not previous or not 0 < dt <= 0.4 or frame["period"] != previous["period"]:
        return result
    for side in ["offense", "defense"]:
        old = {p[0]: np.array(p[1:3]) for p in previous[side]}
        for p in frame[side]:
            if p[0] in old:
                v = (np.array(p[1:3]) - old[p[0]]) / dt
                speed = np.linalg.norm(v)
                result[p[0]] = v * min(1, 25 / max(speed, 0.001))
    return result


def project_catch(frame, previous, receiver, timing_model=None):
    """Constant velocity, 40 ft/s ball, 0.12 s release; no future replay frames."""
    holder = frame.get("geometry", {}).get("handler")
    people = {p[0]: p for p in frame["offense"]}
    if holder not in people or receiver not in people or holder == receiver:
        return None
    v = velocities(frame, previous)
    source = np.array(people[holder][1:3])
    target = np.array(people[receiver][1:3])
    if timing_model is not None:
        from .pass_timing import timing_features

        timing = timing_features(frame, previous, holder, receiver)
        if timing is None:
            return None
        dt = 0.12 + timing_model.duration(timing)
    else:
        dt = 0.12 + np.linalg.norm(target - source) / 40
        for _ in range(3):
            dt = (
                0.12
                + np.linalg.norm(target + v.get(receiver, np.zeros(2)) * dt - source)
                / 40
            )
    if (
        dt > 1.5
        or frame.get("shotClock") is None
        or frame["shotClock"] <= dt
        or frame["gameClock"] <= dt
    ):
        return None
    projected = {
        **frame,
        "frame": frame["frame"] + dt * 25,
        "gameClock": frame["gameClock"] - dt,
        "shotClock": frame["shotClock"] - dt,
    }
    for side in ["offense", "defense"]:
        projected[side] = [
            [p[0], *(np.array(p[1:3]) + v.get(p[0], np.zeros(2)) * dt), *p[3:]]
            for p in frame[side]
        ]
    recipient = next(p for p in projected["offense"] if p[0] == receiver)
    # The intended catch must be in bounds. Other players reaching a boundary
    # stop at it in this approximation instead of invalidating the whole state.
    if abs(recipient[1]) > 45.932 or abs(recipient[2]) > 24.606:
        return None
    for side in ["offense", "defense"]:
        for p in projected[side]:
            if p[0] != receiver:
                p[1] = float(np.clip(p[1], -45.932, 45.932))
                p[2] = float(np.clip(p[2], -24.606, 24.606))
    projected["ball"] = [*recipient[1:3], 3, 1, 0]
    # Construct a short preceding state using the SAME pre-pass velocity
    # projection. This yields closing speed and boundary-aware holder motion;
    # it never reads later replay frames or teleports the ball from the passer.
    history = None
    if receiver in v:
        history = {**projected, "frame": projected["frame"] - 5}
        for side in ["offense", "defense"]:
            history[side] = []
            for p in frame[side]:
                xy = np.array(p[1:3]) + v.get(p[0], np.zeros(2)) * (dt - 0.2)
                xy = np.clip(xy, [-45.932, -24.606], [45.932, 24.606])
                history[side].append([p[0], *xy, *p[3:]])
        old_receiver = next(p for p in history["offense"] if p[0] == receiver)
        history["ball"] = [*old_receiver[1:3], 3, 1, frame["ball"][4]]
    calc = spatial_features(projected, history)
    if calc is None or calc[1]["handler"] != receiver:
        return None
    features, geometry = calc
    projected["geometry"] = geometry
    if history is None:
        for key in ["handler_speed", "handler_toward_rim", "defender_closing_speed"]:
            features[key] = np.nan
    features["holder_x"], features["holder_y"] = recipient[1:3]
    features.update(
        shooter=receiver,
        shot_distance=features["handler_rim_distance"],
        shot_defender=features["nearest_defender"],
        shot_abs_y=abs(recipient[2]),
    )
    features["three"] = bool(
        location_is_three(features["shot_distance"], features["shot_abs_y"])
    )
    features["region"] = str(
        shot_region(
            np.array([features["shot_distance"]]), np.array([features["three"]])
        )[0]
    )
    return dt, projected, features


def export_options(payload, pass_model, epv_model, shot_model, timing_model=None):
    rows, refs = [], []
    for play in payload["plays"].values():
        for i, frame in enumerate(play["frames"]):
            frame.pop("passOptions", None)
            if frame.get("reason") or not frame.get("geometry"):
                continue
            holder = frame["geometry"]["handler"]
            for player in frame["offense"]:
                receiver = player[0]
                feats = pass_features(frame, holder, receiver)
                catch = project_catch(
                    frame, play["frames"][i - 1] if i else None, receiver, timing_model
                )
                if feats is None or catch is None:
                    continue
                dt, projected, state = catch
                rows.append({**state, **{"pass_" + k: val for k, val in feats.items()}})
                refs.append((frame, receiver, dt, projected))
    if not rows:
        return
    table = attach_predictions(pd.DataFrame(rows), shot_model)
    risk = pass_model.predict_proba(
        table[["pass_" + k for k in PASS_FEATURES]].rename(columns=lambda k: k[5:])
    )[:, 1]
    epv = np.maximum(
        0, epv_model.predict(table[EPV_GEOMETRY_FEATURES + EPV_SHOT_FEATURES])
    )
    for (frame, receiver, dt, projected), p, value, row in zip(refs, risk, epv, rows):
        frame.setdefault("passOptions", []).append(
            {
                "player": receiver,
                "route": route_diagnostic({k: row["pass_" + k] for k in PASS_FEATURES}),
                "turnoverProbability": round(float(p), 5),
                "completedEpv": round(float(value), 4),
                "value": round(float((1 - p) * value), 4),
                "arrivalSeconds": round(float(dt), 3),
                "timingModel": "learned" if timing_model is not None else "fixed40",
                "flightSeconds": round(float(dt - 0.12), 3),
                "offense": [
                    [a[0], round(float(a[1]), 2), round(float(a[2]), 2)]
                    for a in projected["offense"]
                ],
                "defense": [
                    [a[0], round(float(a[1]), 2), round(float(a[2]), 2)]
                    for a in projected["defense"]
                ],
            }
        )
