import unittest
import numpy as np
import pandas as pd
from epv.build import remaining_targets, weights, coherent_risks
from epv.features import spatial_features, segment_clearance, FEATURES


def frame():
    return {
        "frame": 100,
        "period": 1,
        "shotClock": 12.0,
        "gameClock": 200.0,
        "offense": [
            [i, x, y, 1, 1.0, str(i)]
            for i, (x, y) in enumerate(
                [(-20, 0), (-35, 20), (-35, -20), (-15, 15), (-40, 2)]
            )
        ],
        "defense": [
            [i + 10, x, y, 1, 1.0, str(i + 10)]
            for i, (x, y) in enumerate(
                [(-23, 0), (-35, 17), (-35, -17), (-17, 15), (-41, 2)]
            )
        ],
        "ball": [-20, 0, 3, 1, 1.0],
    }


class RewardsTest(unittest.TestCase):
    def test_remaining_reward_excludes_already_scored_points(self):
        self.assertEqual(
            remaining_targets(100, 200, [(80, 2), (100, 1), (120, 1), (200, 2)], []),
            (3, 0, 0),
        )

    def test_probability_horizons_are_coherent(self):
        short, long = coherent_risks(np.array([0.3, 0.1]), np.array([0.1, 0.4]))
        np.testing.assert_allclose(short, [0.2, 0.1])
        np.testing.assert_allclose(long, [0.2, 0.4])

    def test_turnover_horizon_and_boundary(self):
        self.assertEqual(remaining_targets(100, 200, [], [(120, 198)]), (0, 1, 1))
        self.assertEqual(remaining_targets(100, 200, [], [(120, 197.9)]), (0, 0, 1))
        self.assertEqual(remaining_targets(100, 200, [], [(100, 200)]), (0, 0, 0))
        self.assertEqual(remaining_targets(100, 200, [], [(80, 201)]), (0, 0, 0))

    def test_long_possessions_do_not_dominate(self):
        df = pd.DataFrame({"possessionId": ["a"] + ["b"] * 4, "frame": [0, 0, 1, 2, 3]})
        w = weights(df)
        self.assertAlmostEqual(w[0], sum(w[1:]))


class GeometryTest(unittest.TestCase):
    def test_basket_matches_skillcorner_distance_convention(self):
        self.assertAlmostEqual(
            spatial_features(frame())[0]["handler_rim_distance"], 20.75
        )

    def test_passing_segment(self):
        self.assertEqual(
            segment_clearance(np.array([0, 0]), np.array([10, 0]), np.array([[5, 2]])),
            2,
        )
        self.assertEqual(
            segment_clearance(np.array([0, 0]), np.array([10, 0]), np.array([[15, 0]])),
            25,
        )

    def test_features_are_invariant_to_player_array_order(self):
        f = frame()
        a = spatial_features(f)[0]
        f["offense"].reverse()
        f["defense"].reverse()
        b = spatial_features(f)[0]
        np.testing.assert_allclose(list(a.values()), list(b.values()), atol=1e-12)
        self.assertEqual(set(a), set(FEATURES))

    def test_ball_flight_and_incomplete_tracking_do_not_get_predictions(self):
        f = frame()
        f["ball"][2] = 12
        self.assertIsNone(spatial_features(f))
        f = frame()
        f["defense"].pop()
        self.assertIsNone(spatial_features(f))

    def test_future_frame_not_used_as_motion_history(self):
        f = frame()
        later = frame()
        later["frame"] = 105
        later["offense"][0][1] = 100
        a = spatial_features(f)[0]
        b = spatial_features(f, later)[0]
        self.assertEqual(a, b)

    def test_trailing_motion(self):
        f = frame()
        previous = frame()
        previous["frame"] = 95
        previous["offense"][0][1] = -19
        a = spatial_features(f, previous)[0]
        self.assertAlmostEqual(a["handler_speed"], 5)
        self.assertAlmostEqual(a["handler_toward_rim"], 5)


if __name__ == "__main__":
    unittest.main()
