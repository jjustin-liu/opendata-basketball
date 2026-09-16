"""Leave-one-game-out test: do exploitable-space features add to our EPV geometry?

Run: .venv/bin/python -m epv.space_eval  ->  artifacts/space-validation.json

Rows are the EPV training states (artifacts/states.pkl, train flag = every other
row, per-possession equal weights) joined to the cached space summaries from
epv.space_field. Targets are the three EPV targets plus five short-horizon heads
(next 3 s) built from the SkillCorner event tables inside the same possession.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from . import space, space_field
from .build import estimator, prediction, score, weights
from .features import BASE_FEATURES, EPV_GEOMETRY_FEATURES, FEATURES

ROOT = Path(__file__).resolve().parents[1]
HORIZON = 75  # 25 Hz frames = 3 s
SHORT_TARGETS = ["shot_3s", "open_shot_3s", "rim_shot_3s", "paint_touch_3s", "assist_opp_3s"]
EPV_TARGETS = ["points", "turnover2", "turnover_rest"]


def event_frames(ev):
    """Per possession: sorted event frames for each short-horizon target."""
    out = {t: {} for t in SHORT_TARGETS}

    def add(target, pid, frame):
        if pid is not None and frame is not None:
            out[target].setdefault(pid, []).append(frame)

    for s in ev["shots"]:
        add("shot_3s", s.get("possessionId"), s.get("startFrame"))
        if s.get("contestLevel") in ("open", "light"):
            add("open_shot_3s", s.get("possessionId"), s.get("startFrame"))
        if s.get("distance") is not None and s["distance"] <= 6.0:
            add("rim_shot_3s", s.get("possessionId"), s.get("startFrame"))
    for t in ev["touches"]:
        if any(r in ("ra", "key") for r in (t.get("regionsIn") or [])):
            add("paint_touch_3s", t.get("possessionId"), t.get("startFrame"))
    for p in ev["passes"]:
        if p.get("assistOpp"):
            add("assist_opp_3s", p.get("possessionId"), p.get("startFrame"))
    return {t: {pid: np.array(sorted(v)) for pid, v in d.items()} for t, d in out.items()}


def short_targets(table, events):
    cols = {t: np.zeros(len(table), dtype=int) for t in SHORT_TARGETS}
    for gid, ev in events.items():
        idx = np.flatnonzero(table.gameId.to_numpy() == gid)
        frames = event_frames(ev)
        pids = table.possessionId.to_numpy()[idx]
        fr = table.frame.to_numpy()[idx]
        for t in SHORT_TARGETS:
            hit = np.zeros(len(idx), dtype=int)
            for pid in np.unique(pids):
                ef = frames[t].get(pid)
                if ef is None:
                    continue
                m = pids == pid
                nxt = np.searchsorted(ef, fr[m], side="left")
                has = nxt < len(ef)
                delta = np.where(has, ef[np.minimum(nxt, len(ef) - 1)] - fr[m], np.inf)
                hit[m] = (delta <= HORIZON).astype(int)
            cols[t][idx] = hit
    return pd.DataFrame(cols, index=table.index)


def assemble():
    states = pd.read_pickle(ROOT / "artifacts/states.pkl")
    events = space_field.load_events()
    parts = []
    for gid in sorted(states.gameId.unique()):
        t = space_field.load_game(int(gid), events)
        parts.append(t[["possessionId", "frame"] + space.SPACE_FEATURES + ["n_extrap", "mean_error", "frontcourt"]])
    joined = states.merge(pd.concat(parts, ignore_index=True), on=["possessionId", "frame"], how="left")
    assert len(joined) == len(states)
    joined = pd.concat([joined, short_targets(joined, events)], axis=1)
    return joined


def feature_sets(target):
    geometry = EPV_GEOMETRY_FEATURES if target == "points" else FEATURES
    sets = {
        "geometry": geometry,
        "geometry_space": geometry + space.SPACE_FEATURES,
        "clock_space": BASE_FEATURES + space.SPACE_FEATURES,
    }
    if target in SHORT_TARGETS:
        sets["clock_location"] = BASE_FEATURES
    return sets


def logo(table, targets):
    """Pooled held-out predictions for every target x feature set, per game."""
    table = table[table.train & table.space_a.notna()].reset_index(drop=True)
    rows = []
    pooled = {}
    for gid in sorted(table.gameId.unique()):
        train = table[table.gameId != gid]
        test = table[table.gameId == gid]
        tw, vw = weights(train), weights(test)
        print(f"held-out {gid}: {len(train)} train, {len(test)} test", flush=True)
        for target in targets:
            kind = "points" if target == "points" else "binary"
            for name, columns in feature_sets(target).items():
                model = estimator(kind)
                model.fit(train[columns], train[target], sample_weight=tw)
                pred = prediction(model, test[columns], kind)
                rows.append({"gameId": int(gid), "target": target, "model": name, "n": len(test), **score(test[target], pred, kind, vw)})
                pooled.setdefault((target, name), []).append((test[target].to_numpy(), pred, vw))
    per_game = pd.DataFrame(rows)
    summary = {}
    for (target, name), parts in pooled.items():
        y = np.concatenate([p[0] for p in parts])
        p = np.concatenate([p[1] for p in parts])
        w = np.concatenate([p[2] for p in parts])
        kind = "points" if target == "points" else "binary"
        summary.setdefault(target, {})[name] = {**score(y, p, kind, w), "rate": float(np.average(y, weights=w))}
    return per_game, summary


def paired(per_game, target, metric, a="geometry_space", b="geometry"):
    x = per_game[(per_game.target == target)].pivot(index="gameId", columns="model", values=metric)
    if a not in x or b not in x:
        return None
    d = (x[a] - x[b]).dropna()
    return {"meanDelta": float(d.mean()), "gamesImproved": int((d < 0).sum()), "games": int(len(d)), "sd": float(d.std(ddof=1)) if len(d) > 1 else None}


def main():
    table = assemble()
    targets = EPV_TARGETS + SHORT_TARGETS
    with threadpool_limits(limits=4):
        per_game, summary = logo(table, targets)
    report = {
        "rows": int((table.train & table.space_a.notna()).sum()),
        "features": space.SPACE_FEATURES,
        "horizonSeconds": HORIZON / 25,
        "targetRates": {t: float(table[t].mean()) for t in SHORT_TARGETS},
        "summary": summary,
        "paired": {
            t: {
                "geometry_space_vs_geometry": paired(per_game, t, "rmse" if t == "points" else "logLoss"),
                "clock_space_vs_geometry": paired(per_game, t, "rmse" if t == "points" else "logLoss", "clock_space", "geometry"),
            }
            for t in targets
        },
        "perGame": per_game.to_dict(orient="records"),
        "note": "Same estimator, weights and leave-one-game-out split as the EPV build. Lower is better; paired deltas are held-out-game differences (model a minus model b).",
    }
    (ROOT / "artifacts/space-validation.json").write_text(json.dumps(report, indent=2))
    for t in targets:
        m = "rmse" if t == "points" else "logLoss"
        line = "  ".join(f"{n}={v[m]:.4f}" for n, v in summary[t].items())
        print(f"{t:16s} {line}", flush=True)


if __name__ == "__main__":
    main()
