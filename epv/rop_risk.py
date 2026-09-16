"""Conservative remaining-possession risk, anchored to other-game prevalence."""
import numpy as np


def conservative_rop(raw, baseline, short):
    """Retain 25% of geometry variation; remaining risk cannot be below 2s risk."""
    return np.clip(np.maximum(.75 * baseline + .25 * np.asarray(raw), short), 0, 1)
