"""Causal, explicit set-shot wind-up scenario; no learned reaction model."""

from copy import deepcopy

import numpy as np

from .features import HOOP
from .passing import velocities

WINDUP_SECONDS = 0.5


def project_release(frame, previous, shooter):
    motion = velocities(frame, previous)
    players = frame["offense"] + frame["defense"]
    if any(p[0] not in motion for p in players):
        return None
    holder = next((p for p in frame["offense"] if p[0] == shooter), None)
    if (
        holder is None
        or frame.get("shotClock") is None
        or frame["shotClock"] <= WINDUP_SECONDS
    ):
        return None
    projected = deepcopy(frame)
    target = np.asarray(holder[1:3])
    for side in ["offense", "defense"]:
        for p in projected[side]:
            if p[0] == shooter:
                continue  # Set shot: shooter gathers at the current spot.
            v = motion[p[0]]
            t = WINDUP_SECONDS
            if side == "defense" and np.dot(v, v) > 0:
                # Stop at closest approach; don't credit an overshoot through the shooter.
                approach = float(np.dot(target - p[1:3], v) / np.dot(v, v))
                if approach > 0:
                    t = min(t, approach)
            p[1:3] = (np.asarray(p[1:3]) + v * t).tolist()
    projected["shotClock"] -= WINDUP_SECONDS
    separation = min(
        np.linalg.norm(np.asarray(p[1:3]) - target) for p in projected["defense"]
    )
    return projected, {
        "shot_distance": float(np.linalg.norm(target - HOOP)),
        "shot_defender": float(separation),
        "shot_abs_y": abs(holder[2]),
        "shot_clock": projected["shotClock"],
    }
