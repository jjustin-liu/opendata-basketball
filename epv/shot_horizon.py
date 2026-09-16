"""Momentum-projected shoot-now value at t+delta; a kinematic scenario, not a policy value.

The per-frame SHOT number answers "release from this exact state". Along a drive
that conditional collapses - the holder crosses the arc and is briefly too far for
a layup and too covered for a jumper - while the possession is improving. This
module projects the holder and the defense forward on causal velocity and rescores
the same released-shot estimator at the later state, under three defensive
responses, and reports the band.

No future replay sample enters a projection. Validation compares each projection
with the estimator's own value at the observed later frame, so it measures state
projection error only, not shooting-model error.
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from . import second_chance as rebounds
from .catch_shoot import catch_shoot_value
from .features import HOOP
from .shooting import load_shots, location_is_three
from .vendor_surrogate import features, fit, season_evidence

ROOT = Path(__file__).resolve().parents[1]
HORIZONS = (0.4, 0.8, 1.2)
RESPONSES = ("hold", "momentum", "close")
WINDOW = 10        # trailing 0.4 s of causal tracking for velocity
GAP = 10           # break velocity and horizon matching across tracking gaps
REACTION = 0.2
POOLED_CAP = 18.0  # ft/s fallback before any other-game evidence
QUANTILE = 0.99    # a guardrail against tracking spikes, not a typical-speed prior
SHRINK = 200       # speed samples before a player's own quantile dominates
MIN_CLOCK = 0.5    # leave room for a release after the projected arrival
MAX_DISTANCE = 32.0
LOW = np.array([-45.932, -24.606])
HIGH = np.array([45.932, 24.606])
THREE_EVIDENCE = 20


def trailing_velocity(frames, i):
    """Mean velocity over the trailing supported window; previous samples only."""
    current = frames[i]
    j = i
    while j > 0:
        previous = frames[j - 1]
        if previous["period"] != current["period"]:
            break
        if frames[j]["frame"] - previous["frame"] > GAP:
            break
        if current["frame"] - previous["frame"] > WINDOW:
            break
        j -= 1
    if j == i:
        return {}
    dt = (current["frame"] - frames[j]["frame"]) / 25
    old = {p[0]: np.asarray(p[1:3], float)
           for side in ("offense", "defense") for p in frames[j][side]}
    return {p[0]: (np.asarray(p[1:3], float) - old[p[0]]) / dt
            for side in ("offense", "defense") for p in current[side] if p[0] in old}


def speed_samples(root, manifest):
    """Frame-to-frame speeds per player and game; the source of the speed caps."""
    samples = {}
    for game in manifest["games"]:
        gid = int(game["match"]["id"])
        for entry in game["plays"]:
            frames = json.loads((root / f"viewer/data/plays/{entry['id']}.json").read_text())["frames"]
            for i in range(1, len(frames)):
                dt = (frames[i]["frame"] - frames[i - 1]["frame"]) / 25
                if not 0 < dt <= 0.4 or frames[i]["period"] != frames[i - 1]["period"]:
                    continue
                old = {p[0]: p[1:3] for side in ("offense", "defense") for p in frames[i - 1][side]}
                for side in ("offense", "defense"):
                    for p in frames[i][side]:
                        q = old.get(p[0])
                        if q is None:
                            continue
                        speed = float(np.hypot(p[1] - q[0], p[2] - q[1])) / dt
                        if speed < 25:
                            samples.setdefault(p[0], {}).setdefault(gid, []).append(speed)
    return {pid: {gid: np.asarray(v, dtype=np.float32) for gid, v in by_game.items()}
            for pid, by_game in samples.items()}


def speed_caps(samples, exclude):
    """Shrunk 99th-percentile speed from the other nine games, per player.

    Measured spread is narrow (p10 16.3, p90 19.4 ft/s) and does not separate
    guards from bigs, so this caps tracking spikes rather than personalising
    speed. Observed velocity, not the cap, carries a live speed mismatch.
    """
    pooled = np.concatenate([v for by_game in samples.values()
                             for gid, v in by_game.items() if gid != exclude] or [np.array([POOLED_CAP])])
    floor = float(np.quantile(pooled, QUANTILE))
    caps = {}
    for pid, by_game in samples.items():
        values = [v for gid, v in by_game.items() if gid != exclude]
        if not values:
            caps[pid] = floor
            continue
        values = np.concatenate(values)
        caps[pid] = float((len(values) * np.quantile(values, QUANTILE) + SHRINK * floor) / (len(values) + SHRINK))
    return caps, floor


def advance(position, velocity, seconds, cap, target=None):
    """Constant heading at capped speed, stopping at closest approach to target."""
    speed = float(np.linalg.norm(velocity))
    if speed <= 1e-9:
        return position
    v = np.asarray(velocity, float) * min(1.0, cap / speed)
    t = seconds
    if target is not None:
        approach = float(np.dot(np.asarray(target, float) - position, v) / np.dot(v, v))
        if approach > 0:
            t = min(t, approach)
    return np.clip(position + v * t, LOW, HIGH)


def projected_state(frame, velocity, seconds, response, caps, holder, floor):
    """Holder drives on, teammates carry momentum, defenders answer one of three ways."""
    player = next((p for p in frame["offense"] if p[0] == holder), None)
    clock = frame.get("shotClock")
    if player is None or clock is None or clock - seconds <= MIN_CLOCK:
        return None
    if len(frame["offense"]) != 5 or len(frame["defense"]) != 5:
        return None
    if any(p[0] not in velocity for p in frame["offense"] + frame["defense"]):
        return None
    cap = lambda pid: caps.get(pid, floor)
    # A driver gathers at the rim rather than running through it.
    spot = advance(np.asarray(player[1:3], float), velocity[holder], seconds, cap(holder), HOOP)
    offense = [[holder, float(spot[0]), float(spot[1])] if p[0] == holder else
               [p[0], *map(float, advance(np.asarray(p[1:3], float), velocity[p[0]], seconds, cap(p[0])))]
               for p in frame["offense"]]
    nearest = min(frame["defense"], key=lambda d: float(np.hypot(d[1] - spot[0], d[2] - spot[1])))[0]
    defense = []
    for d in frame["defense"]:
        start = np.asarray(d[1:3], float)
        if response == "hold":
            end = start
        elif response == "close" and d[0] == nearest:
            delta = spot - start
            length = float(np.linalg.norm(delta))
            end = start + delta * min(1.0, cap(d[0]) * max(0.0, seconds - REACTION) / max(length, 1e-9))
        else:
            end = advance(start, velocity[d[0]], seconds, cap(d[0]), spot)
        defense.append([d[0], *map(float, np.clip(end, LOW, HIGH))])
    return dict(offense=offense, defense=defense, shotClock=clock - seconds)


def candidate(state, shooter, evidence):
    """Surrogate inputs for a hypothetical release, or None outside model support."""
    x = features(state, shooter)
    if x is None or x[0] > MAX_DISTANCE:
        return None
    three = bool(location_is_three(x[0], x[2]))
    if three and evidence.get(shooter, {}).get("attempts", 0) < THREE_EVIDENCE:
        return None
    geometry = rebounds.geometry(state, shooter)
    if geometry is None:
        return None
    return x, geometry, three


def survival(frame, seconds):
    """Constant-hazard read of the existing next-two-second turnover probability."""
    risk = frame.get("turnover2")
    if risk is None:
        return None
    return float(max(0.0, 1.0 - risk) ** (seconds / 2))


def game_projections(game, plays, shots, rt, samples, root):
    """Every horizon and response for one held-out game, scored in one batch."""
    gid = int(game["match"]["id"])
    evidence = season_evidence(game)
    sq = fit(shots[shots.gameId != gid], {p: e["rate"] for p, e in evidence.items() if e["rate"] is not None})
    reb, continuation = rebounds.fit(rt[rt.gameId != gid])
    caps, floor = speed_caps(samples, gid)
    rows, keys = [], []
    for pid, play in plays.items():
        frames = play["frames"]
        for i, frame in enumerate(frames):
            frame.pop("shotHorizon", None)
            holder = (frame.get("geometry") or {}).get("handler")
            if frame.get("reason") or holder is None or not frame.get("shot"):
                continue
            velocity = trailing_velocity(frames, i)
            if holder not in velocity:
                continue
            for seconds in HORIZONS:
                for response in RESPONSES:
                    state = projected_state(frame, velocity, seconds, response, caps, holder, floor)
                    if state is None:
                        continue
                    found = candidate(state, holder, evidence)
                    if found is None:
                        continue
                    x, geometry, three = found
                    rows.append((x, geometry, three, holder))
                    keys.append((pid, i, seconds, response))
    if not rows:
        return {}, caps, floor
    quality = np.clip(sq.predict(np.array([r[0] for r in rows]), [r[3] for r in rows], [r[2] for r in rows]), 0, 1)
    orb = reb.predict_proba(pd.DataFrame([r[1] for r in rows])[rebounds.COLUMNS])[:, 1]
    out = {}
    for (pid, i, seconds, response), (x, _, three, _), q, o in zip(keys, rows, quality, orb):
        value = catch_shoot_value(q, 3 if three else 2, o, continuation)
        out.setdefault((pid, i, seconds), {})[response] = dict(
            pps=value["pps"], distance=round(float(x[0]), 2), defenderFeet=round(float(x[1]), 2), three=three)
    return out, caps, floor

CALIBRATION = ("hold", "momentum", "close", "persistence")


def design(rows, columns=CALIBRATION):
    return np.column_stack([np.array([r[c] for r in rows]) for c in columns] + [np.ones(len(rows))])


def fit_calibration(rows, columns=CALIBRATION, ridge=1e-3):
    """Per horizon, least squares from the three responses and persistence to the observed later value.

    Persistence is an input, so the fit can shrink toward no change; held-out skill
    above zero is therefore the test of whether momentum adds anything to it.
    """
    result = {}
    for seconds in HORIZONS:
        subset = [r for r in rows if r["seconds"] == seconds]
        if len(subset) < 200:
            continue
        x, y = design(subset, columns), np.array([r["target"] for r in subset])
        penalty = ridge * np.eye(x.shape[1])
        penalty[-1, -1] = 0
        result[seconds] = np.linalg.solve(x.T @ x + penalty, x.T @ y)
    return result


def apply_calibration(weights, seconds, responses, persistence, columns=CALIBRATION):
    coefficients = weights.get(seconds)
    if coefficients is None:
        return None
    values = [responses[c]["pps"] if c in responses else persistence for c in columns]
    return float(np.dot(coefficients, values + [1.0]))


def attach(plays, projections, caps, floor, weights):
    """Write the per-frame band the viewer can draw next to shoot-now."""
    written = 0
    for (pid, i, seconds), responses in sorted(projections.items()):
        if len(responses) != len(RESPONSES):
            continue
        frame = plays[pid]["frames"][i]
        holder = frame["geometry"]["handler"]
        values = [responses[r]["pps"] for r in RESPONSES]
        live = survival(frame, seconds)
        persistence = frame["shot"]["shotPlusSecondChance"]
        calibrated = apply_calibration(weights, seconds, responses, persistence)
        if calibrated is None:
            continue
        point = dict(seconds=seconds, pps=round(calibrated, 4),
                     rawMean=round(float(np.mean(values)), 4),
                     lo=round(float(min(values)), 4), hi=round(float(max(values)), 4),
                     closePps=round(float(responses["close"]["pps"]), 4),
                     distance=responses["close"]["distance"], defenderFeet=responses["close"]["defenderFeet"],
                     three=responses["close"]["three"],
                     survival=None if live is None else round(live, 4),
                     discounted=None if live is None else round(calibrated * live, 4))
        horizon = frame.setdefault("shotHorizon", dict(
            source="momentum-projection-v1", holder=holder,
            capFeetPerSecond=round(caps.get(holder, floor), 2), now=frame["shot"]["shotPlusSecondChance"], points=[]))
        horizon["points"].append(point)
        written += 1
    for play in plays.values():
        for frame in play["frames"]:
            horizon = frame.get("shotHorizon")
            if not horizon:
                continue
            best = max([dict(seconds=0.0, discounted=horizon["now"])] +
                       [p for p in horizon["points"] if p["discounted"] is not None],
                       key=lambda p: p["discounted"])
            horizon["bestSeconds"] = best["seconds"]
            horizon["bestDiscounted"] = round(float(best["discounted"]), 4)
    return written


def future_frame(frames, i, seconds):
    """The observed sample one horizon later: same handler, supported, no tracking gap."""
    target = frames[i]["frame"] + 25 * seconds
    holder = frames[i]["geometry"]["handler"]
    for j in range(i + 1, len(frames)):
        if frames[j]["frame"] - frames[j - 1]["frame"] > GAP or frames[j]["period"] != frames[i]["period"]:
            return None
        if abs(frames[j]["frame"] - target) <= 2:
            if frames[j].get("reason") or not frames[j].get("shot"):
                return None
            if (frames[j].get("geometry") or {}).get("handler") != holder:
                return None
            return frames[j]
        if frames[j]["frame"] > target + 2:
            return None
    return None


def validation_rows(gid, plays, projections):
    """Projection against the same estimator's value at the observed later frame."""
    rows = []
    for (pid, i, seconds), responses in projections.items():
        if len(responses) != len(RESPONSES):
            continue
        frames = plays[pid]["frames"]
        frame = frames[i]
        later = future_frame(frames, i, seconds)
        if later is None:
            continue
        holder = frame["geometry"]["handler"]
        velocity = trailing_velocity(frames, i)
        if holder not in velocity:
            continue
        values = [responses[r]["pps"] for r in RESPONSES]
        rows.append(dict(
            gameId=gid, play=pid, frame=frame["frame"], seconds=seconds,
            speed=float(np.linalg.norm(velocity[holder])),
            projection=float(np.mean(values)), close=float(responses["close"]["pps"]),
            hold=float(responses["hold"]["pps"]), momentum=float(responses["momentum"]["pps"]),
            persistence=float(frame["shot"]["shotPlusSecondChance"]),
            target=float(later["shot"]["shotPlusSecondChance"]),
            crossing=bool(responses["close"]["three"] != (later["shot"]["pointsIfMade"] == 3))))
    return rows


