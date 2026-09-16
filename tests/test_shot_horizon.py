import copy
import unittest

import numpy as np

from epv.features import HOOP
from epv.shot_horizon import (
    HORIZONS,
    MIN_CLOCK,
    apply_calibration,
    fit_calibration,
    future_frame,
    momentum_gain,
    projected_state,
    score,
    survival,
    trailing_velocity,
)
from tests.test_model import frame


def moving(step=5, shift=(2.0, 0.0), count=3):
    """A short causal history where everyone drifts by `shift` each sample."""
    frames = []
    for i in range(count):
        f = copy.deepcopy(frame())
        f["frame"] = 100 + i * step
        f["shotClock"] = 12.0 - i * step / 25
        f["turnover2"] = 0.04
        for side in ("offense", "defense"):
            for p in f[side]:
                p[1] += shift[0] * i
                p[2] += shift[1] * i
        f["geometry"] = {"handler": f["offense"][0][0]}
        f["shot"] = {"shotPlusSecondChance": 1.0 + 0.1 * i, "pointsIfMade": 2}
        frames.append(f)
    return frames


class VelocityTest(unittest.TestCase):
    def test_velocity_uses_only_earlier_samples(self):
        frames = moving()
        before = trailing_velocity(frames, 1)
        frames[2]["offense"][0][1] += 40  # a future sample must not reach back
        after = trailing_velocity(frames, 1)
        self.assertEqual(set(before), set(after))
        for pid, v in before.items():
            np.testing.assert_allclose(v, after[pid])

    def test_velocity_is_the_trailing_average_and_breaks_over_gaps(self):
        frames = moving()
        v = trailing_velocity(frames, 2)
        np.testing.assert_allclose(v[frames[2]["offense"][0][0]], [10.0, 0.0])
        frames[2]["frame"] += 40
        self.assertEqual(trailing_velocity(frames, 2), {})

    def test_first_sample_has_no_causal_history(self):
        self.assertEqual(trailing_velocity(moving(), 0), {})


class ProjectionTest(unittest.TestCase):
    def setUp(self):
        self.frames = moving()
        self.velocity = trailing_velocity(self.frames, 2)
        self.holder = self.frames[2]["geometry"]["handler"]
        self.caps = {p[0]: 20.0 for side in ("offense", "defense") for p in self.frames[2][side]}

    def project(self, seconds=0.4, response="hold", frame_=None):
        return projected_state(frame_ or self.frames[2], self.velocity, seconds, response,
                               self.caps, self.holder, 18.0)

    def test_projection_does_not_mutate_the_replay_frame(self):
        original = copy.deepcopy(self.frames[2])
        self.assertIsNotNone(self.project())
        self.assertEqual(self.frames[2], original)

    def test_zero_velocity_reproduces_the_current_positions(self):
        still = {pid: np.zeros(2) for pid in self.velocity}
        state = projected_state(self.frames[2], still, 0.8, "momentum", self.caps, self.holder, 18.0)
        for row, p in zip(state["offense"], self.frames[2]["offense"]):
            np.testing.assert_allclose(row[1:3], p[1:3])
        for row, d in zip(state["defense"], self.frames[2]["defense"]):
            np.testing.assert_allclose(row[1:3], d[1:3])

    def test_expired_shot_clock_has_no_projection(self):
        late = copy.deepcopy(self.frames[2])
        late["shotClock"] = MIN_CLOCK + 0.1
        self.assertIsNone(self.project(seconds=0.4, frame_=late))

    def test_holder_gathers_at_the_rim_rather_than_running_through_it(self):
        frames = moving(shift=(-4.0, 0.0))
        velocity = trailing_velocity(frames, 2)
        holder = frames[2]["geometry"]["handler"]
        caps = {p[0]: 25.0 for side in ("offense", "defense") for p in frames[2][side]}
        state = projected_state(frames[2], velocity, 1.2, "hold", caps, holder, 18.0)
        spot = np.array(next(r for r in state["offense"] if r[0] == holder)[1:3])
        self.assertLessEqual(float(np.linalg.norm(spot - HOOP)), 0.001)

    def test_speed_cap_truncates_displacement(self):
        slow = {pid: v for pid, v in self.velocity.items()}
        capped = projected_state(self.frames[2], slow, 1.0, "hold",
                                 {pid: 2.0 for pid in slow}, self.holder, 2.0)
        start = np.array(next(p for p in self.frames[2]["offense"] if p[0] == self.holder)[1:3])
        spot = np.array(next(r for r in capped["offense"] if r[0] == self.holder)[1:3])
        self.assertLessEqual(float(np.linalg.norm(spot - start)), 2.0 + 1e-9)

    def test_closing_defender_cannot_beat_the_reaction_delay(self):
        hold = self.project(seconds=0.4, response="hold")
        close = self.project(seconds=0.4, response="close")
        spot = np.array(next(r for r in close["offense"] if r[0] == self.holder)[1:3])
        gaps = lambda state: min(float(np.linalg.norm(np.array(d[1:3]) - spot)) for d in state["defense"])
        self.assertLessEqual(gaps(close), gaps(hold) + 1e-9)
        # A closing defender abandons his own velocity and waits out the reaction
        # delay before recovering, matching the convention in epv.movement.
        instant = self.project(seconds=0.2, response="close")
        target = np.array(next(r for r in instant["offense"] if r[0] == self.holder)[1:3])
        original = {d[0]: np.array(d[1:3], float) for d in self.frames[2]["defense"]}
        nearest = min(original, key=lambda pid: float(np.linalg.norm(original[pid] - target)))
        np.testing.assert_allclose(next(r for r in instant["defense"] if r[0] == nearest)[1:3],
                                   original[nearest])


