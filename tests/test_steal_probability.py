import unittest
import numpy as np
from epv.steal_probability import JointStealModel, geometry

class JointStealTest(unittest.TestCase):
    def test_probabilities_sum_to_one_and_follow_player_order(self):
        rng=np.random.default_rng(7);x=rng.normal(size=(120,5,6));y=np.zeros(120,dtype=int);y[:15]=1
        m=JointStealModel().fit(x,y);p=m.predict(x)
        np.testing.assert_allclose(p.sum(axis=1),1)
        self.assertTrue(np.all((p>=0)&(p<=1)))
        permutation=[3,0,4,1,2]
        swapped=m.predict(x[:,permutation,:])
        np.testing.assert_allclose(swapped[:,0],p[:,0])
        np.testing.assert_allclose(swapped[:,1:],p[:,1:][:,permutation])

    def test_geometry_ignores_future_forecasts_and_outcomes(self):
        f={'frame':100,'period':1,'geometry':{'handler':1},'ball':[-20,0,3], 'offense':[[1,-20,0],[2,-30,10]],'defense':[[k,-25,k] for k in range(3,8)]}
        a=geometry(f,None)
        f['stealForecast']={'anyStealProbability':1};f['outcome']='steal'
        np.testing.assert_allclose(a,geometry(f,None))
