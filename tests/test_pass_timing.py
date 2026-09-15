import copy
import unittest
import numpy as np
import pandas as pd
from epv.pass_timing import TimingModel, TIMING_FEATURES, timing_features
from epv.passing import project_catch
from epv.features import spatial_features
from tests.test_model import frame


class TimingTest(unittest.TestCase):
    def test_learned_duration_controls_catch_and_clock(self):
        class Model:
            def duration(self, features):
                return 0.6

        f = frame()
        f["geometry"] = spatial_features(f)[1]
        dt, p, _ = project_catch(f, None, 1, Model())
        self.assertAlmostEqual(dt, 0.72)
        self.assertAlmostEqual(p["shotClock"], f["shotClock"] - 0.72)

    def test_receiver_direction_enters_features(self):
        f = frame()
        previous = copy.deepcopy(f)
        previous["frame"] -= 5
        direction = np.array(f["offense"][1][1:3]) - np.array(f["offense"][0][1:3])
        direction = direction / np.linalg.norm(direction)
        previous["offense"][1][1:3] = (
            np.array(f["offense"][1][1:3]) - direction
        ).tolist()
        a = timing_features(f, previous, 0, 1)
        self.assertAlmostEqual(a["receiver_along"], 5)
        self.assertAlmostEqual(a["receiver_across"], 0)
        self.assertEqual(a["history"], 1)

    def test_model_tracks_training_games_and_bounds_duration(self):
        rows = []
        for i in range(30):
            rows.append(
                {
                    **{k: float(i) for k in TIMING_FEATURES},
                    "duration": 0.1 + i * 0.02,
                    "gameId": i % 3,
                }
            )
        table = pd.DataFrame(rows)
        model = TimingModel.fit(table[table.gameId != 2])
        self.assertNotIn(2, model.training_games)
        values = model.predict(table)
        self.assertTrue(np.all(np.isfinite(values)))
        self.assertTrue(np.all((values >= 0.04) & (values <= 3)))
        self.assertGreater(values[-1], values[0])
