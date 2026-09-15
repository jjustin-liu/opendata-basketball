"""Causal spatial features. Coordinates normalized so offense attacks negative x."""

import math
import numpy as np

# Matches SkillCorner shot distance fields exactly (rounded FIBA basket position).
HOOP = np.array([-40.75, 0.0])
BASE_FEATURES = [
    "shot_clock",
    "game_clock",
    "ball_x",
    "ball_y",
    "ball_height",
    "handler_rim_distance",
]
FEATURES = BASE_FEATURES + [
    "handler_speed",
    "handler_toward_rim",
    "ball_speed",
    "nearest_defender",
    "second_defender",
    "defenders_within_6ft",
    "defenders_within_10ft",
    "defender_closing_speed",
    "rim_protector_distance",
    "sideline_distance",
    "teammate_spacing",
    "open_teammates",
    "best_lane_clearance",
    "mean_lane_clearance",
    "crowded_lanes",
    "handler_control_distance",
    "detected_fraction",
    "mean_position_error",
    "ball_error",
    "history_available",
]


def segment_clearance(start, end, defenders):
    """Minimum distance to the *interior* of a potential passing segment."""
    delta = end - start
    norm = float(delta @ delta)
    if norm < 1e-8:
        return 0.0
    t = ((defenders - start) @ delta) / norm
    interior = (t > 0.05) & (t < 0.95)
    if not interior.any():
        return 25.0
    points = start + np.clip(t, 0, 1)[:, None] * delta
    return float(np.linalg.norm(defenders[interior] - points[interior], axis=1).min())


def spatial_features(frame, previous=None):
    """Return features + geometry, or no estimate for unsupported ball-control states.

    Previous is only an earlier frame. Vendor speed fields are deliberately unused.
    Geometry is descriptive, never interpreted as a per-pass interception probability.
    """
    off, defense, ball = frame["offense"], frame["defense"], frame["ball"]
    if len(off) != 5 or len(defense) != 5 or len(ball) < 3:
        return None
    op = np.array([[p[1], p[2]] for p in off])
    dp = np.array([[p[1], p[2]] for p in defense])
    b = np.array(ball[:2])
    distances = np.linalg.norm(op - b, axis=1)
    h = int(distances.argmin())
    loc = op[h]
    if (
        distances[h] > 5.5
        or ball[2] > 7.5
        or np.linalg.norm(dp - b, axis=1).min() + 1 < distances[h]
    ):
        return None
    dd = np.linalg.norm(dp - loc, axis=1)
    nearest = int(dd.argmin())
    teammates = np.delete(op, h, axis=0)
    lanes = [segment_clearance(loc, mate, dp) for mate in teammates]
    td = np.linalg.norm(teammates[:, None, :] - dp[None, :, :], axis=2).min(axis=1)
    velocity = np.zeros(2)
    ball_speed = 0.0
    closing = 0.0
    history = 0.0
    if previous and previous["period"] == frame["period"]:
        dt = (frame["frame"] - previous["frame"]) / 25
        old = {
            p[0]: np.array(p[1:3]) for p in previous["offense"] + previous["defense"]
        }
        if 0 < dt <= 0.5 and off[h][0] in old:
            velocity = (loc - old[off[h][0]]) / dt
            ball_speed = float(np.linalg.norm(b - np.array(previous["ball"][:2])) / dt)
            if defense[nearest][0] in old:
                prev_distance = np.linalg.norm(
                    old[defense[nearest][0]] - old[off[h][0]]
                )
                closing = float((prev_distance - dd[nearest]) / dt)
            history = 1.0
    errors = [p[4] for p in off + defense]
    values = [
        frame["shotClock"],
        frame["gameClock"],
        *b,
        ball[2],
        float(np.linalg.norm(loc - HOOP)),
        min(float(np.linalg.norm(velocity)), 40),
        float(np.clip(-velocity[0], -40, 40)),
        min(ball_speed, 100),
        float(dd.min()),
        float(np.sort(dd)[1]),
        int((dd < 6).sum()),
        int((dd < 10).sum()),
        float(np.clip(closing, -40, 40)),
        float(np.linalg.norm(dp - HOOP, axis=1).min()),
        max(0, 24.606 - abs(loc[1])),
        float(np.linalg.norm(teammates - loc, axis=1).mean()),
        int((td > 6).sum()),
        max(lanes),
        float(np.mean(lanes)),
        sum(v < 3 for v in lanes),
        float(distances[h]),
        sum(p[3] for p in off + defense) / 10,
        float(np.mean(errors)),
        ball[4],
        history,
    ]
    values = [
        float(v) if v is not None and math.isfinite(v) else float("nan") for v in values
    ]
    return dict(zip(FEATURES, values)), {
        "handler": off[h][0],
        "nearestDefender": defense[nearest][0],
        "lanes": [
            {"player": p[0], "clearance": round(c, 2)}
            for p, c in zip([p for i, p in enumerate(off) if i != h], lanes)
        ],
    }


# EPV must compare observed and hypothetical controlled possession states.
# Ball-flight measurements and tracking-quality artifacts are not available
# symmetrically at a hypothetical catch; retain them for turnover models only.
EPV_GEOMETRY_FEATURES = [
    f
    for f in FEATURES
    if f
    not in {
        "ball_x",
        "ball_y",
        "ball_height",
        "ball_speed",
        "handler_control_distance",
        "detected_fraction",
        "mean_position_error",
        "ball_error",
        "history_available",
    }
] + ["holder_x", "holder_y"]
