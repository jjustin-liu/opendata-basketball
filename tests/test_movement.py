import copy
import unittest

from epv.features import spatial_features
from epv.movement import simulate_pair, summarize, supported, defensive_shift
from tests.test_model import frame


class MovementTest(unittest.TestCase):
    def test_defensive_shift_is_same_clock_and_does_not_mutate_replay(self):
        f=frame();f['geometry']=spatial_features(f)[1]
        original=copy.deepcopy(f)
        d=f['defense'][0][0]
        base=defensive_shift(f,d,0,0)
        shifted=defensive_shift(f,d,2,0)
        self.assertIsNotNone(shifted)
        self.assertEqual(base['shot_clock'],shifted['shot_clock'])
        self.assertEqual(f,original)
        self.assertIsNone(defensive_shift(f,d,100,0))

    def test_small_robust_gains_are_now_accepted(self):
        self.assertIsNotNone(summarize([{'gain':.012},{'gain':.02},{'gain':.03}]))
        self.assertIsNone(summarize([{'gain':.009},{'gain':.02},{'gain':.03}]))
    def test_move_and_stay_share_clock_horizon_and_do_not_mutate_input(self):
        f=frame();f['geometry']=spatial_features(f)[1]
        original=copy.deepcopy(f)
        pair=simulate_pair(f,None,1,[-28,14],.6,'hold',None)
        self.assertIsNotNone(pair)
        self.assertEqual(pair[0]['seconds'],pair[1]['seconds'])
        self.assertEqual(pair[0]['state']['shot_clock'],pair[1]['state']['shot_clock'])
        self.assertAlmostEqual(pair[0]['state']['shot_clock'],f['shotClock']-pair[0]['seconds'])
        self.assertEqual(f,original)

    def test_zero_movement_has_zero_scenario_difference(self):
        f=frame();f['geometry']=spatial_features(f)[1]
        target=f['offense'][1][1:3]
        for response in ('hold','momentum','close'):
            a,b=simulate_pair(f,None,1,target,.6,response,None)
            self.assertEqual(a,b)

    def test_expired_clock_is_rejected(self):
        f=frame();f['geometry']=spatial_features(f)[1];f['shotClock']=.3
        self.assertIsNone(simulate_pair(f,None,1,[-28,14],.6,'hold',None))

    def test_gain_must_survive_all_responses(self):
        self.assertIsNone(summarize([{'gain':.1},{'gain':.2},{'gain':-.01}]))
        result=summarize([{'gain':.1},{'gain':.2},{'gain':.06}])
        self.assertEqual(result['low'],.06)
        self.assertEqual(result['high'],.2)
        self.assertFalse(supported({'shot_clock':1},{'shot_clock':(2,24)}))

    def test_future_history_and_recorded_outcomes_do_not_change_simulation(self):
        f=frame();f['geometry']=spatial_features(f)[1]
        baseline=simulate_pair(f,None,1,[-28,14],.6,'momentum',None)
        f.update(epv=99,points=100,passOptions=[{'value':99}],shot={'value':999})
        future=copy.deepcopy(f);future['frame']+=5
        self.assertEqual(baseline,simulate_pair(f,future,1,[-28,14],.6,'momentum',None))

if __name__=='__main__':unittest.main()
