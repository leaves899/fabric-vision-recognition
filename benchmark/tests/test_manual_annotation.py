"""Synthetic-only tests. No real fabric GT or algorithm accuracy is asserted."""
import csv
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from benchmark.dataset import MANIFEST_FIELDS
from benchmark.manual_annotation import (
    audit, segment_axis_deg, store_annotation, validate_annotation,
)
from benchmark.run_annotated_v5 import check_segments, run


class AnnotationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        folder = self.root / "datasets/public_samples/images/twill"
        folder.mkdir(parents=True)
        self.image_path = "datasets/public_samples/images/twill/01_synth.jpg"
        Image.new("RGB", (500, 250), (40, 100, 155)).save(self.root / self.image_path)
        with (self.root / "datasets/manifest.csv").open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=MANIFEST_FIELDS)
            writer.writeheader()
            writer.writerow(dict(zip(MANIFEST_FIELDS, [
                "PUBLIC-T001", "T001", "UNKNOWN", "DEV", "PUBLIC_UNKNOWN",
                self.image_path, "", "NONE", "NO", "synthetic"
            ])))
        self.annotation = {
            "schema_version":"1.0", "sample_id":"T001", "image_path":self.image_path,
            "eligibility":"DENIM_CANDIDATE", "review_state":"OPERATOR_REVIEWED",
            "reference_confirmed": True, "reference_family":"UNKNOWN",
            "identity_confirmed": False,
            "segments":{
                "reference":[[20,40],[180,40]],
                "check_same":[[20,100],[180,100]],
                "check_cross":[[80,20],[80,210]]
            }, "notes":"synthetic only"
        }

    def test_valid_annotation_has_original_hash_and_axis(self):
        data = validate_annotation(self.root, self.annotation)
        self.assertEqual(data["image_width"], 500)
        self.assertEqual(len(data["image_sha256"]), 64)
        self.assertAlmostEqual(segment_axis_deg(data["segments"]["reference"]), 0)

    def test_persist_and_audit(self):
        out = store_annotation(self.root, self.annotation)
        self.assertEqual(out["review_state"], "OPERATOR_REVIEWED")
        report = audit(self.root)
        self.assertEqual(report["ready_for_v5"], ["T001"])
        self.assertEqual(report["not_started"], 0)

    def test_must_confirm_reference_before_review(self):
        self.annotation["reference_confirmed"] = False
        with self.assertRaises(ValueError):
            validate_annotation(self.root, self.annotation)

    def test_coordinates_in_original_image(self):
        self.annotation["segments"]["reference"] = [[20, 40], [600, 40]]
        with self.assertRaisesRegex(ValueError, "outside"):
            validate_annotation(self.root, self.annotation)

    def test_small_reference_is_not_valid(self):
        self.annotation["segments"]["reference"] = [[20, 40], [30, 40]]
        with self.assertRaisesRegex(ValueError, "shorter"):
            validate_annotation(self.root, self.annotation)

    def test_identity_must_be_confirmed_separately(self):
        self.annotation["reference_family"] = "WARP"
        with self.assertRaisesRegex(ValueError, "identity"):
            validate_annotation(self.root, self.annotation)

    def test_reject_stale_image_hash(self):
        self.annotation["image_sha256"] = "f"*64
        with self.assertRaisesRegex(ValueError, "hash"):
            validate_annotation(self.root, self.annotation)

    def test_validation_segment_cannot_equal_input_reference(self):
        self.annotation["segments"]["check_same"] = self.annotation["segments"]["reference"][:]
        with self.assertRaisesRegex(ValueError, "DIFFERENT"):
            validate_annotation(self.root, self.annotation)

    def test_non_denim_does_not_get_reviewed_as_denim(self):
        self.annotation["eligibility"] = "NEGATIVE_NON_DENIM"
        with self.assertRaisesRegex(ValueError, "non-denim"):
            validate_annotation(self.root, self.annotation)

    def test_candidate_axes_compared_only_with_other_segments(self):
        fake = {"direction_evidence":{"family_a_deg":179, "family_b_deg":90}}
        self.annotation["segments"]["check_same"] = [[30,90],[200,93]]
        errors = check_segments(fake,self.annotation)
        self.assertGreater(errors["independent_same_error_deg"], 0)
        self.assertAlmostEqual(errors["independent_cross_error_deg"], 0)

    def test_no_reviewed_label_returns_not_evaluated(self):
        with tempfile.TemporaryDirectory() as td:
            summary = run(self.root, Path(td), ["T001"], 1)
            self.assertEqual(summary["status"], "NOT_EVALUATED")
            self.assertEqual(summary["completed"], 0)
            self.assertTrue((Path(td)/"comparison.csv").is_file())


if __name__ == "__main__":
    unittest.main()