def score(rows, column="calibrated"):
    if not rows or column not in rows[0]:
        return None
    predicted = np.array([r[column] for r in rows])
    persistence = np.array([r["persistence"] for r in rows])
    actual = np.array([r["target"] for r in rows])
    moved = actual != persistence
    agreed = np.sign(predicted - persistence)[moved] == np.sign(actual - persistence)[moved]
    mae, base = float(np.abs(predicted - actual).mean()), float(np.abs(persistence - actual).mean())
    return dict(n=len(rows), mae=round(mae, 4), persistenceMae=round(base, 4),
                rmse=round(float(np.sqrt(((predicted - actual) ** 2).mean())), 4),
                persistenceRmse=round(float(np.sqrt(((persistence - actual) ** 2).mean())), 4),
                bias=round(float((predicted - actual).mean()), 4),
                skill=round(1 - mae / base, 4) if base else None,
                directionAccuracy=round(float(agreed.mean()), 4) if moved.any() else None)


def momentum_gain(subset):
    """Share of the shrinkage-only error that the projection itself removes."""
    full, plain = score(subset), score(subset, "shrunk")
    if not full or not plain or not plain["mae"]:
        return None
    return round((plain["mae"] - full["mae"]) / plain["mae"], 4)


def report(rows):
    """Per horizon, per response and per regime; the fast-drive rows are the point."""
    summary = {}
    for seconds in HORIZONS:
        subset = [r for r in rows if r["seconds"] == seconds]
        fast = [r for r in subset if r["speed"] >= 10]
        summary[f"+{seconds}s"] = dict(
            momentumGain=momentum_gain(subset),
            momentumGainFast=momentum_gain(fast),
            fastShrinkageOnly=score(fast, "shrunk"),
            all=score(subset),
            fast=score([r for r in subset if r["speed"] >= 10]),
            slow=score([r for r in subset if r["speed"] < 10]),
            arcCrossing=score([r for r in subset if r["crossing"]]),
            rawMean=score(subset, "projection"),
            shrinkageOnly=score(subset, "shrunk"),
            closeResponseOnly=score(subset, "close"),
            holdResponseOnly=score(subset, "hold"),
            byGame={str(gid): score([r for r in subset if r["gameId"] == gid])
                    for gid in sorted({r["gameId"] for r in rows})})
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, nargs="*")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()
    manifest_path = ROOT / "viewer/data/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    shots = load_shots(ROOT)
    shots = shots[shots.vendorQuality.between(0, 100)]
    rt, _ = rebounds.load_examples(ROOT)
    samples = speed_samples(ROOT, manifest)
    games = [g for g in manifest["games"]
             if not args.games or int(g["match"]["id"]) in args.games]

    # Pass one: raw physics projections and the comparison rows they can be judged on.
    raw, rows = {}, []
    for game in games:
        gid = int(game["match"]["id"])
        plays = {entry["id"]: json.loads((ROOT / f"viewer/data/plays/{entry['id']}.json").read_text())
                 for entry in game["plays"]}
        projections, caps, floor = game_projections(game, plays, shots, rt, samples, ROOT)
        raw[gid] = (projections, caps, floor)
        rows.extend(validation_rows(gid, plays, projections))
        print("Projected", gid, len(projections), flush=True)

    # Pass two: calibrate each game on the other nine, then evaluate and write.
    total, scored = 0, []
    for game in games:
        gid = int(game["match"]["id"])
        projections, caps, floor = raw[gid]
        others = [r for r in rows if r["gameId"] != gid] or rows
        weights = fit_calibration(others)
        # Ablation: the same shrinkage without any projection input.
        shrinkage = fit_calibration(others, ("persistence",))
        fold = [r for r in rows if r["gameId"] == gid]
        for row in fold:
            responses = {c: dict(pps=row[c]) for c in RESPONSES}
            value = apply_calibration(weights, row["seconds"], responses, row["persistence"])
            row["calibrated"] = row["persistence"] if value is None else value
            plain = apply_calibration(shrinkage, row["seconds"], {}, row["persistence"], ("persistence",))
            row["shrunk"] = row["persistence"] if plain is None else plain
        scored.extend(fold)
        if not args.no_write:
            plays = {entry["id"]: json.loads((ROOT / f"viewer/data/plays/{entry['id']}.json").read_text())
                     for entry in game["plays"]}
            total += attach(plays, projections, caps, floor, weights)
            for pid, play in plays.items():
                (ROOT / f"viewer/data/plays/{pid}.json").write_text(
                    json.dumps(play, separators=(",", ":"), allow_nan=False))
            print("Shot horizon", gid, total, flush=True)

    if not args.no_write and not args.games:
        manifest["metrics"]["shotHorizon"] = dict(
            projections=total, horizons=list(HORIZONS), responses=list(RESPONSES),
            scope="Causal constant-heading projection of the holder and defence, rescored with the same "
                  "released-shot surrogate and field-goal rebound continuation, then blended with the current "
                  "shoot-now value by a least-squares fit on the other nine games. No fouls, no free throws, no "
                  "route feasibility and no adaptive help. Conditional on still holding the ball; the discounted "
                  "value applies the existing next-two-second turnover probability at constant hazard.")
        manifest_path.write_text(json.dumps(manifest, separators=(",", ":"), allow_nan=False))

    if args.validate:
        summary = report(scored)
        (ROOT / "artifacts/shot-horizon-validation.json").write_text(json.dumps(dict(
            horizons=list(HORIZONS), responses=list(RESPONSES), comparisons=len(scored),
            target="Shoot-now value of the same held-out estimator at the observed later frame",
            baseline="Persistence: the current shoot-now value carried forward",
            calibration="Least squares from hold/momentum/close and persistence, fitted on the other nine games",
            scope="Measures state projection only, not shooting-model error. Rows need the same handler, a "
                  "supported later frame and no tracking gap, so they condition on the possession continuing.",
            summary=summary), indent=2))
        print(f"{'horizon':>8} {'group':>12} {'n':>6} {'MAE':>7} {'persist':>8} {'skill':>7} {'dir':>7} {'bias':>7}")
        for horizon, groups in summary.items():
            for name in ("all", "fast", "slow", "arcCrossing"):
                entry = groups[name]
                if not entry:
                    continue
                print(f"{horizon:>8} {name:>12} {entry['n']:>6} {entry['mae']:>7.3f} "
                      f"{entry['persistenceMae']:>8.3f} {entry['skill']:>+7.3f} "
                      f"{entry['directionAccuracy']:>7} {entry['bias']:>+7.3f}")
    print(json.dumps(dict(projections=total, comparisons=len(scored))))


if __name__ == "__main__":
    with threadpool_limits(limits=2):
        main()
