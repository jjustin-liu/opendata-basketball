"""Exploitable-space field: P(offense reaches q first) x value of an open shot from q.

Ported from Luke Blommesteyn's `spaceholes` analysis of this same release
(https://github.com/lblommesteyn/opendata-basketball, MIT), with two deliberate
changes: velocities are causal (previous replay sample only, never a centred
difference), and the geometry matches this repository's hoop and arc constants.

Coordinates: replay frames already attack negative x, hoop at (-40.75, 0).
Player rows are [id, x, y, isDetected, predError, jersey].
"""

from __future__ import annotations

import numpy as np
from scipy import ndimage
from scipy.special import ndtr

from .shooting import ARC_FT, CORNER_FT

HOOP = np.array([-40.75, 0.0])
HALF_LENGTH = 45.932
HALF_WIDTH = 24.606

# Movement model. Fitted percentiles from detected 25 Hz tracking across the ten
# games are in artifacts/movement-constants.json (scripts/fit_movement_constants.py):
# 99.9th percentile speed ~21 ft/s, 99th percentile acceleration ~14-20 ft/s^2
# depending on smoothing. Blommesteyn's robustness table shows the action
# ranking is insensitive to +-30% changes in either.
V_MAX = 20.0  # ft/s
A_MAX = 16.0  # ft/s^2
REACTION = 0.2  # s before a player can change motion
SIGMA_T0 = 0.15  # s irreducible arrival-time noise
V_REF = 10.0  # ft/s converts positional error to time
KAPPA_T = 0.10  # arrival-time noise grows with arrival time
EXTRAP_INFLATE = 1.5  # extrapolated positions carry more error
ERROR_TO_SD = 2.146  # predError is a 90% radial bound; isotropic Gaussian sd

TAU = 0.5  # points threshold for "exploitable"
OCCUPIED_RADIUS = 5.0  # ft: space this close to an attacker is "occupied"
MIN_HOLE_CELLS = 6

GRID_X = np.arange(-HALF_LENGTH + 0.5, 0.0, 1.0)  # baseline .. half court
GRID_Y = np.arange(-24.0 + 0.5, 24.0, 1.0)
GX, GY = np.meshgrid(GRID_X, GRID_Y, indexing="ij")
GRID = np.stack([GX.ravel(), GY.ravel()], axis=1).astype(np.float32)
NX, NY = len(GRID_X), len(GRID_Y)
CELL_AREA = 1.0


def rim_distance(q):
    return np.hypot(q[:, 0] - HOOP[0], q[:, 1] - HOOP[1])


def is_three(q):
    return (rim_distance(q) > ARC_FT) | (np.abs(q[:, 1]) > CORNER_FT)


_R = rim_distance(GRID)
NEAR_RIM = _R <= 8.0
THREE = is_three(GRID) & (_R <= 30)
CORNER = (np.abs(GRID[:, 1]) >= CORNER_FT - 3) & (GRID[:, 0] <= HOOP[0] + 8)
PAINT = (np.abs(GRID[:, 1]) <= 8.04) & (GRID[:, 0] <= -HALF_LENGTH + 19.03)


def value_geometric(q=GRID):
    """Parametric expected points of an open shot from q (prior for the empirical map)."""
    r = rim_distance(q)
    two = 1.35 - 0.5 * np.clip(r / 15.0, 0, 1)
    three = 1.05 - 0.70 * np.clip((r - ARC_FT) / 13.0, 0, 1)
    v = np.where(is_three(q), three, two)
    v = np.where(r > 40.0, 0.05, v)
    return np.where(q[:, 0] > 0, 0.0, v).astype(np.float32)


