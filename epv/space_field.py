"""Per-game exploitable-space fields: cache summaries, export value maps and holes.

Run: .venv/bin/python -m epv.space_field [--game GID] [--no-export]

Outputs
  .cache/epv/space-{gid}-{version}.joblib   per-frame summaries for every replay frame
  viewer/data/space-value.json              leave-one-game-out open-shot value grids
  viewer/data/holes/{gid}.json              empty valuable regions per supported frame
  viewer/data/plays/*.json                  frame['space'] = {a, hole, occ} (rounded)
"""

from __future__ import annotations

import argparse
import hashlib
import json
from bisect import bisect_right
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from . import space

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache/epv"
OUT = ROOT / "viewer/data"
VERSION = hashlib.sha256((ROOT / "epv/space.py").read_bytes()).hexdigest()[:10]


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, separators=(",", ":"), allow_nan=False))


def load_events(root=ROOT):
    out = {}
    for path in sorted((root / "data/matches").glob("*/*_dynamic_events.json")):
        gid = int(path.parent.name)
        out[gid] = json.loads(path.read_text())
    return out


def manifest(root=ROOT):
    return json.loads((root / "viewer/data/manifest.json").read_text())


def value_maps(events):
    """Leave-one-game-out empirical open-shot value per game, plus training counts."""
    shots = space.open_shots(events)
    maps = {}
    for gid in events:
        train = shots[shots.gameId != gid]
        v, n_eff = space.fit_value_map(train)
        maps[gid] = (v, len(train))
    return maps


class ChanceIndex:
    def __init__(self, chances):
        self.chances = sorted([c for c in chances if c["startFrame"] < c["endFrame"]], key=lambda c: c["startFrame"])
        self.starts = [c["startFrame"] for c in self.chances]

    def at(self, frame):
        i = bisect_right(self.starts, frame) - 1
        if i < 0 or frame >= self.chances[i]["endFrame"]:
            return None
        return self.chances[i]


def game_table(gid, plays, value, chances):
    """Summaries for every replay frame of a game, aligned with play frames."""
    index = ChanceIndex(chances)
    parts = []
    for play in plays:
        df, _ = space.compute_frames(play["frames"], value)
        df.insert(0, "frameIndex", np.arange(len(play["frames"])))
        df.insert(0, "frame", [f["frame"] for f in play["frames"]])
        df.insert(0, "possessionId", play["id"])
        df.insert(0, "gameId", gid)
        meta = [index.at(f["frame"]) for f in play["frames"]]
        df["chanceId"] = [c["id"] if c else None for c in meta]
        df["frontcourt"] = [
            bool(c and c.get("frontcourtFrame") is not None and f["frame"] >= c["frontcourtFrame"])
            for c, f in zip(meta, play["frames"])
        ]
        df["supported"] = [("epv" in f) for f in play["frames"]]
        df["epv"] = [f.get("epv", np.nan) for f in play["frames"]]
        df["turnover2"] = [f.get("turnover2", np.nan) for f in play["frames"]]
        df["shotClock"] = [f.get("shotClock") if f.get("shotClock") is not None else np.nan for f in play["frames"]]
        parts.append(df)
    return pd.concat(parts, ignore_index=True)


def load_game(gid, events=None, plays=None, rebuild=False):
    """Cached per-frame table for a game (computes if missing)."""
    path = CACHE / f"space-{gid}-{VERSION}.joblib"
    if path.exists() and not rebuild:
        return joblib.load(path)
    events = events or load_events()
    if plays is None:
        game = next(g for g in manifest()["games"] if g["match"]["id"] == gid)
        plays = [json.loads((OUT / f"plays/{p['id']}.json").read_text()) for p in game["plays"]]
    value, _ = value_maps(events)[gid]
    table = game_table(gid, plays, value, events[gid]["chances"])
    CACHE.mkdir(parents=True, exist_ok=True)
    joblib.dump(table, path, compress=3)
    return table


def export_value_grid(maps):
    grid = {}
    for gid, (v, n) in maps.items():
        cells = [
            [int(round(x - 0.5)), int(round(y - 0.5)), round(float(val), 3)]
            for (x, y), val in zip(space.GRID, v)
            if x < 0 and val > 0
        ]
        grid[str(gid)] = {"cells": cells, "trainingShots": int(n), "method": "open/light shots, other games, kernel 4 ft, prior weight 6, mirrored"}
    dump(OUT / "space-value.json", grid)


def export_game(gid, plays, value, table):
    """Write frame['space'] into play JSON and a holes file for movement candidates."""
    holes_out = {}
    by_play = {p["id"]: p for p in plays}
    rows = table.set_index(["possessionId", "frameIndex"])
    for pid, play in by_play.items():
        _, fields = space.compute_frames(play["frames"], value, store_fields=True)
        for i, f in enumerate(play["frames"]):
            r = rows.loc[(pid, i)]
            if not np.isfinite(r["space_a"]):
                f.pop("space", None)
                continue
            f["space"] = {"a": round(float(r["space_a"]), 1), "hole": round(float(r["space_hole"]), 1), "occ": round(float(r["space_occ"]), 1)}
            if f.get("reason") or not f.get("geometry", {}).get("handler") or (f.get("shotClock") or 0) < 3:
                continue
            off = np.array([[p[1], p[2]] for p in f["offense"]], dtype=np.float32)
            hs = space.holes(fields[i], off)
            if hs:
                holes_out.setdefault(pid, {})[str(f["frame"])] = [[round(cx, 1), round(cy, 1), round(m, 1), n] for cx, cy, m, n in hs]
        dump(OUT / f"plays/{pid}.json", play)
    dump(OUT / f"holes/{gid}.json", {"version": 1, "plays": holes_out, "note": "Connected regions of control x open-shot value above 0.5 pts, at least 5 ft from every attacker; [cx, cy, mass, cells]."})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--game", type=int)
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--no-export", action="store_true")
    args = parser.parse_args()
    events = load_events()
    maps = value_maps(events)
    if not args.no_export:
        export_value_grid(maps)
    for game in manifest()["games"]:
        gid = game["match"]["id"]
        if args.game and gid != args.game:
            continue
        plays = [json.loads((OUT / f"plays/{p['id']}.json").read_text()) for p in game["plays"]]
        table = load_game(gid, events, plays, rebuild=args.rebuild)
        if not args.no_export:
            export_game(gid, plays, maps[gid][0], table)
        blind = space.low_confidence(table).mean()
        print(f"{gid}: {len(table)} frames, mean A={table.space_a.mean():.1f}, blind={blind:.3f}", flush=True)


if __name__ == "__main__":
    main()
