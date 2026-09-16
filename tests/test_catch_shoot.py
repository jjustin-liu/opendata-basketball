import unittest
from epv.catch_shoot import project_release, catch_shoot_value

class CatchShootTest(unittest.TestCase):
    def test_cs_contains_only_field_goal_and_rebound_value(self):
        v=catch_shoot_value(.3,3,.2,1.1)
        self.assertAlmostEqual(v['pps'],1.054)
        self.assertAlmostEqual(v['firstChancePps'],.9)
        self.assertAlmostEqual(v['secondChanceValue'],.154)
        self.assertEqual(catch_shoot_value(1,3,.2,1.1)['secondChanceValue'],0)
    def test_closeout_clock_and_immutable_source(self):
        option=dict(player=1,arrivalSeconds=.7,offense=[[1,0,0]],defense=[[2,8,0],[3,12,0],[4,15,0],[5,20,0],[6,25,0]])
        state=project_release(dict(shotClock=10),option)
        self.assertAlmostEqual(state['shotClock'],8.8)
        self.assertAlmostEqual(state['defense'][0][1],4.4)
        self.assertEqual(option['defense'][0][1],8)
        self.assertIsNone(project_release(dict(shotClock=1),option))