def fit_value_map(shots, q=GRID, bandwidth=4.0, prior_weight=6.0, mirror=True):
    """Kernel-smoothed points of open/light shots, shrunk to value_geometric.

    shots: DataFrame with x, y, points (0 or 2/3). Value transfers only within the
    same 2/3-point zone. Returns (V, effective sample count) per cell.
    """
    loc = shots[["x", "y"]].to_numpy(dtype=float)
    pts = shots["points"].to_numpy(dtype=float)
    if mirror:
        loc = np.vstack([loc, loc * np.array([1, -1])])
        pts = np.concatenate([pts, pts])
    if len(loc) == 0:
        return value_geometric(q), np.zeros(len(q), dtype=np.float32)
    d2 = ((q[:, None, :] - loc[None, :, :]) ** 2).sum(-1)
    w = np.exp(-0.5 * d2 / bandwidth**2)
    w = w * (is_three(q)[:, None] == is_three(loc)[None, :])
    n_eff = w.sum(1)
    prior = value_geometric(q)
    v = (w @ pts + prior_weight * prior) / (n_eff + prior_weight)
    v = np.where(q[:, 0] > 0, 0.0, v)
    return v.astype(np.float32), n_eff.astype(np.float32)


def open_shots(events, game_ids=None):
    """Rows (gameId, x, y, points) of open/light, non-fouled-miss shots."""
    import pandas as pd

    rows = []
    for gid, ev in events.items():
        if game_ids is not None and gid not in game_ids:
            continue
        for s in ev["shots"]:
            if s.get("location") is None or s.get("contestLevel") not in ("open", "light"):
                continue
            points = (3 if s["three"] else 2) * int(bool(s["outcome"]))
            rows.append({"gameId": gid, "x": s["location"][0], "y": s["location"][1], "points": points})
    return pd.DataFrame(rows, columns=["gameId", "x", "y", "points"])


def tta_kinematic(p, v, q=GRID, v_max=V_MAX, a_max=A_MAX, reaction=REACTION):
    """Arrival times (m, k, n): drift for `reaction`, then bang-bang toward q."""
    p1 = p + v * reaction
    diff = q[None, None, :, :] - p1[:, :, None, :]
    d = np.linalg.norm(diff, axis=-1)
    u = diff / np.maximum(d, 1e-6)[..., None]
    s0 = np.clip(np.einsum("mknd,mkd->mkn", u, v), -v_max, v_max)
    neg = s0 < 0
    t_stop = np.where(neg, -s0 / a_max, 0.0)
    d_eff = d + np.where(neg, s0 * s0 / (2 * a_max), 0.0)
    s0p = np.where(neg, 0.0, s0)
    d_acc = (v_max * v_max - s0p * s0p) / (2 * a_max)
    t_short = (-s0p + np.sqrt(s0p * s0p + 2 * a_max * d_eff)) / a_max
    t_long = (v_max - s0p) / a_max + (d_eff - d_acc) / v_max
    return reaction + t_stop + np.where(d_eff <= d_acc, t_short, t_long)


def tta_sigma(t_mean, pred_error, detected, sigma0=SIGMA_T0, v_ref=V_REF, kappa=KAPPA_T, inflate=EXTRAP_INFLATE):
    pe = np.asarray(pred_error, dtype=np.float32) / ERROR_TO_SD
    pe = np.where(np.asarray(detected) == 1, pe, pe * inflate)
    s_pos = (pe / v_ref)[:, :, None]
    return np.sqrt(sigma0**2 + s_pos**2 + (kappa * t_mean) ** 2)


def clark_min(mu, sd):
    """Clark (1961) moment matching for min_i of independent normals. (m,k,n) -> (m,n)."""
    m1, s1 = mu[:, 0, :], sd[:, 0, :]
    for i in range(1, mu.shape[1]):
        m2, s2 = mu[:, i, :], sd[:, i, :]
        a = np.sqrt(s1 * s1 + s2 * s2) + 1e-6
        alpha = (m1 - m2) / a
        phi = np.exp(-0.5 * alpha * alpha) / np.sqrt(2 * np.pi)
        big_phi = ndtr(alpha)
        mmin = m1 * (1 - big_phi) + m2 * big_phi - a * phi
        m2nd = (m1 * m1 + s1 * s1) * (1 - big_phi) + (m2 * m2 + s2 * s2) * big_phi - (m1 + m2) * a * phi
        s1 = np.sqrt(np.maximum(m2nd - mmin * mmin, 1e-8))
        m1 = mmin
    return m1, s1


