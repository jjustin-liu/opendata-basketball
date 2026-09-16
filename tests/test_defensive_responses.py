import copy
import unittest
from epv.defensive_responses import response_pair, robust_reduction
from epv.features import spatial_features
from tests.test_model import frame

class DefensiveResponseTest(unittest.TestCase):
    def test_rejects_pressure_that_opens_a_backcut(self):
        self.assertIsNone(robust_reduction([(1.2,1.1),(.9,1.15)]))
        self.assertIsNone(robust_reduction([(1.2,1.1),(1.3,1.4)]))
        self.assertIsNotNone(robust_reduction([(1.2,1.1),(1.3,1.2)]))
    def test_no_response_or_unsupported_value_is_not_safe(self):
        self.assertIsNone(robust_reduction([(1.2,1.1)]))
        self.assertIsNone(robust_reduction([(1.2,1.1),(float('nan'),1)]))
    def test_equal_clock_source_immutable_and_cut_moves_toward_rim(self):
        f=frame();f['geometry']=spatial_features(f)[1]
        d=f['defense'][0];c=dict(player=d[0],origin=d[1:3],to=[d[1]+2,d[2]])
        original=copy.deepcopy(f)
        receiver=next(p for p in f['offense'] if p[0]!=f['geometry']['handler'])
        pair=response_pair(f,c,receiver[0],4)
        self.assertIsNotNone(pair)
        self.assertEqual(pair[0]['state']['shot_clock'],pair[1]['state']['shot_clock'])
        self.assertEqual(pair[0]['state']['shot_clock'],f['shotClock']-2)
        self.assertEqual(f,original)
