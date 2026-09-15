"""Compare pre-pass catch EPV with observed post-catch EPV, both held out.
This is forecast consistency, NOT validation against true expected points.
"""

import csv
import json
from pathlib import Path
from bisect import bisect_left
import math
import statistics

ROOT = Path(__file__).resolve().parents[1]


def audit():
    aliases = {
        int(r["player_id"]): int(r["canonical_player_id"])
        for r in csv.DictReader((ROOT / "data/player_id_aliases.csv").open())
    }
    records = []
    for path in (ROOT / "data/matches").glob("*/*_dynamic_events.json"):
        plays = {}
        for e in json.loads(path.read_text())["passes"]:
            if e["complete"] is not True or e["inbounds"] or not e["endFrame"]:
                continue
            pid = e["possessionId"]
            fpath = ROOT / f"viewer/data/plays/{pid}.json"
            if not fpath.exists():
                continue
            if pid not in plays:
                plays[pid] = json.loads(fpath.read_text())
            frames = plays[pid]["frames"]
            idx = bisect_left([f["frame"] for f in frames], e["startFrame"]) - 1
            if idx < 0 or e["startFrame"] - frames[idx]["frame"] > 5:
                continue
            pre = frames[idx]
            receiver = aliases.get(e["receiverId"], e["receiverId"])
            option = next(
                (o for o in pre.get("passOptions", []) if o["player"] == receiver), None
            )
            if not option:
                continue
            actual = next(
                (
                    f
                    for f in frames[idx + 1 :]
                    if e["endFrame"] <= f["frame"] <= e["endFrame"] + 8
                    and "epv" in f
                    and f.get("geometry", {}).get("handler") == receiver
                ),
                None,
            )
            if actual is None:
                continue
            predicted_loc = next(p[1:3] for p in option["offense"] if p[0] == receiver)
            observed_loc = next(p[1:3] for p in actual["offense"] if p[0] == receiver)
            records.append(
                {
                    "passId": e["id"],
                    "gameId": int(path.parent.name),
                    "predicted": option["completedEpv"],
                    "observed": actual["epv"],
                    "error": option["completedEpv"] - actual["epv"],
                    "positionErrorFt": math.dist(predicted_loc, observed_loc),
                    "postCatchDelay": (actual["frame"] - e["endFrame"]) / 25,
                }
            )
    return records


if __name__ == "__main__":
    rows = audit()
    print(
        json.dumps(
            {
                "passes": len(rows),
                "mae": statistics.mean(abs(r["error"]) for r in rows),
                "bias": statistics.mean(r["error"] for r in rows),
                "receiverErrorFt": statistics.mean(r["positionErrorFt"] for r in rows),
            },
            indent=2,
        )
    )
    import sys

    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(json.dumps(rows))


def summarize(records):
    if not records:
        return {"passes": 0}
    return {
        "passes": len(records),
        "mae": statistics.mean(abs(r["error"]) for r in records),
        "bias": statistics.mean(r["error"] for r in records),
        "receiverErrorFt": statistics.mean(r["positionErrorFt"] for r in records),
        "meanPostCatchDelay": statistics.mean(r["postCatchDelay"] for r in records),
        "meaning": "Pre-release predicted conditional catch EPV versus the same held-out model at the first supported actual catch state, at most 0.32 s after the event. This is forecast consistency, not ground-truth EPV accuracy. Pass-weighted summary.",
    }


def publish_report():
    rows = audit()
    summary = summarize(rows)
    (ROOT / "artifacts/catch_validation.json").write_text(
        json.dumps({"summary": summary, "passes": rows})
    )
    for path in [ROOT / "viewer/data/manifest.json", ROOT / "artifacts/metrics.json"]:
        value = json.loads(path.read_text())
        metrics = value["metrics"] if "metrics" in value else value
        metrics["catchValidation"] = summary
        path.write_text(json.dumps(value, separators=(",", ":"), allow_nan=False))
    return summary