def control(off_p, off_v, off_pe, off_det, def_p, def_v, def_pe, def_det, q=GRID, **motion):
    """P(min offensive arrival < min defensive arrival) per cell, (m, n)."""
    mu_o = tta_kinematic(off_p, off_v, q, **motion)
    mu_d = tta_kinematic(def_p, def_v, q, **motion)
    mo, so = clark_min(mu_o, tta_sigma(mu_o, off_pe, off_det))
    md, sd = clark_min(mu_d, tta_sigma(mu_d, def_pe, def_det))
    return ndtr((md - mo) / np.sqrt(so * so + sd * sd)).astype(np.float32)


def control_monte_carlo(off_p, off_v, off_pe, off_det, def_p, def_v, def_pe, def_det, q=GRID, draws=400, seed=0):
    """Sampling check for clark_min; not used in the pipeline."""
    rng = np.random.default_rng(seed)
    mu_o = tta_kinematic(off_p, off_v, q)
    mu_d = tta_kinematic(def_p, def_v, q)
    so = tta_sigma(mu_o, off_pe, off_det)
    sd = tta_sigma(mu_d, def_pe, def_det)
    wins = np.zeros(mu_o.shape[::2], dtype=np.float32)
    for _ in range(draws):
        to = (mu_o + so * rng.standard_normal(mu_o.shape)).min(1)
        td = (mu_d + sd * rng.standard_normal(mu_d.shape)).min(1)
        wins += to < td
    return wins / draws


def to_grid(h):
    return h.reshape(NX, NY)


def summaries(h, off_xy):
    """Scalar summaries of a batch of fields h (m, n). off_xy (m, 5, 2)."""
    out = {}
    hp = np.maximum(h - TAU, 0)
    dmin = np.linalg.norm(GRID[None, None, :, :] - off_xy[:, :, None, :], axis=-1).min(1)
    near = dmin < OCCUPIED_RADIUS
    out["space_total"] = h.sum(1) * CELL_AREA
    out["space_a"] = hp.sum(1) * CELL_AREA
    out["space_occ"] = (hp * near).sum(1) * CELL_AREA
    out["space_hole"] = (hp * ~near).sum(1) * CELL_AREA
    out["space_hole_rim"] = (hp * ~near * NEAR_RIM[None, :]).sum(1) * CELL_AREA
    out["space_max"] = h.max(1)
    out["space_rim"] = h[:, NEAR_RIM].sum(1) * CELL_AREA
    out["space_corner"] = h[:, CORNER].sum(1) * CELL_AREA
    out["space_three"] = h[:, THREE].sum(1) * CELL_AREA
    out["space_paint"] = h[:, PAINT].sum(1) * CELL_AREA
    cc = np.zeros(len(h), dtype=np.float32)
    ncomp = np.zeros(len(h), dtype=np.int16)
    for i in range(len(h)):
        g = to_grid(hp[i])
        lab, n = ndimage.label(g > 0)
        ncomp[i] = n
        if n:
            cc[i] = ndimage.sum(g, lab, index=np.arange(1, n + 1)).max() * CELL_AREA
    out["space_cc"] = cc
    out["space_holes"] = ncomp
    return out


SPACE_FEATURES = [
    "space_a",
    "space_hole",
    "space_occ",
    "space_hole_rim",
    "space_rim",
    "space_corner",
    "space_three",
    "space_paint",
    "space_cc",
    "space_holes",
    "space_max",
    "space_total",
    "control_area",
]


