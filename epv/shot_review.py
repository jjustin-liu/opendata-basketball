"""Attach exact shot-event clocks for replay postmortems."""

import json
import math
from pathlib import Path


def apply_release_quality(event, shot):
    """Observed release only; vendor score interpreted as percent make probability."""
    event["fouled"] = bool(shot.get("fouled"))
    forecast = event.get("shotForecast")
    if not forecast:
        return False
    quality = forecast.get("quality") or {}
    if "pooledQuality" not in forecast:
        forecast["pooledQuality"] = dict(quality)
    score = shot.get("shotQuality")
    valid = isinstance(score, (int, float)) and not isinstance(score, bool) and math.isfinite(score) and 0 <= score <= 100
    if valid:
        probability = score / 100
        points = 3 if shot["three"] else 2
        quality = {**forecast["pooledQuality"], "makeProbability": probability,
                   "fieldGoalValue": round(probability * points, 4),
                   "pointsIfMade": points, "vendorQuality": score,
                   "source": "skillcorner"}
    else:
        quality = {**forecast["pooledQuality"], "source": "pooled-fallback"}
    forecast["quality"] = quality
    per_miss = forecast.get("secondChancePerMiss")
    probability = quality.get("makeProbability")
    forecast["secondChancePerShot"] = round((1-probability)*per_miss, 4) if probability is not None and per_miss is not None else None
    if event["fouled"]:
        forecast["secondChancePerShot"] = None
        forecast["foulValueUnavailable"] = True
    return valid


def main():
    root = Path(__file__).resolve().parents[1]
    updated = 0
    for source in (root / "data/matches").glob("*/*_dynamic_events.json"):
        shots = json.loads(source.read_text())["shots"]
        groups = {}
        for shot in shots:
            groups.setdefault(shot["possessionId"], {})[shot["startFrame"]] = shot
        for pid, by_frame in groups.items():
            path = root / f"viewer/data/plays/{pid}.json"
            if not path.exists():
                continue
            play = json.loads(path.read_text())
            for event in play["events"]:
                if event["type"] != "shot" or event["frame"] not in by_frame:
                    continue
                shot = by_frame[event["frame"]]
                event.update(
                    shotClock=shot["shotClock"], gameClock=shot["startGameClock"]
                )
                apply_release_quality(event, shot)
                updated += 1
            path.write_text(json.dumps(play, separators=(",", ":"), allow_nan=False))
    print(f"Attached release clocks for {updated} shots")


if __name__ == "__main__":
    main()
