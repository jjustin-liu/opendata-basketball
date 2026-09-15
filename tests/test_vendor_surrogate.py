import unittest
import numpy as np
import pandas as pd
from epv.vendor_surrogate import features, fit, season_evidence
from epv.shooting import SHOT_FEATURES

class VendorSurrogateTest(unittest.TestCase):
    def test_geometry_uses_holder_and_current_defenders(self):
        f={'offense':[[1,-30,0]],'defense':[[2,-27,4]],'shotClock':10}
        self.assertEqual(features(f,1),[10.75,5.,0,10])
        self.assertIsNone(features(f,3))

    def test_make_outcome_does_not_change_score_fit(self):
        x=pd.DataFrame({k:np.linspace(1,20,30) for k in SHOT_FEATURES})
        x['vendorQuality']=np.linspace(20,80,30);x['made']=0;x['shooter']=1
        a=fit(x).predict(x[SHOT_FEATURES].to_numpy())
        x['made']=1
        np.testing.assert_allclose(a,fit(x).predict(x[SHOT_FEATURES].to_numpy()))

    def test_long_threes_cannot_gain_from_distance_or_extreme_openness(self):
        x=pd.DataFrame({k:np.linspace(1,30,60) for k in SHOT_FEATURES})
        x['vendorQuality']=np.linspace(80,20,60);x['shooter']=1;x['three']=True
        m=fit(x)
        states=np.array([[d,g,2,15] for g in [9,15,25] for d in [24,27,30,32]])
        p=m.predict(states,[1]*12,[True]*12).reshape(3,4)
        self.assertTrue(np.all(np.diff(p,axis=1)<=1e-9))
        np.testing.assert_allclose(p[0],p[1]);np.testing.assert_allclose(p[0],p[2])

    def test_season_prior_excludes_current_game(self):
        e=season_evidence({'players':{'1':{'sampleFga':211,'sampleThreePa':5}},'shotAttempts':[{'player':1,'three':False},{'player':1,'three':True}]})[1]
        self.assertEqual(e['attempts'],4)
        self.assertAlmostEqual(e['rate'],4/209)

    def test_three_fit_does_not_learn_easy_twos(self):
        three=pd.DataFrame({k:np.linspace(23,30,60) for k in SHOT_FEATURES})
        three['vendorQuality']=30;three['shooter']=1;three['three']=True
        two=three.copy();two['three']=False;two['shot_distance']=2;two['vendorQuality']=90
        data=pd.concat([three,two],ignore_index=True)
        a=fit(data).predict([[25,9,2,15]],[1],[True])
        data.loc[~data.three,'vendorQuality']=10
        b=fit(data).predict([[25,9,2,15]],[1],[True])
        np.testing.assert_allclose(a,b)
