"""Empirical interpretation check; this cannot establish vendor score semantics."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, log_loss

ROOT = Path(__file__).resolve().parents[1]
rows = [
    s
    for p in (ROOT / "data/matches").glob("*/*_dynamic_events.json")
    for s in json.loads(p.read_text())["shots"]
]
d = pd.DataFrame(rows)
d = d[d.shotQuality.notna()].copy()
d["p"] = d.shotQuality / 100


def summary(g):
    p = g.p.to_numpy()
    y = g.outcome.astype(int).to_numpy()
    return {
        "n": len(g),
        "scoreMean": round(float(p.mean()), 4),
        "makeRate": round(float(y.mean()), 4),
        "brier": round(brier_score_loss(y, p), 4),
        "logLoss": round(log_loss(y, np.clip(p, 1e-9, 1 - 1e-9), labels=[0, 1]), 4),
        "scoreMin": float(g.shotQuality.min()),
        "scoreMax": float(g.shotQuality.max()),
    }


result = {
    "all": summary(d),
    "missing": len(rows) - len(d),
    "subsets": {},
    "bands": [],
    "games": [],
}
for label, g in [
    ("2PT", d[~d.three]),
    ("3PT", d[d.three]),
    ("notFouled", d[~d.fouled]),
    ("fouled", d[d.fouled]),
    ("blocked", d[d.blocked]),
]:
    result["subsets"][label] = summary(g)
for label, g in [("all", d), ("2PT", d[~d.three]), ("3PT", d[d.three])]:
    for lo in range(0, 100, 10):
        band = g[
            (g.shotQuality >= lo) & (g.shotQuality < (lo + 10 if lo < 90 else 100.001))
        ]
        if len(band):
            result["bands"].append(
                dict(group=label, band=f"{lo}-{lo + 10}", **summary(band))
            )
for gid, g in d.groupby("gameId"):
    result["games"].append(dict(gameId=int(gid), **summary(g)))
# Compare interpretation to training-game 2PT/3PT base rates, without fitting the score.
base = []
actual = []
probs = []
for gid, g in d.groupby("gameId"):
    train = d[d.gameId != gid]
    rates = train.groupby("three").outcome.mean()
    base.extend(g.three.map(rates))
    actual.extend(g.outcome.astype(int))
    probs.extend(g.p)
result["heldOutTypeBaseline"] = {
    "brier": brier_score_loss(actual, base),
    "logLoss": log_loss(actual, base),
}
# Cluster bootstrap of average calibration gap to respect within-game dependence.
rng = np.random.default_rng(42)
groups = [g for _, g in d.groupby("gameId")]
sums = np.array([(g.p - g.outcome.astype(int)).sum() for g in groups])
ns = np.array([len(g) for g in groups])
ix = rng.integers(0, len(groups), (10000, len(groups)))
gap = sums[ix].sum(axis=1) / ns[ix].sum(axis=1)
result["calibrationGapGameBootstrap95"] = np.quantile(gap, [0.025, 0.975]).tolist()
(ROOT / "artifacts/vendor_quality_check.json").write_text(json.dumps(result, indent=2))
print(json.dumps(result, indent=2))
