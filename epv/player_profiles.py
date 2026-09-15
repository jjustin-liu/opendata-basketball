"""Display-only listed bios and full-sample three-point attempt rates."""

import csv
import json
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def normalized(value):
    return "".join(
        c
        for c in unicodedata.normalize("NFKD", value or "").lower()
        if c.isalnum() and not unicodedata.combining(c)
    )


def main():
    bios = json.loads((ROOT / "data/player_bios_acb.json").read_text())
    by_id = {str(b["acbId"]): b for b in bios}
    by_name = {}
    for b in bios:
        for key in ("name", "fullName"):
            by_name[normalized(b[key])] = b
    aliases = list(csv.DictReader((ROOT / "data/player_id_aliases.csv").open()))
    canonical = {int(a["player_id"]): int(a["canonical_player_id"]) for a in aliases}
    known = {a["canonical_player_id"]: by_id.get(a["acb_player_id"]) for a in aliases}
    positions = {
        "Base": "PG",
        "Escolta": "SG",
        "Alero": "SF",
        "Ala-pívot": "PF",
        "Pívot": "C",
    }
    path = ROOT / "viewer/data/manifest.json"
    manifest = json.loads(path.read_text())
    if "shooting" in manifest.get("metrics", {}):
        manifest["metrics"]["shooting"]["skill"] = (
            "Pooled quality; shooter identity does not adjust make probability."
        )
    counts = {}
    possessions = {}
    matched = set()
    for game in sorted(manifest["games"], key=lambda g: g["match"]["date_time"]):
        for pid, player in game["players"].items():
            bio = known.get(pid) or by_name.get(normalized(player["name"]))
            if bio:
                matched.add(pid)
                player.update(
                    position=positions.get(bio["position"], "?"),
                    heightCm=bio["heightCm"],
                    bioSource=bio["source"],
                )
            player.pop("priorFga", None)
            player.pop("priorThreePa", None)
        gid = game["match"]["id"]
        events = json.loads(
            (ROOT / f"data/matches/{gid}/{gid}_dynamic_events.json").read_text()
        )
        for possession in events["possessions"]:
            for pid in {
                str(canonical.get(pid, pid)) for pid in possession["offPlayerIds"]
            }:
                possessions[pid] = possessions.get(pid, 0) + 1
        game["recordedPasses"] = [
            {
                "possession": p["possessionId"],
                "start": p["startFrame"],
                "end": p["endFrame"],
                "passer": canonical.get(p["passerId"], p["passerId"]),
                "receiver": canonical.get(p.get("receiverId"), p.get("receiverId"))
                if p["complete"]
                else None,
            }
            for p in events["passes"]
            if p.get("endFrame") is not None
        ]
        shots = []
        for s in events["shots"]:
            if s["fouled"] and not s["outcome"]:
                continue
            pid = str(canonical.get(s["shooterId"], s["shooterId"]))
            shots.append(
                {"player": int(pid), "frame": s["endFrame"], "three": bool(s["three"])}
            )
            c = counts.setdefault(pid, [0, 0, 0])
            c[0] += 1
            c[1] += int(s["three"])
            c[2] += int(s["three"] and s["outcome"])
        game["shotAttempts"] = shots
    for game in manifest["games"]:
        for pid, player in game["players"].items():
            player["sampleOffPossessions"] = possessions.get(pid, 0)
            player["sampleFga"], player["sampleThreePa"], player["sampleThreePm"] = (
                counts.get(pid, [0, 0, 0])
            )
    # Prefer the larger season release. Avoid counting TOTAL and team splits twice.
    aggregate_rows = list(
        csv.DictReader(
            (ROOT / "data/aggregates/acb_shotsaggregates_20252026.csv").open()
        )
    )
    groups = {}
    for row in aggregate_rows:
        groups.setdefault(row["player_id"], []).append(row)
    season = {}
    for raw_id, rows in groups.items():
        totals = [r for r in rows if r["team_name"].lower() == "total"]
        pid = str(canonical.get(int(raw_id), int(raw_id)))
        counts_row = season.setdefault(pid, [0, 0, 0, 0])
        for row in totals or rows:
            for i, key in enumerate(
                ["attempts", "three_attempts", "three_mades", "possessions_played"]
            ):
                counts_row[i] += int(float(row[key] or 0))
    for game in manifest["games"]:
        for pid, player in game["players"].items():
            player["shootingSample"] = "10-game tracking sample"
            if pid in season:
                (
                    player["sampleFga"],
                    player["sampleThreePa"],
                    player["sampleThreePm"],
                    player["sampleOffPossessions"],
                ) = season[pid]
                player["shootingSample"] = "293-game season aggregate release"
    path.write_text(json.dumps(manifest, separators=(",", ":")))
    print(
        f"Listed bios matched: {len(matched)} players; 3PR uses the full available game sample."
    )


if __name__ == "__main__":
    main()
