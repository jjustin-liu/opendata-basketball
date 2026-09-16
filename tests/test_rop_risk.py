import unittest
import numpy as np
from epv.rop_risk import conservative_rop


class RopRiskTests(unittest.TestCase):
    def test_shrinks_extreme_risk(self):
        self.assertAlmostEqual(float(conservative_rop(.34, .16, .05)), .205)

    def test_respects_short_horizon(self):
        self.assertAlmostEqual(float(conservative_rop(.1, .16, .25)), .25)

    def test_vectorized(self):
        np.testing.assert_allclose(conservative_rop([.1, .3], .16, [.01, .01]), [.145, .195])
