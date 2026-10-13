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
from benchmark.first_yarn_three_stage import (evaluate_centers,analyze_sample,bilateral_boundary_evidence,two_physical_yarn_anchor_hypothesis)

ROOT=Path(__file__).resolve().parents[2]


class PhysicalYarnTrajectoryTests(unittest.TestCase):
    def test_batch_target_is_true_physical_yarn_not_visible_segment(self):
        self.assertEqual(annotation_target_for("U20261013_01"),"PHYSICAL_YARN_REFERENCE")
        self.assertEqual(annotation_target_for("T004"),"UNSPECIFIED")
        self.assertEqual(annotation_target_for("U20261013_01","PHYSICAL_YARN_TRAJECTORY"),"PHYSICAL_YARN_REFERENCE")
        with self.assertRaisesRegex(ValueError,"PHYSICAL_YARN_REFERENCE"):
            annotation_target_for("U20261013_02","VISIBLE_YARN_SEGMENT")

    def test_five_operator_files_and_native_coordinates_preserved(self):
        for n in ("01","02","03","05","06"):
            path=ROOT/"datasets/annotations/drafts"/f"U20261013_{n}.json"
            raw=json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(raw["annotation_target"],"PHYSICAL_YARN_REFERENCE")
            self.assertTrue(raw["path_may_cross_occlusion"])
            self.assertFalse(raw["visible_pixel_gt_confirmed"])
            self.assertFalse(raw["centerline_pixel_gt_confirmed"])
            result=validate_annotation(ROOT,raw)
            self.assertEqual(result["segments"],raw["segments"])
            self.assertEqual(result["coordinate_space"],"ZOOM_2X_NATIVE_PIXELS")
            self.assertEqual(result["annotation_target"],"PHYSICAL_YARN_REFERENCE")
            self.assertEqual(result["annotation_semantics"],"PHYSICAL_YARN_REFERENCE")
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

    def test_paired_flanks_are_optical_evidence_not_real_yarn_certificate(self):
        xx=np.arange(500)[None,:]
        yy=np.arange(500)[:,None]
        ridges=np.exp(-(((yy-14+18)%36)-18)**2/(2*5.**2))
        z=np.uint8(np.clip(65+150*ridges*(.8+.2*np.sin(xx/23)**2),0,255))
        img=cv2.merge([z,z,z])
        guess,visual=score_profile(img,0,approximate_roi_center=[250,250])
        rows=bilateral_boundary_evidence(visual,guess)
        self.assertFalse(rows.get("physical_yarn_identity_certified",False))
        if visual is not None:
            self.assertGreater(len(rows["candidate_bilateral_support"]),0)
            for rec in rows["candidate_bilateral_support"]:
                self.assertGreaterEqual(rec["two_sided_boundary_support_ratio"],0)
                self.assertLessEqual(rec["two_sided_boundary_support_ratio"],1)

    def test_two_actual_yarn_anchors_calibrate_candidate_pitch_third_is_holdout(self):
        ann={"segments":{"reference":[[30,100],[300,100]],
                         "check_same":[[30,220],[300,220]],
                         "holdout_same":[[30,340],[300,340]]},
             "same_family_intervals":3,"same_family_intervals_confirmed":True}
        matrix=np.array([[1.,0,0],[0,1.,0]],float)
        visual=(np.zeros((480,480,3),np.uint8),
                list(range(20,460,40)),matrix,np.array([0,0],float))
        report=two_physical_yarn_anchor_hypothesis(ann,visual)
        self.assertEqual(report["inferred_nominal_physical_pitch_px"],40)
        self.assertFalse(report["third_real_yarn_heldout"]["was_used_to_calibrate"])
        self.assertEqual(report["third_real_yarn_heldout"]["residual_as_fraction_of_nominal_pitch"],0)
        self.assertFalse(report["automatic_real_yarn_count_certified"])
        self.assertEqual(report["third_real_yarn_heldout"]["evaluation_role"],
                         "A3_INDEPENDENT_APPROXIMATE_PHYSICAL_YARN_REFERENCE")
        snapshot=report["approximate_candidate_targets"]
        ann["segments"]["holdout_same"]=[[30,357],[300,357]]
        moved=two_physical_yarn_anchor_hypothesis(ann,visual)
        self.assertEqual(moved["approximate_candidate_targets"],snapshot)
        self.assertEqual(moved["inferred_nominal_physical_pitch_px"],40)
        self.assertNotEqual(moved["third_real_yarn_heldout"]["approximate_geometry_residual_px"],
                            report["third_real_yarn_heldout"]["approximate_geometry_residual_px"])
        self.assertEqual(report["grid_site_count"],len(report["approximate_candidate_targets"]))
        self.assertFalse(report["third_real_yarn_heldout"]["pixel_centerline_ground_truth"])
        # Both physical fiber anchors constrain the lattice but no photo peak
        # can ever be claimed to be certified as the real yarn.
        self.assertTrue(all(not t["actual_visible_yarn_confirmed"] for t in report["approximate_candidate_targets"]))
        ann["same_family_intervals_confirmed"]=False
        self.assertTrue(two_physical_yarn_anchor_hypothesis(ann,visual)["status"].startswith("ABSTAIN"))

    def test_blank_image_never_outputs_physical_count(self):
        img=np.full((600,600,3),128,np.uint8)
        ann={"sample_id":"SYNTH","annotation_target":"PHYSICAL_YARN_REFERENCE",
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
