import json
import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

r = json.load(open("artifacts/vendor_quality_check.json"))
fig, axes = plt.subplots(1, 2, figsize=(10, 4), layout="constrained")
for ax, group, title in zip(
    axes, ["all", "3PT"], ["All scored attempts (n=1,433)", "Three-pointers (n=519)"]
):
    b = [b for b in r["bands"] if b["group"] == group]
    n = np.array([x["n"] for x in b])
    p = np.array([x["makeRate"] for x in b])
    x = np.array([x["scoreMean"] for x in b])
    z = 1.96
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    rad = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    ax.plot([0, 100], [0, 100], ls="--", color="#9aa5ac", lw=1)
    ax.errorbar(
        x * 100,
        p * 100,
        yerr=np.array([p - c + rad, c + rad - p]) * 100,
        fmt="o",
        color="#138477",
        capsize=3,
    )
    ax.set(
        xlim=(0, 100),
        ylim=(0, 100),
        xlabel="Mean SkillCorner SQ",
        ylabel="Observed make rate (%)",
        title=title,
    )
    ax.grid(alpha=0.15)
fig.suptitle("SkillCorner SQ behaves like a make probability", fontsize=14)
fig.savefig("artifacts/vendor_quality_calibration.png", dpi=150)
