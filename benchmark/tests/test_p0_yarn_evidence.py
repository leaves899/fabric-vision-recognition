"""Fail-closed P0-1 tests: optical evidence is NOT physical-yarn identity GT."""
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from benchmark.p0_yarn_evidence import (
    evidence_for_site, validate_physical_evidence_labels,
    extract_patch, gallery_triptych, sample_gallery_center,
)


def site(supported=True):
    return {"nominal_physical_yarn_index":7,
            "nominal_y_2x_px":120.,
            "image_evidence_supported":supported,
            "linear_drift_corrected_center_jitter_2x_px":1.2,
            "candidate_supported_short_runs_zoom_native_xy":[[[80.,118.],[150.,120.],[220.,121.]]]
                if supported else [],
            "local_observations":[{"x":i*20.,"y":120+i*.1,
                 "supported":bool(supported),"paired_flank_score":0.7 if supported else 0.}
                 for i in range(9)]}


class P0PhysicalEvidenceTests(unittest.TestCase):
    def test_strong_image_evidence_never_becomes_yarn_probability(self):
        candidate=evidence_for_site("U20261013_01",site(),32)
        self.assertGreater(candidate["image_evidence_score"],.7)
        self.assertEqual(candidate["identity_hypothesis"],"UNKNOWN")
        self.assertIsNone(candidate["physical_identity_probability"])
        self.assertFalse(candidate["physical_identity_verified"])
        self.assertFalse(candidate["count_eligible"])
        self.assertIn("YARN",candidate["competing_explanations"])
        self.assertIn("TWILL",candidate["competing_explanations"])
        self.assertIsNone(candidate["evidence"]["fiber_morphology"])
        self.assertIsNone(candidate["evidence"]["crossing_occlusion_topology"])

    def test_weak_image_evidence_does_not_manufacture_ground_truth(self):
        candidate=evidence_for_site("U20261013_05",site(False),32)
        self.assertEqual(candidate["identity_status"],"REJECTED_INSUFFICIENT_IMAGE_EVIDENCE")
        self.assertFalse(candidate["count_eligible"])
        self.assertIsNone(candidate["physical_identity_probability"])

    def test_empty_external_gt_is_allowed_and_explicit(self):
        self.assertEqual(validate_physical_evidence_labels(
            {"schema_version":"1.0","labels":[]}),[])

    def test_photo_only_annotation_must_not_be_physical_gt(self):
        sample={"candidate_id":"U20261013_01:A:0","sample_id":"U20261013_01",
                "physical_fabric_id":"F01","image_sha256":"abc",
                "label":"PHYSICAL_YARN_VISIBLE",
                "evidence_source":"PHONE_IMAGE_ONLY","reviewer":"R01",
                "independent_review":True}
        with self.assertRaisesRegex(ValueError,"PHONE_ONLY"):
            validate_physical_evidence_labels({"schema_version":"1.0","labels":[sample]})
        sample["evidence_source"]="MICROSCOPE_PHYSICAL_CONFIRMATION"
        self.assertEqual(len(validate_physical_evidence_labels(
            {"schema_version":"1.0","labels":[sample]})),1)
        with self.assertRaisesRegex(ValueError,"duplicate candidate"):
            validate_physical_evidence_labels(
                {"schema_version":"1.0","labels":[sample,sample]})
        sample["independent_review"]=False
        with self.assertRaises(ValueError):
            validate_physical_evidence_labels({"schema_version":"1.0","labels":[sample]})

    def test_no_implicit_negative_half_pitch(self):
        gray=np.full((140,140,3),100,np.uint8)
        for y in (28,60,92,124):
            cv2.line(gray,(0,y),(139,y),(180,180,180),6)
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/"patch.jpg"
            gallery_triptych(gray,[65.,60.],[0,1],32,"F01:A:1",output)
            triptych=cv2.imread(str(output))
            self.assertIsNotNone(triptych)
            self.assertEqual(triptych.shape[:2],(160,336))
            # The output has labels "unlabeled side"; no false-negative label.

    def test_crop_outside_actual_image_uses_zero_not_mirror(self):
        source=np.full((50,50,3),143,np.uint8)
        cut=extract_patch(source,[3,3],side=40)
        self.assertEqual(cut.shape,(40,40,3))
        self.assertTrue(np.all(cut[0,0]==0))
        self.assertTrue(np.all(cut[20,20]==143))

    def test_candidate_gallery_center_from_actual_short_run(self):
        s=site()
        xy=sample_gallery_center(s,None)
        self.assertAlmostEqual(xy[0],150)
        self.assertAlmostEqual(xy[1],119.666666,places=3)


if __name__=="__main__":
    unittest.main()
