"""Null-controlled, event-aligned change in exploitable space and EPV around actions.

Run: .venv/bin/python -m epv.action_values [--perturb]
  -> artifacts/action-values.json, docs/action-values.md

For every tagged action (pick, drive, off-ball screen, handoff, isolation, pass,
closeout, shot) the signal is averaged over the second before the anchor frame
and the 1.5 s after it, inside the same chance, on frontcourt frames only, with
low-confidence tracking frames dropped. The same statistic on random no-action
frames (at least 1 s from any tagged event) is the null. Coverage splits reuse
the SkillCorner defensive-coverage labels so the deltas can be read per coverage.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from . import space, space_field

ROOT = Path(__file__).resolve().parents[1]
FPS = 25
PRE, POST, PEAK = 25, 38, 75  # frames: 1 s before, 1.5 s after, 3 s peak window
MIN_PRE, MIN_POST = 3, 4  # 5 Hz samples required in each window
SIGNALS = ["space_a", "space_hole", "space_occ", "epv", "turnover2"]
NULL_GAP = 25
NULL_PER_GAME = 400

KINDS = {
    "pick": ("picks", "frame", ["bhrDefType", "scrDefType", "locationType", "direct"]),
    "drive": ("drives", "startFrame", ["category", "blowby", "endType"]),
    "off_ball_screen": ("off_ball_screens", "frame", ["cutterDefType", "screenerDefType", "ledToShot"]),
    "handoff": ("handoffs", "frame", ["locationType", "receiverDefType", "setterDefType"]),
    "isolation": ("isolations", "startFrame", []),
    "pass": ("passes", "startFrame", ["assistOpp", "complete", "distanceBin"]),
    "closeout": ("closeouts", "startFrame", ["bhrAction"]),
    "shot": ("shots", "startFrame", ["contestLevel", "three"]),
}
ANCHOR_TABLES = [("picks", "frame"), ("drives", "startFrame"), ("off_ball_screens", "frame"), ("handoffs", "frame"),
                 ("isolations", "startFrame"), ("passes", "startFrame"), ("closeouts", "startFrame"), ("shots", "startFrame"),
                 ("turnovers", "frame"), ("rebounds", "frame"), ("posts", "startFrame")]


def distance_bin(d):
    if d is None:
        return None
    return "short<15" if d < 15 else ("mid15-30" if d < 30 else "long30+")


class GameSeries:
    """Per-possession arrays for fast window lookups."""

    def __init__(self, table):
        self.blind = space.low_confidence(table).to_numpy()
        self.pos = {}
        t = table.reset_index(drop=True)
        for pid, g in t.groupby("possessionId", sort=False):
            g = g.sort_values("frame")
            self.pos[pid] = {
                "frame": g.frame.to_numpy(),
                "chance": g.chanceId.to_numpy(),
                "front": g.frontcourt.to_numpy(),
                "blind": self.blind[g.index.to_numpy()],
                "signals": {s: g[s].to_numpy(dtype=float) for s in SIGNALS},
            }

    def delta(self, pid, t0):
        p = self.pos.get(pid)
        if p is None:
            return None
        fr = p["frame"]
        i0 = np.searchsorted(fr, t0)
        if i0 >= len(fr) or i0 == 0:
            return None
        chance = p["chance"][min(i0, len(fr) - 1)]
        if chance is None or not p["front"][min(i0, len(fr) - 1)]:
            return None
        ok = (p["chance"] == chance) & ~p["blind"]
        pre = ok & (fr >= t0 - PRE) & (fr < t0)
        post = ok & (fr >= t0) & (fr <= t0 + POST)
        peak = ok & (fr >= t0) & (fr <= t0 + PEAK)
        if pre.sum() < MIN_PRE or post.sum() < MIN_POST:
            return None
        out = {}
        for s, v in p["signals"].items():
            a, b = v[pre], v[post]
            if np.isnan(a).all() or np.isnan(b).all():
                out[s] = {"delta": np.nan, "peak": np.nan, "halfLife": np.nan, "pre": np.nan}
                continue
            base = np.nanmean(a)
            excess = v[peak] - base
            if np.isnan(excess).all():
                pk, hl = np.nan, np.nan
            else:
                j = int(np.nanargmax(excess))
                pk = float(excess[j])
                after = excess[j:]
                below = np.flatnonzero(after < 0.5 * pk) if pk > 0 else np.array([])
                hl = float((fr[peak][j + below[0]] - t0) / FPS) if len(below) else np.nan
            out[s] = {"delta": float(np.nanmean(b) - base), "peak": pk, "halfLife": hl, "pre": float(base)}
        return out


def collect(gid, ev, series):
    rows = []
    anchors = {}
    for kind, (table, field, attrs) in KINDS.items():
        for e in ev[table]:
            pid, t0 = e.get("possessionId"), e.get(field)
            if pid is None or t0 is None:
                continue
            anchors.setdefault(pid, []).append(t0)
            d = series.delta(pid, t0)
            if d is None:
                continue
            row = {"gameId": gid, "kind": kind, "possessionId": pid, "frame": t0}
            for a in attrs:
                row[a] = distance_bin(e.get("distance")) if a == "distanceBin" else e.get(a)
            for s, v in d.items():
                row[f"{s}__delta"], row[f"{s}__peak"], row[f"{s}__half"], row[f"{s}__pre"] = v["delta"], v["peak"], v["halfLife"], v["pre"]
            rows.append(row)
    for table, field in ANCHOR_TABLES:
        for e in ev[table]:
            if e.get("possessionId") and e.get(field) is not None:
                anchors.setdefault(e["possessionId"], []).append(e[field])
    rng = np.random.default_rng(gid)
    cands = []
    for pid, p in series.pos.items():
        an = np.array(sorted(anchors.get(pid, [])))
        for f, front, ch in zip(p["frame"], p["front"], p["chance"]):
            if not front or ch is None:
                continue
            if len(an) and np.abs(an - f).min() < NULL_GAP:
                continue
            cands.append((pid, int(f)))
    for k in rng.permutation(len(cands))[: NULL_PER_GAME * 3]:
        pid, f = cands[k]
        d = series.delta(pid, f)
        if d is None:
            continue
        row = {"gameId": gid, "kind": "null", "possessionId": pid, "frame": f}
        for s, v in d.items():
            row[f"{s}__delta"], row[f"{s}__peak"], row[f"{s}__half"], row[f"{s}__pre"] = v["delta"], v["peak"], v["halfLife"], v["pre"]
        rows.append(row)
        if sum(r["kind"] == "null" and r["gameId"] == gid for r in rows) >= NULL_PER_GAME:
            break
    return rows


def boot_ci(x, draws=1000, seed=0):
    x = x[np.isfinite(x)]
    if len(x) < 2:
        return [None, None]
    rng = np.random.default_rng(seed)
    m = rng.choice(x, size=(draws, len(x)), replace=True).mean(1)
    return [float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))]


def describe(x, null=None):
    x = x[np.isfinite(x)]
    out = {"n": int(len(x)), "mean": float(x.mean()) if len(x) else None, "ci95": boot_ci(x)}
    if null is not None and len(x) >= 5:
        null = null[np.isfinite(null)]
        out["vsNull"] = float(x.mean() - null.mean())
        out["pMannWhitney"] = float(stats.mannwhitneyu(x, null, alternative="two-sided").pvalue)
    return out


def summarize(df):
    null = df[df.kind == "null"]
    report = {"null": {}, "kinds": {}}
    for s in SIGNALS:
        report["null"][s] = {
            "delta": describe(null[f"{s}__delta"].to_numpy()),
            "peak": describe(null[f"{s}__peak"].to_numpy()),
            "pre": describe(null[f"{s}__pre"].to_numpy()),
        }
    for kind, (_, _, attrs) in KINDS.items():
        sub = df[df.kind == kind]
        entry = {"n": int(len(sub)), "signals": {}, "splits": {}}
        for s in SIGNALS:
            entry["signals"][s] = {
                "delta": describe(sub[f"{s}__delta"].to_numpy(), null[f"{s}__delta"].to_numpy()),
                "peak": describe(sub[f"{s}__peak"].to_numpy(), null[f"{s}__peak"].to_numpy()),
                "halfLife": describe(sub[f"{s}__half"].to_numpy()),
                "pre": describe(sub[f"{s}__pre"].to_numpy()),
            }
        for a in attrs:
            if a not in sub:
                continue
            levels = {}
            for level, g in sub.groupby(sub[a].astype(str)):
                if len(g) < 8:
                    continue
                levels[level] = {s: describe(g[f"{s}__delta"].to_numpy(), null[f"{s}__delta"].to_numpy()) for s in SIGNALS}
            if levels:
                entry["splits"][a] = levels
        report["kinds"][kind] = entry
    return report


def perturb(events, tables, kinds=("pick", "drive", "off_ball_screen", "pass", "shot"), resamples=3, seed=0):
    """Recompute space deltas with jittered positions and altered motion constants."""
    from . import space as sp

    maps = space_field.value_maps(events)
    manifest = space_field.manifest()
    variants = {"jitter": None, "v_max-20%": dict(v_max=sp.V_MAX * 0.8), "v_max+20%": dict(v_max=sp.V_MAX * 1.2),
                "a_max-30%": dict(a_max=sp.A_MAX * 0.7), "a_max+30%": dict(a_max=sp.A_MAX * 1.3)}
    baseline = {k: [] for k in kinds}
    out = {v: {k: [] for k in kinds} for v in variants}
    rng = np.random.default_rng(seed)
    for game in manifest["games"]:
        gid = game["match"]["id"]
        ev = events[gid]
        value = maps[gid][0]
        plays = {p["id"]: json.loads((space_field.OUT / f"plays/{p['id']}.json").read_text()) for p in game["plays"]}
        series = GameSeries(tables[gid])
        for kind in kinds:
            table, field, _ = KINDS[kind]
            for e in ev[table]:
                pid, t0 = e.get("possessionId"), e.get(field)
                if pid not in plays or t0 is None:
                    continue
                base = series.delta(pid, t0)
                if base is None:
                    continue
                play = plays[pid]
                frames = play["frames"]
                idx = [i for i, f in enumerate(frames) if t0 - PRE - 5 <= f["frame"] <= t0 + PEAK]
                if not idx:
                    continue
                window = [frames[i] for i in idx]
                lookup = lambda j, idx=idx, frames=frames: frames[idx[j] - 1] if idx[j] > 0 else None
                baseline[kind].append(base["space_a"]["delta"])
                for name, motion in variants.items():
                    deltas = []
                    for r in range(resamples if motion is None else 1):
                        if motion is None:
                            offsets = {}
                            jit = []
                            for f in window:
                                g = dict(f)
                                for side in ("offense", "defense"):
                                    g[side] = [jittered(p, rng, offsets) for p in f[side]]
                                jit.append(g)
                            df = _compute_with(jit, value, lambda j: jit[j - 1] if j > 0 else None, {})
                        else:
                            df = _compute_with(window, value, lookup, motion)
                        fr = np.array([f["frame"] for f in window])
                        pre = (fr >= t0 - PRE) & (fr < t0)
                        post = (fr >= t0) & (fr <= t0 + POST)
                        a = df.space_a.to_numpy()
                        if np.isfinite(a[pre]).sum() >= MIN_PRE and np.isfinite(a[post]).sum() >= MIN_POST:
                            deltas.append(np.nanmean(a[post]) - np.nanmean(a[pre]))
                    out[name][kind].append(float(np.mean(deltas)) if deltas else np.nan)
        print(f"perturbation {gid} done", flush=True)
    report = {}
    for kind in kinds:
        b = np.array(baseline[kind])
        report[kind] = {"n": int(len(b)), "baselineMean": float(np.nanmean(b)) if len(b) else None, "variants": {}}
        for name in variants:
            x = np.array(out[name][kind])
            ok = np.isfinite(x) & np.isfinite(b)
            report[kind]["variants"][name] = {
                "mean": float(x[ok].mean()) if ok.any() else None,
                "corrWithBaseline": float(np.corrcoef(x[ok], b[ok])[0, 1]) if ok.sum() > 2 else None,
                "signAgreement": float((np.sign(x[ok]) == np.sign(b[ok])).mean()) if ok.any() else None,
            }
    return report


def jittered(p, rng, offsets):
    """Player row shifted by a per-player offset drawn once per window from its error bound.

    A constant offset over a 4 s window mimics smooth tracking error and leaves the
    causal velocity estimate intact; independent per-frame noise would not.
    """
    if p[0] not in offsets:
        err = p[4] if len(p) > 4 and p[4] is not None and np.isfinite(p[4]) and p[4] >= 0 else 4.0
        offsets[p[0]] = rng.normal(0, abs(err) / space.ERROR_TO_SD, size=2)  # abs: -0.0 is a rejected scale
    dx, dy = offsets[p[0]]
    return [p[0], p[1] + dx, p[2] + dy] + list(p[3:])


def _compute_with(window, value, lookup, motion):
    """space_a per frame with alternative motion constants."""
    from . import space as sp

    keep = [i for i, f in enumerate(window) if len(f["offense"]) == 5 and len(f["defense"]) == 5]
    a = np.full(len(window), np.nan)
    if keep:
        pos = [sp.positions(window[i], lookup(i)) for i in keep]
        stack = {k: np.stack([p[k] for p in pos]) for k in pos[0]}
        c = sp.control(stack["off_xy"], stack["off_v"], stack["off_pe"], stack["off_det"],
                       stack["def_xy"], stack["def_v"], stack["def_pe"], stack["def_det"], **motion)
        h = c * value[None, :]
        a[keep] = np.maximum(h - sp.TAU, 0).sum(1) * sp.CELL_AREA
    return pd.DataFrame({"space_a": a})


def markdown(report):
    lines = ["# Action values: event-aligned change in exploitable space and EPV", "",
             "Generated by `epv.action_values`. Δ = mean over the 1.5 s after the action minus the mean over the 1 s before, "
             "inside the same chance, frontcourt frames only, low-confidence tracking frames dropped. "
             "`null` is the same statistic on random no-action frames. Space units are point·ft² above the 0.5-point threshold; EPV and turnover are points and probability.", ""]
    lines += ["| kind | n | ΔA | ΔA null-adj | p | Δhole | Δocc | ΔEPV | Δtov2 | peak A | half-life s |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    n0 = report["null"]
    lines.append(f"| null | {n0['space_a']['delta']['n']} | {n0['space_a']['delta']['mean']:+.1f} | – | – | {n0['space_hole']['delta']['mean']:+.1f} | {n0['space_occ']['delta']['mean']:+.1f} | {n0['epv']['delta']['mean']:+.3f} | {n0['turnover2']['delta']['mean']:+.3f} | {n0['space_a']['peak']['mean']:+.1f} | – |")
    for kind, e in report["kinds"].items():
        s = e["signals"]
        f = lambda sig, key="delta", fmt="{:+.1f}": fmt.format(s[sig][key]["mean"]) if s[sig][key]["mean"] is not None else "–"
        hl = s["space_a"]["halfLife"]["mean"]
        lines.append(f"| {kind} | {e['n']} | {f('space_a')} | {s['space_a']['delta'].get('vsNull', float('nan')):+.1f} | {s['space_a']['delta'].get('pMannWhitney', float('nan')):.3g} | {f('space_hole')} | {f('space_occ')} | {f('epv', fmt='{:+.3f}')} | {f('turnover2', fmt='{:+.3f}')} | {f('space_a', 'peak')} | {hl:.2f} |" if hl is not None else
                     f"| {kind} | {e['n']} | {f('space_a')} | – | – | {f('space_hole')} | {f('space_occ')} | {f('epv', fmt='{:+.3f}')} | {f('turnover2', fmt='{:+.3f}')} | {f('space_a', 'peak')} | – |")
    lines += ["", "## Coverage splits", ""]
    for kind, e in report["kinds"].items():
        for attr, levels in e["splits"].items():
            lines.append(f"**{kind} · {attr}**")
            lines.append("")
            lines.append("| level | n | ΔA | 95% CI | ΔA vs null | p | ΔEPV | Δhole |")
            lines.append("|---|---|---|---|---|---|---|---|")
            for level, v in sorted(levels.items(), key=lambda kv: -kv[1]["space_a"]["n"]):
                a = v["space_a"]
                ci = a["ci95"]
                lines.append(f"| {level} | {a['n']} | {a['mean']:+.1f} | [{ci[0]:+.1f}, {ci[1]:+.1f}] | {a.get('vsNull', float('nan')):+.1f} | {a.get('pMannWhitney', float('nan')):.3g} | {v['epv']['mean']:+.3f} | {v['space_hole']['mean']:+.1f} |" if ci[0] is not None and v['epv']['mean'] is not None else f"| {level} | {a['n']} | – | – | – | – | – | – |")
            lines.append("")
    if "perturbation" in report:
        lines += ["## Robustness", "", "Space deltas recomputed with positions jittered by the SkillCorner error bound (3 draws) and with motion constants varied.", "",
                  "| kind | n | baseline ΔA | variant | mean ΔA | corr | sign agreement |", "|---|---|---|---|---|---|---|"]
        for kind, e in report["perturbation"].items():
            for name, v in e["variants"].items():
                if v["mean"] is None:
                    continue
                lines.append(f"| {kind} | {e['n']} | {e['baselineMean']:+.1f} | {name} | {v['mean']:+.1f} | {v['corrWithBaseline']:.3f} | {v['signAgreement']:.2f} |")
    lines += ["", "Caveats: ten games; velocities are causal (previous replay sample only); the value map scores open-shot points, not the ball; "
              "changes after passes and shots partly reflect the ball moving to another region and the chance ending. Not a causal estimate of action quality."]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--perturb", action="store_true")
    args = parser.parse_args()
    events = space_field.load_events()
    tables = {gid: space_field.load_game(gid, events) for gid in events}
    rows = []
    for gid, ev in events.items():
        rows += collect(gid, ev, GameSeries(tables[gid]))
        print(f"{gid}: {sum(r['gameId'] == gid for r in rows)} aligned rows", flush=True)
    df = pd.DataFrame(rows)
    report = summarize(df)
    report["counts"] = df.kind.value_counts().to_dict()
    report["windows"] = {"preSeconds": PRE / FPS, "postSeconds": POST / FPS, "peakSeconds": PEAK / FPS, "nullGapSeconds": NULL_GAP / FPS}
    if args.perturb:
        report["perturbation"] = perturb(events, tables)
    (ROOT / "artifacts").mkdir(exist_ok=True)
    (ROOT / "artifacts/action-values.json").write_text(json.dumps(report, indent=2, allow_nan=True))
    df.to_pickle(ROOT / "artifacts/action-values-rows.pkl")
    (ROOT / "docs/action-values.md").write_text(markdown(report))
    for kind, e in report["kinds"].items():
        a = e["signals"]["space_a"]["delta"]
        print(f"{kind:16s} n={e['n']:4d} dA={a['mean']:+7.1f} vsNull={a.get('vsNull', float('nan')):+7.1f} p={a.get('pMannWhitney', float('nan')):.3g} dEPV={e['signals']['epv']['delta']['mean']:+.3f}", flush=True)


if __name__ == "__main__":
    main()