class MatchingTest(unittest.TestCase):
    def test_future_frame_requires_the_same_supported_handler(self):
        frames = moving(step=10, count=3)
        self.assertIs(future_frame(frames, 0, 0.4), frames[1])
        frames[1]["geometry"]["handler"] = 999
        self.assertIsNone(future_frame(frames, 0, 0.4))
        frames[1]["geometry"]["handler"] = frames[0]["geometry"]["handler"]
        frames[1]["reason"] = "Ball in flight"
        self.assertIsNone(future_frame(frames, 0, 0.4))

    def test_future_frame_breaks_across_tracking_gaps(self):
        frames = moving(step=10, count=3)
        frames[1]["frame"] += 30
        frames[2]["frame"] += 30
        self.assertIsNone(future_frame(frames, 0, 0.4))

    def test_survival_discounts_with_the_horizon(self):
        f = moving()[0]
        self.assertAlmostEqual(survival(f, 2.0), 0.96)
        self.assertGreater(survival(f, 0.4), survival(f, 1.2))
        self.assertIsNone(survival({"shot": {}}, 0.4))


class CalibrationTest(unittest.TestCase):
    def rows(self, n=400, noise=0.0):
        rng = np.random.default_rng(0)
        rows = []
        for i in range(n):
            base = float(rng.uniform(0.6, 1.8))
            rows.append(dict(seconds=HORIZONS[0], hold=base, momentum=base, close=base,
                             persistence=base, target=base + noise * float(rng.normal()),
                             speed=12.0, crossing=False, gameId=1))
        return rows

    def test_calibration_recovers_an_unbiased_fit(self):
        rows = self.rows()
        weights = fit_calibration(rows)
        value = apply_calibration(weights, HORIZONS[0],
                                  {"hold": dict(pps=1.2), "momentum": dict(pps=1.2), "close": dict(pps=1.2)}, 1.2)
        self.assertAlmostEqual(value, 1.2, places=3)

    def test_unknown_horizon_has_no_calibration(self):
        self.assertIsNone(apply_calibration(fit_calibration(self.rows()), 99.0, {}, 1.0))

    def test_too_few_rows_are_not_fitted(self):
        self.assertEqual(fit_calibration(self.rows(n=10)), {})

    def test_perfect_projection_scores_full_skill(self):
        rows = [dict(seconds=HORIZONS[0], calibrated=1.5, shrunk=1.2, projection=1.5,
                     persistence=1.0, target=1.5, speed=12.0, crossing=False, gameId=1)] * 20
        self.assertEqual(score(rows)["skill"], 1.0)
        self.assertEqual(score(rows)["mae"], 0.0)
        self.assertEqual(momentum_gain(rows), 1.0)


if __name__ == "__main__":
    unittest.main()
