import unittest
from collections import Counter
from epv.defense import fit_priors
from epv.steal_risk import threat

class DefenseTest(unittest.TestCase):
    def test_excludes_displayed_game_and_shrinks_sparse_players(self):
        counts={1:(Counter({1:100,2:100}),Counter({1:10})),2:(Counter({1:10,2:100}),Counter({1:1,2:1}))}
        p,pool=fit_priors(counts,{1})
        self.assertEqual(p[1]['steals'],1)
        self.assertEqual(p[1]['defensivePossessions'],10)
        self.assertGreater(p[1]['priorPer100'],pool)
        self.assertLess(p[1]['priorPer100'],10)
        self.assertAlmostEqual(p[1]['evidenceWeight'],10/110)

    def test_prior_changes_local_threat_not_distant_or_missing_players(self):
        p={1:{'priorPer100':3},2:{'priorPer100':1}}
        self.assertEqual(threat([1],[1],p,1),2)
        self.assertEqual(threat([1],[0],p,1),0)
        self.assertEqual(threat([999],[1],p,1),0)