def holes(h, off_xy, tau=TAU, occupied_radius=OCCUPIED_RADIUS, min_cells=MIN_HOLE_CELLS):
    """Connected valuable regions no attacker occupies: list of (cx, cy, mass, cells)."""
    dmin = np.linalg.norm(GRID - off_xy[:, None, :], axis=-1).min(0)
    g = to_grid((h > tau) & (dmin >= occupied_radius))
    lab, n = ndimage.label(g)
    out = []
    hg = to_grid(np.maximum(h - tau, 0))
    for label in range(1, n + 1):
        mask = lab == label
        cells = int(mask.sum())
        if cells < min_cells:
            continue
        cx, cy = ndimage.center_of_mass(mask)
        out.append((float(GRID_X[0] + cx), float(GRID_Y[0] + cy), float((hg * mask).sum()), cells))
    return out


def positions(frame, previous=None, max_dt=0.4):
    """Attack-frame arrays for one replay frame with causal velocities."""
    off = np.array([[p[1], p[2]] for p in frame["offense"]], dtype=np.float32)
    de = np.array([[p[1], p[2]] for p in frame["defense"]], dtype=np.float32)
    off_v = np.zeros_like(off)
    def_v = np.zeros_like(de)
    dt = (frame["frame"] - previous["frame"]) / 25 if previous else 0.0
    if previous and 0 < dt <= max_dt and previous.get("period") == frame.get("period"):
        old = {p[0]: np.array(p[1:3], dtype=np.float32) for p in previous["offense"] + previous["defense"]}
        for arr, vel in ((frame["offense"], off_v), (frame["defense"], def_v)):
            for i, p in enumerate(arr):
                if p[0] in old:
                    vel[i] = (np.array(p[1:3], dtype=np.float32) - old[p[0]]) / dt
    return dict(
        off_xy=off,
        def_xy=de,
        off_v=off_v,
        def_v=def_v,
        off_pe=np.array([p[4] for p in frame["offense"]], dtype=np.float32),
        def_pe=np.array([p[4] for p in frame["defense"]], dtype=np.float32),
        off_det=np.array([p[3] for p in frame["offense"]], dtype=np.int8),
        def_det=np.array([p[3] for p in frame["defense"]], dtype=np.int8),
    )


def compute_frames(frames, value, batch=64, store_fields=False, previous_lookup=None):
    """Field summaries for a list of replay frames (same play, in order).

    Returns (DataFrame of summaries aligned to `frames`, optional list of h fields).
    Frames without ten players get NaN rows.
    """
    import pandas as pd

    keep = [i for i, f in enumerate(frames) if len(f["offense"]) == 5 and len(f["defense"]) == 5]
    recs = {k: np.full(len(frames), np.nan, dtype=np.float32) for k in SPACE_FEATURES + ["n_extrap", "mean_error"]}
    fields = [None] * len(frames) if store_fields else None
    for b0 in range(0, len(keep), batch):
        idx = keep[b0 : b0 + batch]
        pos = [
            positions(
                frames[i],
                previous_lookup(i) if previous_lookup else (frames[i - 1] if i > 0 else None),
            )
            for i in idx
        ]
        stack = {k: np.stack([p[k] for p in pos]) for k in pos[0]}
        c = control(
            stack["off_xy"], stack["off_v"], stack["off_pe"], stack["off_det"],
            stack["def_xy"], stack["def_v"], stack["def_pe"], stack["def_det"],
        )
        h = c * value[None, :]
        s = summaries(h, stack["off_xy"])
        s["control_area"] = c.sum(1) * CELL_AREA
        s["n_extrap"] = 10 - stack["off_det"].sum(1) - stack["def_det"].sum(1)
        s["mean_error"] = (stack["off_pe"].mean(1) + stack["def_pe"].mean(1)) / 2
        for k, v in s.items():
            recs[k][idx] = v
        if store_fields:
            for j, i in enumerate(idx):
                fields[i] = h[j]
    return pd.DataFrame(recs), fields


def low_confidence(table, max_extrap=8, max_error=4.0):
    """Frames where tracking is essentially blind; control collapses to 0.5 there."""
    return (table["n_extrap"] >= max_extrap) | (table["mean_error"] > max_error)
