"""Deterministic synthetic checks; passing does not validate real yarn identity."""
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from pure10.engine import analyze, PARAMETERS, _axis_error
from pure10.evaluate_six import _spacing, _mean_axis


class PhysicalAnnotationSemantics(unittest.TestCase):
    def test_interval_distance_not_necessarily_adjacent(self):
        line1 = [[10, 5],[100, 5]]
        line2 = [[10, 45],[100, 45]]
        self.assertAlmostEqual(_spacing(line1, line2, 4), 10.)
        self.assertAlmostEqual(_spacing(line1, line2, 2), 20.)

    def test_rotated_different_trajectories_are_not_segments(self):
        first = [[10, 30],[100, 60]]
        other = [[10, 60],[100, 90]]
        self.assertAlmostEqual(_spacing(first, other, 3),
                               30/(1+(1/3)**2)**.5/3, places=4)

    def test_axis_mod_180(self):
        self.assertAlmostEqual(_axis_error(179,1),2)
        self.assertAlmostEqual(_mean_axis([179,1,0]),0,places=5)


class PureEngine(unittest.TestCase):
    @staticmethod
    def synthetic():
        y,x=np.mgrid[:576,:576]
        # Two genuine orthogonal repeated structures; no training labels.
        img=np.zeros((576,576,3),np.uint8)
        periodic=(np.sin(2*np.pi*x/18)>0.45).astype(float)*33
        periodic+=(np.sin(2*np.pi*y/23)>0.50).astype(float)*47
        img[:,:,:]=np.clip(80+periodic[...,None]+
                            12*np.sin((x+y)/65)[...,None],0,255)
        return img

    def test_ten_parameter_keys_and_abstention(self):
        with tempfile.TemporaryDirectory() as t:
            image=Path(t)/"test.png"
            cv2.imwrite(str(image),self.synthetic())
            res=analyze(image)
            self.assertEqual(set(res["parameters"]),set(PARAMETERS))
            self.assertFalse(res["annotation_used_in_inference"])
            self.assertEqual(res["physical_calibration"],"UNAVAILABLE")
            for key in ("warp_density_per_cm","weft_density_per_cm",
                        "weave_structure","warp_direction_angle",
                        "weft_direction_angle"):
                self.assertEqual(res["parameters"][key]["status"],"UNAVAILABLE")
            self.assertEqual(res["parameters"]["surface_texture_and_color"]["status"],
                             "CANDIDATE")

    def test_fixed_scale_is_only_from_supplied_frame_corners(self):
        with tempfile.TemporaryDirectory() as t:
            image=Path(t)/"test.png"
            cv2.imwrite(str(image),self.synthetic())
            corners=[[0,0],[575,0],[575,575],[0,575]]
            res=analyze(image,warp_family="a",corners=corners)
            self.assertEqual(res["physical_calibration"],"provided_5cm_corners")
            self.assertEqual(res["yarn_identity"],"operator_selected")
            self.assertEqual(set(res["parameters"]),set(PARAMETERS))
            # Physical densities are CANDIDATE or UNAVAILABLE, NEVER CONFIRMED.
            self.assertNotEqual(res["parameters"]["warp_density_per_cm"]["status"],
                                "CONFIRMED")


if __name__=="__main__":
    unittest.main()
