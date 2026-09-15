import unittest
import numpy as np
from epv.action_defense import action_features

class ActionDefenseTest(unittest.TestCase):
    def setUp(self):
        self.f={'offense':[[1,-20,0],[2,-30,10],[8,-25,-15]],'defense':[[i,-25,i] for i in range(3,8)]}

    def test_selected_receiver_changes_pass_geometry(self):
        a=action_features(self.f,1,'steal',{},2)
        b=action_features(self.f,1,'steal',{},8)
        self.assertFalse(np.allclose(a,b))
        self.assertIsNone(action_features(self.f,1,'steal',{},1))

    def test_shot_geometry_is_current_not_future_release(self):
        a=action_features(self.f,1,'block',{})
        self.f['futureShot']={'blockerId':3,'location':[0,0]}
        np.testing.assert_allclose(a,action_features(self.f,1,'block',{}))
        self.assertAlmostEqual(a[0,4],20.75)
