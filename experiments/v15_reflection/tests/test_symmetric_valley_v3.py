"""V3 falsification tests; never equate heuristic 'verified' to actual yarn."""
from __future__ import annotations
import unittest

import cv2
import numpy as np

from experiments.v15_reflection.symmetric_valley_user_v3 import detect_and_verify_physical_yarns_v3
from experiments.v15_reflection.symmetric_valley_v3_guarded import investigate


N=600

def optical_crosshatch(a=58.,b=148.,amp2=13.):
    y,x=np.mgrid[:N,:N].astype(np.float32)
    t,u=np.deg2rad([a,b])
    v1=-x*np.sin(t)+y*np.cos(t)
    v2=-x*np.sin(u)+y*np.cos(u)
    image=145.-32.*np.cos(2*np.pi*v1/17.)-amp2*np.cos(2*np.pi*v2/29.)
    return cv2.cvtColor(np.uint8(np.clip(image,0,255)),cv2.COLOR_GRAY2BGR)


class V3CriticalControls(unittest.TestCase):
    def test_uniform_refused(self):
        v=detect_and_verify_physical_yarns_v3(np.full((N,N,3),110,np.uint8))
        self.assertFalse(v["accepted"])

    def test_pure_optical_crosshatch_is_false_positive_in_raw_v3(self):
        # Characterization test: this image is not physically woven!
        a=optical_crosshatch()
        v=detect_and_verify_physical_yarns_v3(a)
        self.assertTrue(v["accepted"])
        self.assertEqual(v["reject_reason"],"verified")
        guarded=investigate(a)
        self.assertFalse(guarded["is_physical_yarn_verified"])
        self.assertFalse(guarded["has_cross_occlusion_same_yarn_match"])
        self.assertIsNone(guarded["density_per_cm"])

    def test_measured_pitch_not_really_measured(self):
        a=optical_crosshatch()
        v=detect_and_verify_physical_yarns_v3(a)
        self.assertTrue(v["accepted"])
        self.assertIn(round(v["estimated_yarn_pitch_px"],1),{4.,6.,8.4})
        guarded=investigate(a)
        self.assertFalse(guarded["is_yarn_pitch_measured"])

    def test_crosshatch_90_degree_rotation(self):
        a=optical_crosshatch()
        v=[detect_and_verify_physical_yarns_v3(np.rot90(a,k).copy())
           for k in (0,1,2,3)]
        self.assertTrue(all(x["accepted"] for x in v))
        x=v[0]["warp_or_dom_deg"]
        for k,y in enumerate(v):
            error=abs((y["warp_or_dom_deg"]-(x+90*k)+90)%180-90)
            self.assertLess(error,1.)

if __name__=="__main__":
    unittest.main()
