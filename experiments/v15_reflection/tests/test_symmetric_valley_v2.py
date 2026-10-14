"""Synthetic regression and falsification cases for symmetric dark-valley V2.

Important: the optical-shadow test documents a false-positive, NOT a pass in
physical-yarn recognition. Tests verify that the safer API never certifies it.
"""
import unittest
import cv2
import numpy as np

from experiments.v15_reflection.symmetric_valley_user_v2 import detect_true_yarn_directions_v2
from experiments.v15_reflection.symmetric_valley_guarded import inspect_candidate, angle_distance_180


N = 600


def stripe(theta_deg, *, width=1.8, pitch=17., amplitude=22.):
    y,x=np.mgrid[:N,:N].astype(np.float32)
    t=np.deg2rad(theta_deg)
    v=-x*np.sin(t)+y*np.cos(t)
    dist=np.abs((v+pitch/2)%pitch-pitch/2)
    gray=110-amplitude*np.exp(-.5*(dist/width)**2)
    return cv2.cvtColor(np.uint8(np.clip(gray,0,255)),cv2.COLOR_GRAY2BGR)


def spots_and_optional_seams(seams=False):
    y,x=np.mgrid[:N,:N]
    a=np.ones((N,N,3),np.float32)*[115,74,35]
    t=np.deg2rad(78.)
    across=-x*np.sin(t)+y*np.cos(t)
    if seams:
        seam_distance=np.minimum(across%18.,18.-across%18.)
        a-=10*np.exp(-.5*(seam_distance/1.6)**2)[:,:,None]
    for row in range(-24,40):
        for col in range(-24,40):
            if (col-row)%4: continue
            cx=300+col*16*np.cos(t)-row*18*np.sin(t)
            cy=300+col*16*np.sin(t)+row*18*np.cos(t)
            if not (0<=cx<N and 0<=cy<N):continue
            x0=max(0,int(cx)-9);x1=min(N,int(cx)+10)
            y0=max(0,int(cy)-9);y1=min(N,int(cy)+10)
            dot=np.exp(-.5*(((x[y0:y1,x0:x1]-cx)/5)**2+
                             ((y[y0:y1,x0:x1]-cy)/4)**2))
            a[y0:y1,x0:x1]+=125*dot[:,:,None]
    return np.uint8(np.clip(a,0,255))


class SymmetricValleyV2Tests(unittest.TestCase):
    def test_uniform_rejects(self):
        v=inspect_candidate(np.full((N,N,3),110,np.uint8))
        self.assertEqual(v['status'],'ABSTAINED')
        self.assertFalse(v['is_real_yarn_verified'])

    def test_bright_float_without_seams_rejects(self):
        v=detect_true_yarn_directions_v2(spots_and_optional_seams(False))
        self.assertFalse(v['accepted'])

    def test_weak_synthetic_seams_and_quarter_turns(self):
        a=spots_and_optional_seams(True)
        for k in (0,1,2,3):
            v=inspect_candidate(np.rot90(a,k).copy())
            self.assertEqual(v['status'],'OPTICAL_DARK_VALLEY_UNVERIFIED')
            self.assertLess(angle_distance_180(v['axis_angle_deg'],(78+90*k)%180),2.)

    def test_dark_optical_stripes_are_false_positive_in_original(self):
        # There are NO yarns in this image: only geometrically symmetric
        # diagonal shadow bands. The original detector nevertheless accepts.
        raw=detect_true_yarn_directions_v2(stripe(58))
        self.assertTrue(raw['accepted'])
        self.assertLess(angle_distance_180(raw['warp_or_dom_deg'],58),1.5)
        v=inspect_candidate(stripe(58))
        self.assertTrue(v['macro_overlap_risk'])
        self.assertFalse(v['is_real_yarn_verified'])
        self.assertIsNone(v['yarn_density_cm'])

    def test_peak_median_not_probability(self):
        raw=detect_true_yarn_directions_v2(stripe(58))
        self.assertGreater(raw['confidence'],1.e6)  # unbounded histogram statistic
        self.assertFalse(inspect_candidate(stripe(58))['is_real_yarn_verified'])


if __name__=='__main__':
    unittest.main()
