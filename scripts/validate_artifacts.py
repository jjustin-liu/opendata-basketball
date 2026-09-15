"""Check exported data, held-out provenance, geometry alignment and risk bounds."""

import json
import math
from pathlib import Path
import statistics
import sys
from collections import Counter
import joblib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from epv.shooting import load_shots

shots = load_shots(ROOT)
manifest = json.loads((ROOT / "viewer/data/manifest.json").read_text())
assert len(manifest["games"]) == 10
for metric in manifest["metrics"]["perGame"]:
    assert metric["gameId"] not in metric["trainingGameIds"]
    assert len(metric["trainingGameIds"]) == 9
states = 0
plays = 0
alignment = []
shot_states = 0
for game in manifest["games"]:
    gid = game["match"]["id"]
    shot_counts = Counter(
        zip(shots[shots.gameId != gid].shooter, shots[shots.gameId != gid].region)
    )
    table, payload = joblib.load(ROOT / f".cache/epv/{gid}.joblib")
    source = json.loads(
        (ROOT / f"data/matches/{gid}/{gid}_dynamic_events.json").read_text()
    )
    byframe = {f["frame"]: f for p in payload["plays"].values() for f in p["frames"]}
    for shot in source["shots"]:
        fr = byframe.get(shot["startFrame"])
        if fr and shot["location"]:
            shooter = next(
                (p for p in fr["offense"] if p[0] == shot["shooterId"]), None
            )
            if shooter:
                alignment.append(math.dist(shooter[1:3], shot["location"]))
    for entry in game["plays"]:
        p = json.loads((ROOT / f"viewer/data/plays/{entry['id']}.json").read_text())
        plays += 1
        assert p["gameId"] == gid
        assert all(
            a["frame"] < b["frame"] for a, b in zip(p["frames"], p["frames"][1:])
        )
        count = 0
        for fr in p["frames"]:
            if "epv" in fr:
                count += 1
                states += 1
                assert fr["reason"] is None
                assert math.isfinite(fr["epv"]) and fr["epv"] >= 0
                assert 0 <= fr["turnover2"] <= fr["turnoverRest"] <= 1
                assert len(fr["offense"]) == len(fr["defense"]) == 5
                assert math.isfinite(fr["epvGeometry"]) and fr["epvGeometry"] >= 0
                for option in fr.get("passOptions", []):
                    assert option["player"] != fr["geometry"]["handler"]
                    assert option["player"] in [p[0] for p in fr["offense"]]
                    assert 0 <= option["turnoverProbability"] <= 1
                    if "route" in option:
                        route = option["route"]
                        assert 0 <= route["immediateReach"] <= route["reachableDefenders"] <= 5
                        assert math.isfinite(route["advantageSeconds"])
                    assert 0 < option["arrivalSeconds"] <= 1.501
                    if option.get("timingModel") == "learned":
                        assert .039 <= option["flightSeconds"] <= 3.001
                        assert abs(option["arrivalSeconds"]-option["flightSeconds"]-.12) < .0011
                    assert option["arrivalSeconds"] < fr["shotClock"] + 0.001
                    assert (
                        abs(
                            option["value"]
                            - (1 - option["turnoverProbability"])
                            * option["completedEpv"]
                        )
                        < 0.0002
                    )
                    assert len(option["offense"]) == len(option["defense"]) == 5
                if "shot" in fr:
                    shot_states += 1
                    shot = fr["shot"]
                    assert 0 <= shot["makeProbability"] <= 1
                    assert (
                        abs(
                            shot["fieldGoalValue"]
                            - shot["makeProbability"] * shot["pointsIfMade"]
                        )
                        < 0.0001
                    )
                    assert shot["shooter"] == fr["geometry"]["handler"]
                    assert (
                        shot["trainingAttempts"]
                        == shot_counts[(shot["shooter"], shot["region"])]
                    )
                    if shot["trainingAttempts"] == 0:
                        assert shot["makeProbability"] == shot["pooledProbability"]
        assert count == entry["supportedFrames"]
assert states == manifest["metrics"]["predictionStates"]
assert plays == manifest["metrics"]["possessions"]
assert (
    len(alignment) > 100 and statistics.median(alignment) < 0.002 and max(alignment) < 5
), (len(alignment), max(alignment))
print(
    f"PASS: {plays} plays, {states} held-out states; all risk bounds and {len(manifest['metrics']['perGame'])} fold records verified."
)
print(
    f"PASS: {len(alignment)} exact-frame shot comparisons validate orientation; median offset {statistics.median(alignment):.6f} ft, maximum {max(alignment):.3f} ft (source alignment noise)."
)

print(
    f"PASS: {shot_states} shooting scenarios have correct player identity, held-out attempt counts, and field-goal values."
)
