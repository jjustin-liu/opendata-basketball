"""Fit top speed / acceleration percentiles from detected 25 Hz tracking.

Centred smoothing is fine here: these are global constants, not per-state features.
Writes artifacts/movement-constants.json.
"""
import gzip, json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def game_samples(gid):
    tracks = {}
    with gzip.open(ROOT / f".cache/tracking/{gid}_tracking_data.jsonl.gz", "rt") as f:
        for line in f:
            d = json.loads(line)
            if d["gameClockStopped"] or len(d["homePlayers"]) != 5 or len(d["awayPlayers"]) != 5:
                continue
            for a in d["homePlayers"] + d["awayPlayers"]:
                if a["isDetected"]:
                    tracks.setdefault(a["playerId"], []).append((d["frameIdx"], a["xyz"][0], a["xyz"][1]))
    speeds, accels = [], []
    for rows in tracks.values():
        r = np.array(rows)
        for seg in np.split(r, np.flatnonzero(np.diff(r[:, 0]) != 1) + 1):
            if len(seg) < 25:
                continue
            k = np.ones(5) / 5  # 0.2 s moving average
            sx, sy = np.convolve(seg[:, 1], k, "valid"), np.convolve(seg[:, 2], k, "valid")
            v = np.hypot(sx[10:] - sx[:-10], sy[10:] - sy[:-10]) / 0.4  # centred ±0.2 s
            a = np.abs(v[5:] - v[:-5]) / 0.2
            speeds.append(v)
            accels.append(a)
    return np.concatenate(speeds), np.concatenate(accels)


def main():
    matches = json.loads((ROOT / "data/matches.json").read_text())
    per_game, all_v, all_a = [], [], []
    for m in matches:
        v, a = game_samples(m["id"])
        per_game.append({"gameId": m["id"], "speed_p99": float(np.percentile(v, 99)), "speed_p999": float(np.percentile(v, 99.9)),
                         "accel_p99": float(np.percentile(a, 99)), "samples": int(len(v))})
        all_v.append(v); all_a.append(a)
        print(per_game[-1], flush=True)
    v, a = np.concatenate(all_v), np.concatenate(all_a)
    out = {"method": "Detected positions only, 0.2 s moving average, centred ±0.2 s speed, 0.2 s speed change for acceleration.",
           "speed_p99": float(np.percentile(v, 99)), "speed_p999": float(np.percentile(v, 99.9)),
           "accel_p99": float(np.percentile(a, 99)), "accel_p999": float(np.percentile(a, 99.9)), "perGame": per_game}
    (ROOT / "artifacts/movement-constants.json").write_text(json.dumps(out, indent=2))
    print(json.dumps({k: v for k, v in out.items() if k != "perGame"}, indent=2))


if __name__ == "__main__":
    main()
