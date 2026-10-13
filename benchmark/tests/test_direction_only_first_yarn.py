"""Direction-only semantics and synthetic evidence tests; never assert yarn truth on photos."""
import unittest
import numpy as np
import cv2

from benchmark.direction_only_first_yarn import (
    synthetic_direction_line, score_profile, central_native_crop
)
from benchmark.first_yarn_evidence import diagnostic_one


class DirectionOnlyFirstYarnTests(unittest.TestCase):
    def test_image_center_is_not_reference_position(self):
        frame=np.zeros((1024,900,3),dtype=np.uint8)
        self.assertEqual(tuple(central_native_crop(frame)[0].shape[:2]),(750,750))
        a=synthetic_direction_line((750,750,3),22)
        b=synthetic_direction_line((750,750,3),22)
        np.testing.assert_array_equal(a,b)
        np.testing.assert_allclose(a.mean(axis=0),[375,375])

    def test_no_texture_abstains(self):
        frame=np.full((600,600,3),120,np.uint8)
        record,visual=score_profile(frame,0)
        self.assertEqual(record["status"],"ABSTAIN_NO_CONSISTENT_IMAGE_RIDGES")
        self.assertIsNone(visual)

    def test_consistent_synthetic_horizontal_threads_generate_only_candidates(self):
        yy=np.arange(640)[:,None]
        xx=np.arange(640)[None,:]
        delta=((yy-22+16)%32)-16
        ridge=np.exp(-.5*(delta/4)**2)
        variation=.8+.2*np.sin(xx/29)**2
        z=np.uint8(np.clip(70+155*ridge*variation,0,255))
        img=cv2.merge([z,z,z])
        result,visual=score_profile(img,0)
        self.assertEqual(result["status"],"IMAGE_TEXTURE_RIDGE_CANDIDATES_REQUIRE_YARN_CONFIRMATION",result)
        self.assertGreaterEqual(result["image_only_candidate_ridge_count"],5,result)
        self.assertFalse(result["physical_yarn_centers_verified"])

    def test_same_angle_different_user_line_position_cannot_affect_image_candidates(self):
        img=np.full((350,350,3),90,np.uint8)
        # Both examples infer exactly the SAME angle despite different drawn location.
        a=[[5,20],[205,20]]
        b=[[70,260],[270,260]]
        from benchmark.first_yarn_evidence import axis_deg
        p1,_=score_profile(img,axis_deg(a))
        p2,_=score_profile(img,axis_deg(b))
        self.assertEqual(p1,p2)

    def test_previous_physical_center_experiment_abstains(self):
        ann={"sample_id":"U20261013_01",
             "segments":{"reference":[[30,60],[250,90]]}}
        record,data=diagnostic_one(ann,np.full((320,320,3),120,np.uint8))
        self.assertEqual(record["status"],"INVALIDATED_DIRECTION_ONLY_ANNOTATION")
        self.assertIsNone(data)
        self.assertFalse(record["physical_yarn_center_gt_available"])


if __name__=="__main__":
    unittest.main()
