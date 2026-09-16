import unittest
import pandas as pd
from epv.foul_value import components, geometry, FoulModel, FEATURES


class FoulValueTests(unittest.TestCase):
    def test_branch_accounting(self):
        c = components(.5, 2, .2, .1, .8, .4)
        self.assertAlmostEqual(c['expectedFta'], .25)
        self.assertAlmostEqual(c['freeThrowValue'], .2)
        self.assertAlmostEqual(c['secondChancePerShot'], .16)
        self.assertAlmostEqual(c['shotPlusSecondChance'], 1.36)
        self.assertAlmostEqual(c['foulProbability']*c['fouledPps']+(1-c['foulProbability'])*c['notFouledPps'],1.36)

    def test_ft_rebounds_count_only_the_final_attempt_and_branch_weights_reconcile(self):
        c=components(.5,3,.2,.1,.8,.4,.12,1.1)
        self.assertAlmostEqual(c['ftSecondChanceIfFouled'],.2*.12*1.1)
        self.assertAlmostEqual(c['ftSecondChancePerShot'],.15*.2*.12*1.1)
        self.assertAlmostEqual(c['foulProbability']*c['fouledPps']+(1-c['foulProbability'])*c['notFouledPps'],c['shotPlusSecondChance'])
        self.assertIsNone(components(1,2,0,0,.8,.4)['fouledPps'])
        self.assertIsNone(components(0,2,1,1,.8,.4)['notFouledPps'])

    def test_foul_miss_has_no_live_rebound_and_andone_is_one(self):
        self.assertEqual(components(0, 3, 1, 1, 1, 2)['shotPlusSecondChance'], 3)
        self.assertEqual(components(1, 3, 1, 1, 1, 2)['shotPlusSecondChance'], 4)
        self.assertIsNone(components(.5, 2, .2, .1, .8, None)['shotPlusSecondChance'])

    def test_geometry_ignores_outcome_and_labels(self):
        f = dict(offense=[[1, -30, 2]], defense=[[2,-31,2],[3,-25,3],[4,0,0],[5,3,3],[6,5,5]],shotClock=12)
        self.assertEqual(geometry(f,1),geometry(dict(f,outcome=True,fouled=True),1))
        self.assertEqual(geometry(f,1)['defender_distance'],1)
        self.assertIsNone(geometry(f,99))

    def test_player_ft_accuracy_and_outcome_independence(self):
        rows = [dict.fromkeys(FEATURES, 2.) | dict(gameId=1, shooter=str(i%3), made=i%2, fouled=int(i%5==0)) for i in range(60)]
        data = pd.DataFrame(rows)
        ft = pd.DataFrame([dict(shooter='0',made=i%2) for i in range(10)])
        model = FoulModel(data,ft,{'0':dict(season_ftr=.2,ft_rate=.9),'1':dict(season_ftr=.4,ft_rate=.6)})
        sample = data.iloc[:2].copy()
        before = model.predict(sample)
        self.assertEqual(list(before[2]),[.9,.6])
        sample['made'] = 1-sample.made
        sample['fouled'] = 1-sample.fouled
        after = model.predict(sample)
        self.assertTrue(all((a==b).all() for a,b in zip(before,after)))
