import unittest
from copy import deepcopy
from epv.shot_release import project_release


class ShotReleaseTest(unittest.TestCase):
    def frames(self):
        now = {'frame': 10, 'period': 1, 'shotClock': 8,
               'offense': [[1, -20., 0., True]],
               'defense': [[2, -14., 0., True]]}
        old = deepcopy(now)
        old['frame'] = 5
        old['defense'][0][1] = -12.
        return now, old

    def test_closing_defender_and_clock(self):
        now, old = self.frames()
        release, features = project_release(now, old, 1)
        self.assertAlmostEqual(features['shot_defender'], 1.)
        self.assertEqual(release['shotClock'], 7.5)
        self.assertEqual(release['offense'], now['offense'])
        self.assertEqual(now['defense'][0][1], -14.)

    def test_retreat_is_not_treated_as_closeout(self):
        now, old = self.frames()
        old['defense'][0][1] = -16.
        _, features = project_release(now, old, 1)
        self.assertAlmostEqual(features['shot_defender'], 11.)

    def test_no_projection_without_history_or_time(self):
        now, old = self.frames()
        self.assertIsNone(project_release(now, None, 1))
        now['shotClock'] = .3
        self.assertIsNone(project_release(now, old, 1))
