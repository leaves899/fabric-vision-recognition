from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from benchmark.dataset import GROUND_TRUTH_FIELDS, MANIFEST_FIELDS, load_csv, validate
from benchmark.public_intake import prepare, write_csv


class PublicIntakeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "datasets/public_samples/images/plain").mkdir(parents=True)
        self.catalog = self.root / "sources.json"
        self.manifest = self.root / "manifest.csv"
        self.gt = self.root / "ground_truth.csv"
        write_csv(self.manifest, MANIFEST_FIELDS, [])
        write_csv(self.gt, GROUND_TRUTH_FIELDS, [])
        self.items = [
            {"id": "P001", "path": "plain/p1.jpg", "source_page": "https://example.org/p1", "license": "CC0", "weave_candidate": "plain"},
            {"id": "P002", "path": "plain/p2.jpg", "source_page": "https://example.org/p2", "license": "CC0", "weave_candidate": "twill"},
        ]
        self.catalog.write_text(json.dumps({"items": self.items}), encoding="utf-8")
        (self.root / "datasets/public_samples/images/plain/p1.jpg").write_bytes(b"fake jpeg bytes")

    def intake(self):
        return prepare(self.root, self.catalog, self.manifest, self.gt)

    def test_only_present_photo_and_no_made_up_gt(self):
        manifest, truth, report = self.intake()
        self.assertEqual(report["present_images"], 1)
        self.assertEqual(report["pending_image_download"], ["P002"])
        self.assertEqual(manifest[0]["face"], "UNKNOWN")
        self.assertEqual(manifest[0]["calibration_type"], "NONE")
        self.assertEqual(manifest[0]["capture_mode"], "PUBLIC_UNKNOWN")
        self.assertEqual(truth[0]["review_status"], "NOT_EVALUATED")
        self.assertEqual(truth[0]["weave_type"], "")
        self.assertEqual(truth[0]["warp_density_per_cm"], "")
        self.assertEqual(report["validation"]["errors"], [])

    def test_idempotent_incremental_and_gt_preserved(self):
        manifest, truth, _ = self.intake()
        write_csv(self.manifest, MANIFEST_FIELDS, manifest)
        write_csv(self.gt, GROUND_TRUTH_FIELDS, truth)
        second_manifest, second_gt, report = self.intake()
        self.assertEqual(report["added"], [])
        self.assertEqual(report["already_registered"], ["P001"])
        self.assertEqual(len(second_manifest), 1)
        # Simulate human-entered label before a new photo arrives.
        truth[0]["gt_source"] = "reviewed_by_operator"
        truth[0]["review_status"] = "DRAFT"
        write_csv(self.gt, GROUND_TRUTH_FIELDS, truth)
        (self.root / "datasets/public_samples/images/plain/p2.jpg").write_bytes(b"fake jpeg bytes")
        final_manifest, final_gt, report = self.intake()
        self.assertEqual(report["added"], ["P002"])
        self.assertEqual(len(final_manifest), 2)
        self.assertEqual(final_gt[0]["review_status"], "DRAFT")
        self.assertEqual(final_gt[1]["weave_type"], "")

    def test_duplicate_catalog_id_fails(self):
        self.catalog.write_text(json.dumps({"items": self.items * 2}), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "duplicate source ID"):
            self.intake()

    def test_traversal_is_rejected(self):
        self.items[0]["path"] = "../../outside.jpg"
        self.catalog.write_text(json.dumps({"items": self.items}), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "invalid image path"):
            self.intake()

    def test_missing_license_blocks_intake(self):
        self.items[0].pop("license")
        self.catalog.write_text(json.dumps({"items": self.items}), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "licensing"):
            self.intake()

if __name__ == "__main__":
    unittest.main()
