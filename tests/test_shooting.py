import unittest
import numpy as np
import pandas as pd
from epv.shooting import ShotModel, shot_region, location_is_three, attach_predictions


def attempts():
    rows = []
    for player in [1, 2]:
        for i in range(40):
            rows.append(
                {
                    "gameId": 10 + i % 2,
                    "shooter": player,
                    "region": "three",
                    "shot_distance": 23 + (i % 4) / 4,
                    "shot_defender": 3 + (i % 5),
                    "shot_abs_y": i % 4,
                    "shot_clock": 5 + i % 10,
                    "three": True,
                    "made": int(i < (28 if player == 1 else 8)),
                }
            )
    return pd.DataFrame(rows)


class ShootingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = ShotModel.fit(attempts())

    def test_player_identity_does_not_change_quality_at_identical_geometry(self):
        query = attempts().iloc[:2].copy()
        query.iloc[1] = query.iloc[0]
        query["shooter"] = [1, 2]
        pooled, personal, offsets, counts = self.model.predict(query)
        self.assertAlmostEqual(pooled[0], pooled[1])
        self.assertAlmostEqual(personal[0], personal[1])
        np.testing.assert_array_equal(offsets, [0, 0])
        np.testing.assert_array_equal(counts, [40, 40])

    def test_unseen_player_or_zone_falls_back_to_pooled(self):
        query = attempts().iloc[:2].copy()
        query["shooter"] = [999, 1]
        query["region"] = ["three", "rim"]
        pooled, personal, offsets, counts = self.model.predict(query)
        np.testing.assert_allclose(pooled, personal)
        np.testing.assert_array_equal(counts, [0, 0])

    def test_player_effects_use_only_training_games(self):
        model = ShotModel.fit(attempts().query("gameId == 10"))
        self.assertEqual(model.training_games, (10,))
        self.assertEqual(model.counts[(1, "three")], 20)

    def test_range_mask_and_field_goal_value(self):
        query = attempts().iloc[:2].copy()
        query["shot_distance"] = [24, 50]
        result = attach_predictions(query, self.model)
        self.assertAlmostEqual(
            result.shot_field_goal_value.iloc[0],
            3 * result.shot_make_probability.iloc[0],
        )
        self.assertTrue(np.isnan(result.shot_field_goal_value.iloc[1]))

    def test_fiba_corner_and_arc(self):
        np.testing.assert_array_equal(
            location_is_three([21.8, 21.8, 23], [21.8, 0, 0]), [True, False, True]
        )
        np.testing.assert_array_equal(
            shot_region([5, 15, 24], [False, False, True]), ["rim", "two", "three"]
        )


if __name__ == "__main__":
    unittest.main()
