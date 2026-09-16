import unittest

import numpy as np
import pandas as pd

from epv import space


def nearest(x, y):
    return int(np.argmin(np.hypot(space.GRID[:, 0] - x, space.GRID[:, 1] - y)))


def ten_players(f, off_x=-30.0, off_det=True, def_det=True, def_err=2.0):
    return {
        "frame": f,
        "offense": [[i, off_x + 3 * i, 2.0 * i - 4, off_det, 2.0] for i in range(5)],
        "defense": [[10 + i, -20.0, 2.0 * i - 4, def_det, def_err] for i in range(5)],
    }


class SpaceFieldTests(unittest.TestCase):
    def test_arrival_time_monotone_and_moving_away_costs_time(self):
        p = np.array([[[-30.0, 0.0]]])  # (batch, player, xy)
        q = np.array([[-30.0 - d, 0.0] for d in (2, 5, 10, 20, 40)], dtype=np.float32)
        still = space.tta_kinematic(p, np.zeros((1, 1, 2)), q)[0, 0]
        self.assertTrue(np.all(np.diff(still) > 0))
        toward = space.tta_kinematic(p, np.array([[[-10.0, 0.0]]]), q)[0, 0]
        away = space.tta_kinematic(p, np.array([[[10.0, 0.0]]]), q)[0, 0]
        self.assertTrue(np.all(toward < still))
        self.assertTrue(np.all(away > still))
        dist = np.abs(q[:, 0] + 30)
        self.assertTrue(np.all(still >= space.REACTION + dist / space.V_MAX - 1e-6))

    def test_clark_min_matches_monte_carlo(self):
        rng = np.random.default_rng(0)
        mu = np.array([1.0, 1.2, 1.5, 3.0, 4.0])[None, :, None]  # (batch, player, cell)
        sd = np.array([0.3, 0.2, 0.4, 0.5, 0.3])[None, :, None]
        draws = rng.normal(mu, sd, size=(200000, 5, 1)).min(1)
        m, s = space.clark_min(mu, sd)
        self.assertLess(abs(float(m[0, 0]) - draws.mean()), 0.01)
        self.assertLess(abs(float(s[0, 0]) - draws.std()), 0.02)

    def test_control_field_prefers_nearer_team(self):
        off = np.array([[[-35.0, 0.0]] + [[-5.0, y] for y in (-20, -10, 10, 20)]])
        de = np.array([[[-5.0, y] for y in (-20, -10, 0, 10, 20)]])
        zeros = np.zeros((1, 5, 2))
        pe = np.full((1, 5), 2.0)
        det = np.ones((1, 5), dtype=bool)
        c = space.control(off, zeros, pe, det, de, zeros, pe, det)
        self.assertGreater(c[0][space.NEAR_RIM].mean(), 0.9)
        self.assertLess(c[0][space.GRID[:, 0] > -8].mean(), 0.5)
        mc = space.control_monte_carlo(off, zeros, pe, det, de, zeros, pe, det, draws=300)
        self.assertLess(np.abs(c - mc).mean(), 0.04)

    def test_value_map_zone_separation_and_mirror(self):
        shots = pd.DataFrame({"x": [-38.0, -18.0], "y": [5.0, 0.0], "points": [2.0, 3.0]})
        v, n = space.fit_value_map(shots)
        grid = space.to_grid(v)
        self.assertTrue(np.allclose(grid, grid[:, ::-1], atol=1e-5))
        prior = space.value_geometric()
        self.assertGreater(v[nearest(-38, 5)], prior[nearest(-38, 5)])
        self.assertLess(abs(v[nearest(-40, 0)] - prior[nearest(-40, 0)]), abs(v[nearest(-38, 5)] - prior[nearest(-38, 5)]))
        self.assertGreater(v[nearest(-18, 0)], prior[nearest(-18, 0)])
        # a made three does not leak into the two-point zone around it
        self.assertLess(abs(v[nearest(-22, 0)] - prior[nearest(-22, 0)]), 0.05)
        self.assertTrue(np.all(v[space.GRID[:, 0] > 0] == 0))
        self.assertTrue(np.all(n >= 0))

    def test_positions_uses_causal_velocity_only(self):
        prev, cur = ten_players(0, -30.0), ten_players(5, -28.0)
        pos = space.positions(cur, prev)
        self.assertTrue(np.allclose(pos["off_v"][:, 0], 10.0))
        self.assertTrue(np.allclose(pos["def_v"], 0))
        self.assertTrue(np.allclose(space.positions(cur, None)["off_v"], 0))
        self.assertTrue(np.allclose(space.positions(cur, ten_players(-20, -60.0))["off_v"], 0))

    def test_holes_are_empty_valuable_regions(self):
        off = np.array([[-40.0, 0.0], [-38.0, 3.0], [-36.0, -3.0], [-42.0, 4.0], [-30.0, 0.0]])
        h = np.zeros(len(space.GRID), dtype=np.float32)
        corner = (space.GRID[:, 0] < -40) & (space.GRID[:, 1] > 19)
        h[corner] = 1.2
        found = space.holes(h, off)
        self.assertEqual(len(found), 1)
        cx, cy, mass, cells = found[0]
        self.assertLess(cx, -40)
        self.assertGreater(cy, 19)
        self.assertEqual(cells, int(corner.sum()))
        self.assertGreater(mass, 0)
        self.assertEqual(space.holes(h, np.array([[-43.0, 21.5]])), [])

    def test_compute_frames_summaries_and_low_confidence(self):
        frames = [ten_players(0), ten_players(5, def_det=False, def_err=12.0), {"frame": 10, "offense": [], "defense": []}]
        table, fields = space.compute_frames(frames, space.value_geometric(), store_fields=True)
        self.assertEqual(list(table.columns[: len(space.SPACE_FEATURES)]), space.SPACE_FEATURES)
        self.assertTrue(np.isnan(table.space_a.iloc[2]))
        self.assertIsNone(fields[2])
        self.assertGreater(table.space_a.iloc[0], 0)
        self.assertAlmostEqual(table.space_a.iloc[0], table.space_hole.iloc[0] + table.space_occ.iloc[0], places=2)
        self.assertEqual(table.n_extrap.tolist()[:2], [0, 5])
        self.assertEqual(space.low_confidence(table).tolist()[:2], [False, True])


if __name__ == "__main__":
    unittest.main()
