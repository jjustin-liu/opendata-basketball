import copy
import unittest
import numpy as np
from epv.features import spatial_features
from epv.passing import infer_receiver, pass_features, project_catch, velocities
from tests.test_model import frame


class PassingTest(unittest.TestCase):
    def test_direction_recovers_receiver_and_rejects_ambiguous_ray(self):
        f = frame()
        self.assertEqual(infer_receiver(f, 0, [-23, 4]), 1)
        f["offense"][3][1:3] = [-30, 13.5]
        self.assertIsNone(infer_receiver(f, 0, [-23, 4]))
        self.assertIsNone(infer_receiver(f, 0, [-20.1, 0.1]))

    def test_lane_features_respond_to_intervening_defender(self):
        f = frame()
        before = pass_features(f, 0, 1)
        f["defense"][0][1:3] = [-27.5, 10]
        after = pass_features(f, 0, 1)
        self.assertLess(after["lane_clearance"], before["lane_clearance"])
        self.assertIsNone(pass_features(f, 0, 0))

    def test_catch_transfers_control_and_decrements_clocks(self):
        f = frame()
        f["geometry"] = spatial_features(f)[1]
        original = copy.deepcopy(f)
        dt, projected, features = project_catch(f, None, 1)
        self.assertEqual(projected["geometry"]["handler"], 1)
        self.assertEqual(features["shooter"], 1)
        self.assertAlmostEqual(projected["shotClock"], f["shotClock"] - dt)
        self.assertEqual(f, original)
        self.assertIsNone(project_catch(f, None, 0))
        f["shotClock"] = 0.1
        self.assertIsNone(project_catch(f, None, 1))

    def test_projection_uses_prior_velocity_and_rejects_future_history(self):
        f = frame()
        f["geometry"] = spatial_features(f)[1]
        previous = copy.deepcopy(f)
        previous["frame"] -= 5
        previous["offense"][1][1] -= 1
        dt, projected, _ = project_catch(f, previous, 1)
        p = next(p for p in projected["offense"] if p[0] == 1)
        self.assertAlmostEqual(p[1], f["offense"][1][1] + 5 * dt)
        previous["frame"] = f["frame"] + 5
        self.assertEqual(velocities(f, previous), {})
        previous["frame"] = f["frame"] - 100
        self.assertEqual(velocities(f, previous), {})


if __name__ == "__main__":
    unittest.main()


class InterceptionTimingTest(unittest.TestCase):
    def test_defender_in_lane_has_time_advantage(self):
        from epv.passing import interception_features

        a, b = np.array([0.0, 0.0]), np.array([24.0, 0.0])
        near = interception_features(a, b, np.array([[12.0, 0.3]]))
        far = interception_features(a, b, np.array([[12.0, 15.0]]))
        self.assertEqual(near["immediate_lane_reach"], 1)
        self.assertGreater(near["intercept_advantage"], 0)
        self.assertGreater(near["intercept_advantage"], far["intercept_advantage"])
        self.assertEqual(far["reachable_defenders"], 0)

    def test_reach_features_are_rotation_and_translation_invariant(self):
        from epv.passing import interception_features

        a, b = np.array([0.0, 0.0]), np.array([20.0, 10.0])
        d = np.array([[10.0, 6.0], [8.0, -12.0]])
        first = interception_features(a, b, d)
        second = interception_features(-a + 3, -b + 3, -d + 3)
        for key in first:
            self.assertAlmostEqual(first[key], second[key])


class CatchBoundaryTest(unittest.TestCase):
    def test_other_player_crossing_sideline_does_not_cancel_pass(self):
        f = frame()
        f["geometry"] = spatial_features(f)[1]
        f["offense"][2][2] = -24.5
        previous = copy.deepcopy(f)
        previous["frame"] -= 5
        previous["offense"][2][2] += 1
        result = project_catch(f, previous, 1)
        self.assertIsNotNone(result)
        projected = result[1]
        other = next(p for p in projected["offense"] if p[0] == 2)
        self.assertAlmostEqual(other[2], -24.606)
        self.assertIsNone(project_catch(f, previous, 2))

    def test_other_defender_crossing_baseline_does_not_cancel_pass(self):
        f = frame()
        f["geometry"] = spatial_features(f)[1]
        f["defense"][4][1] = -45.8
        previous = copy.deepcopy(f)
        previous["frame"] -= 5
        previous["defense"][4][1] += 1
        result = project_catch(f, previous, 1)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result[1]["defense"][4][1], -45.932)


class CatchMotionConsistencyTest(unittest.TestCase):
    def test_projected_closing_speed_and_history_are_preserved(self):
        f = frame()
        f["geometry"] = spatial_features(f)[1]
        previous = copy.deepcopy(f)
        previous["frame"] -= 5
        # Defender nearest receiver 1 closes at 2 ft/s; receiver stationary.
        previous["defense"][1][2] -= 0.4
        result = project_catch(f, previous, 1)
        self.assertIsNotNone(result)
        features = result[2]
        self.assertEqual(features["history_available"], 1)
        self.assertAlmostEqual(features["defender_closing_speed"], 2, places=5)
        self.assertAlmostEqual(features["holder_x"], -35)
        self.assertAlmostEqual(features["holder_y"], 20)

    def test_unavailable_motion_is_missing_not_zero(self):
        f = frame()
        f["geometry"] = spatial_features(f)[1]
        features = project_catch(f, None, 1)[2]
        for key in ["handler_speed", "handler_toward_rim", "defender_closing_speed"]:
            self.assertTrue(np.isnan(features[key]))

    def test_epv_does_not_use_unobservable_ball_measurements(self):
        from epv.features import EPV_GEOMETRY_FEATURES

        self.assertIn("holder_x", EPV_GEOMETRY_FEATURES)
        self.assertIn("defender_closing_speed", EPV_GEOMETRY_FEATURES)
        for key in [
            "ball_speed",
            "ball_height",
            "ball_x",
            "ball_y",
            "ball_error",
            "handler_control_distance",
            "history_available",
        ]:
            self.assertNotIn(key, EPV_GEOMETRY_FEATURES)
