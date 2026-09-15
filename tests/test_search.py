import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from epv.search import CLASSES, FEATURES, adjusted, effects, examples, next_event


class SearchTest(unittest.TestCase):
    def test_attempted_pass_owns_its_turnover_branch(self):
        label, _, delay = next_event(
            {"endFrame": 120}, 100, [(110, 0, "pass", {}), (110, 2, "turnover", {})]
        )
        self.assertEqual(label, "pass")
        self.assertEqual(delay, 0.4)

    def test_shooting_foul_is_counted_with_shot(self):
        label, _, _ = next_event(
            {"endFrame": 120},
            100,
            [(115, 1, "shot", {"complexShotType": "stepback"}), (115, 3, "foul", {})],
        )
        self.assertEqual(label, "pullup")

    def test_horizon_does_not_invent_retention_after_unknown_end(self):
        self.assertEqual(
            next_event({"endFrame": 200}, 100, [(151, 0, "pass", {})])[0], "retain"
        )
        self.assertEqual(next_event({"endFrame": 140}, 100, [])[0], "other")
        self.assertEqual(
            next_event({"endFrame": 200}, 100, [(99, 0, "pass", {})])[0], "retain"
        )

    def test_player_effect_requires_multiple_games_and_enough_touches(self):
        t = pd.DataFrame(
            {
                "player": [1] * 25,
                "gameId": [1] * 25,
                "outcome": ["pass"] * 25,
                "points": [2] * 25,
            }
        )
        prob = np.full((25, len(CLASSES)), 1 / len(CLASSES))
        value = np.ones(25)
        e = effects(t, prob, value)
        self.assertEqual(e[1]["weight"], 0)
        p, v = adjusted(prob, value, t, e)
        np.testing.assert_allclose(p, prob)
        np.testing.assert_allclose(v, value)
        t.loc[12:, "gameId"] = 2
        e = effects(t, prob, value)
        self.assertGreater(e[1]["weight"], 0)
        p, v = adjusted(prob, value, t, e)
        np.testing.assert_allclose(p.sum(axis=1), 1)
        self.assertTrue((p >= 0).all())

    def test_anchor_is_strictly_prior_and_future_geometry_not_features(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "artifacts").mkdir()
            (root / "data/matches/1").mkdir(parents=True)
            (root / "data/player_id_aliases.csv").write_text(
                "player_id,canonical_player_id\n"
            )
            row = {k: 1.0 for k in FEATURES}
            row.update(
                gameId=1,
                possessionId="p",
                frame=9,
                shooter=7,
                handler_rim_distance=20,
                shot_clock=10,
                points=2,
            )
            future = {**row, "frame": 10, "nearest_defender": 999}
            pd.DataFrame([row, future]).to_pickle(root / "artifacts/states.pkl")
            data = {
                "touches": [
                    {
                        "id": "t",
                        "possessionId": "p",
                        "startFrame": 0,
                        "endFrame": 100,
                        "playerId": 7,
                    }
                ],
                "dribbles": [{"touchId": "t", "frame": 10}],
                "passes": [],
                "shots": [],
                "turnovers": [],
                "fouls": [],
            }
            (root / "data/matches/1/1_dynamic_events.json").write_text(json.dumps(data))
            table, _, _ = examples(root)
            self.assertEqual(len(table), 1)
            self.assertEqual(table.iloc[0].frame, 9)
            self.assertEqual(table.iloc[0].nearest_defender, 1)
            self.assertNotIn("points", FEATURES)
            self.assertNotIn("releaseDistance", FEATURES)


if __name__ == "__main__":
    unittest.main()
