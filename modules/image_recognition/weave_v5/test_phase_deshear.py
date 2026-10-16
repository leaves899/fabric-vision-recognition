"""Regression for V5 yarn-axis shear correction (no image truth used by detector).

Measured numbers below were exported from three separate V3/V4 detections
BEFORE the deshear fix. They are only regression fixtures, not model inputs.
"""
import math
import unittest
import numpy as np
from .weave_topology_v4 import corrected_phase_advance, score_models


class TestPhaseDeshear(unittest.TestCase):
    def test_affine_shear_for_2_1_and_3_1_under_rotation(self):
        for period in (3,4,5,6):
            for angle_deg in (0,13,47,90,180,270):
                for direction in (-1,1):
                    a=math.radians(angle_deg)
                    u=120*np.array([math.cos(a),math.sin(a)])
                    normal=np.array([-math.sin(a),math.cos(a)])
                    v=(120*direction/period+5.5)*u/120+47*normal
                    tilt=a+math.atan2(5.5,47)
                    raw,desheared,px=corrected_phase_advance(u,v,tilt)
                    self.assertAlmostEqual(desheared,direction/period,places=6)
                    self.assertAlmostEqual(px,5.5,places=5)

    def test_real_front_rois_rank_3_1_after_correction(self):
        # u,v,major-axis angle and median float span from independent ROIs.
        measurements=[
            ([112.603,-.331],[33.187,46.842],6.79,66.91),
            ([111.799,-.513],[33.381,47.193],6.76,64.06),
            ([111.263,-.369],[33.598,47.797],8.07,65.03),
        ]
        for u,v,angle,length in measurements:
            model=dict(repeat_vector=np.array(u),advance_vector=np.array(v),
                       observed_float_orientation_rad=math.radians(angle))
            ranks=score_models(model,[(i,length) for i in range(20)])
            self.assertEqual(ranks[0]['name'],'3/1')
            self.assertTrue(abs(ranks[0]['phase_advance']-.25)<.02)
            self.assertGreater(ranks[0]['float_axis_shear_removed_px'],5)

    def test_preserves_real_2_1_and_2_2_cases(self):
        for period,on in ((3,2),(4,3),(4,2)):
            u=np.array([120.,0.])
            v=np.array([120/period+5.5,47])
            length=(on-.4)*(120/period)
            model=dict(repeat_vector=u,advance_vector=v,
                       observed_float_orientation_rad=math.atan2(5.5,47))
            ranks=score_models(model,[(i,length) for i in range(20)])
            self.assertEqual(ranks[0]['name'],f'{on}/{period-on}')

    def test_near_singular_direction_is_not_corrected(self):
        raw,corr,removed=corrected_phase_advance([100,0],[30,50],math.radians(80))
        self.assertEqual(raw,corr)
        self.assertEqual(removed,0)

if __name__=='__main__':
    unittest.main()
