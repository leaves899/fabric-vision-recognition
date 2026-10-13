"""Annotation semantics and three-stage geometric evaluation contracts.

Synthetic images validate implementation only. Operator-inferred tracks are not
automatically promoted to pixelwise physically visible yarn GT.
"""
import json
import unittest
from pathlib import Path

import cv2
import numpy as np

from benchmark.manual_annotation import annotation_target_for,validate_annotation
from benchmark.direction_only_first_yarn import score_profile, axis_deg
from benchmark.first_yarn_three_stage import evaluate_centers, analyze_sample

ROOT=Path(__file__).resolve().parents[2]


class PhysicalYarnTrajectoryTests(unittest.TestCase):
    def test_batch_target_is_true_physical_yarn_not_visible_segment(self):
        self.assertEqual(annotation_target_for("U20261013_01"),"PHYSICAL_YARN_TRAJECTORY")
        self.assertEqual(annotation_target_for("T004"),"UNSPECIFIED")
        with self.assertRaisesRegex(ValueError,"PHYSICAL_YARN_TRAJECTORY"):
            annotation_target_for("U20261013_02","VISIBLE_YARN_SEGMENT")

    def test_five_operator_files_and_native_coordinates_preserved(self):
        for n in ("01","02","03","05","06"):
            path=ROOT/"datasets/annotations/drafts"/f"U20261013_{n}.json"
            raw=json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(raw["annotation_target"],"PHYSICAL_YARN_TRAJECTORY")
            self.assertTrue(raw["path_may_cross_occlusion"])
            self.assertFalse(raw["visible_pixel_gt_confirmed"])
            self.assertFalse(raw["centerline_pixel_gt_confirmed"])
            result=validate_annotation(ROOT,raw)
            self.assertEqual(result["segments"],raw["segments"])
            self.assertEqual(result["coordinate_space"],"ZOOM_2X_NATIVE_PIXELS")
            self.assertEqual(result["annotation_target"],"PHYSICAL_YARN_TRAJECTORY")
            self.assertEqual(result["image_sha256"],raw["image_sha256"])

    def test_cannot_invent_visible_pixel_gt_for_occluded_trajectory(self):
        p=ROOT/"datasets/annotations/drafts/U20261013_01.json"
        raw=json.loads(p.read_text(encoding="utf-8"))
        raw["visible_pixel_gt_confirmed"]=True
        with self.assertRaisesRegex(ValueError,"visible pixel"):
            validate_annotation(ROOT,raw)
        raw["visible_pixel_gt_confirmed"]=False
        raw["centerline_pixel_gt_confirmed"]=True
        with self.assertRaisesRegex(ValueError,"pixel centerline"):
            validate_annotation(ROOT,raw)

    def test_synthetic_periodic_texture_remains_unverified_even_if_correct_axis(self):
        y=np.arange(700)[:,None]
        x=np.arange(700)[None,:]
        ribbon=np.exp(-((y-24+16)%32-16)**2/(2*4.**2))
        val=np.clip(75+140*ribbon*(.75+.25*np.sin(x/31)**2),0,255).astype(np.uint8)
        bgr=cv2.merge([val,val,val])
        result,visual=score_profile(bgr,0,approximate_roi_center=[350,350])
        self.assertIn(result["status"],["IMAGE_TEXTURE_RIDGE_CANDIDATES_REQUIRE_YARN_CONFIRMATION",
                                        "ABSTAIN_NO_CONSISTENT_IMAGE_RIDGES"])
        self.assertFalse(result["physical_yarn_centers_verified"])
        if visual is not None:
            # The manually inferred fiber center can agree with photo texture
            # and STILL not establish yarn identity.
            ann={"segments":{"reference":[[100,120],[600,120]],
                             "check_same":[[100,216],[600,216]],
                             "holdout_same":[[100,312],[600,312]]},
                 "same_family_intervals":3}
            check=evaluate_centers(ann,visual,result)
            self.assertFalse(check["physical_center_pixel_gt"])
            self.assertTrue(check["counts_are_hypotheses_not_real_yarn_count"])

    def test_blank_image_never_outputs_physical_count(self):
        img=np.full((600,600,3),128,np.uint8)
        ann={"sample_id":"SYNTH","annotation_target":"PHYSICAL_YARN_TRAJECTORY",
             "image_sha256":"synthetic","segments":{
                "reference":[[50,120],[500,120]],
                "check_same":[[50,216],[500,216]],
                "holdout_same":[[50,312],[500,312]]},
             "same_family_intervals":3}
        result,visual,_=analyze_sample(ann,img)
        self.assertEqual(result["decision"],"ABSTAIN_NOT_ENOUGH_VISIBLE_YARN_PIXEL_GT")
        self.assertIsNone(result["validated_physical_yarn_center_count"])
        self.assertIsNone(result["density_per_cm"])
        self.assertEqual(result["step_C"]["status"],"ABSTAIN_NO_IMAGE_STRUCTURE")


if __name__=="__main__":
    unittest.main()
