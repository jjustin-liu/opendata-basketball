import unittest
from epv.shot_review import apply_release_quality

class ReleaseQualityTest(unittest.TestCase):
    def test_conversion_miss_weight_and_fallback(self):
        event = {'shotForecast': {'quality': {'makeProbability': .4, 'fieldGoalValue': 1.2}, 'secondChancePerMiss': .5}}
        self.assertTrue(apply_release_quality(event, {'shotQuality': 60, 'three': True}))
        f = event['shotForecast']
        self.assertEqual(f['quality']['fieldGoalValue'], 1.8)
        self.assertEqual(f['secondChancePerShot'], .2)
        apply_release_quality(event, {'shotQuality': 60, 'three': True})
        self.assertEqual(f['pooledQuality']['makeProbability'], .4)
        self.assertFalse(apply_release_quality(event, {'shotQuality': None, 'three': True}))
        self.assertEqual(f['quality']['makeProbability'], .4)
        self.assertEqual(f['secondChancePerShot'], .3)
