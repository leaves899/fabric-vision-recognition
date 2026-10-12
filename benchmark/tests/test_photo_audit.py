"""Synthetic image-only tests; no textile GT and no recognition-accuracy claims."""
from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from benchmark.dataset import MANIFEST_FIELDS, GROUND_TRUTH_FIELDS
from benchmark.photo_audit import analyze, inspect_image, quantile


def save_csv(path: Path, fields, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


class PhotoAuditTests(unittest.TestCase):
    def test_grayscale_quantile(self):
        self.assertEqual(quantile([2, 2, 6], 0.5), 2)
        self.assertEqual(quantile([2, 2, 6], 0.1), 0)
        with self.assertRaises(ValueError):
            quantile([], 0.5)

    def test_native_size_and_sha_of_real_generated_image(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "synthetic.png"
            Image.new("RGB", (1200, 1050), (127, 127, 127)).save(path)
            result = inspect_image(path)
            self.assertEqual(result["native_width"], 1200)
            self.assertEqual(result["native_height"], 1050)
            self.assertEqual(result["container"], "PNG")
            self.assertIn("LOW_TONAL_SPREAD_REVIEW", result["quality_flags"])
            self.assertEqual(len(result["sha256"]), 64)

    def test_missing_photo_is_reported_not_invented(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            manifest = root / "manifest.csv"
            gt = root / "ground_truth.csv"
            sources = root / "sources.json"
            save_csv(manifest, MANIFEST_FIELDS, [dict(zip(MANIFEST_FIELDS, (
                "PUBLIC-P001", "P001", "UNKNOWN", "DEV", "PUBLIC_UNKNOWN",
                "datasets/public_samples/images/plain/fake.jpg", "", "NONE", "NO", "synthetic"
            )))])
            save_csv(gt, GROUND_TRUTH_FIELDS, [])
            sources.write_text(json.dumps({"items": [
                {"id": "P001", "path": "plain/fake.jpg",
                 "source_page": "https://example.org", "weave_candidate": "plain"}
            ]}), encoding="utf-8")
            rows, queue, result = analyze(root, manifest, gt, sources)
            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(rows[0]["state"], "MISSING_IMAGE")
            self.assertEqual(queue, [])
            self.assertEqual(result["without_confirmed_gt"], 1)

    def test_annotation_queue_never_becomes_ground_truth(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = root / "datasets/public_samples/images/plain/fake.jpg"
            path.parent.mkdir(parents=True)
            Image.new("RGB", (64, 64), (80, 120, 160)).save(path)
            manifest = root / "manifest.csv"
            gt = root / "ground_truth.csv"
            sources = root / "sources.json"
            save_csv(manifest, MANIFEST_FIELDS, [dict(zip(MANIFEST_FIELDS, (
                "PUBLIC-P001", "P001", "UNKNOWN", "DEV", "PUBLIC_UNKNOWN",
                "datasets/public_samples/images/plain/fake.jpg", "", "NONE", "NO", ""
            )))])
            save_csv(gt, GROUND_TRUTH_FIELDS, [])
            sources.write_text(json.dumps({"items": [
                {"id": "P001", "path": "plain/fake.jpg",
                 "source_page": "https://example.org", "weave_candidate": "plain"}
            ]}), encoding="utf-8")
            rows, queue, result = analyze(root, manifest, gt, sources)
            self.assertEqual(result["status"], "INCOMPLETE_NO_INDEPENDENT_GT")
            self.assertEqual(rows[0]["confirmed_gt"], "NO")
            self.assertEqual(queue[0]["source_id"], "P001")
            self.assertEqual(result["no_v5_result"], 1)


if __name__ == "__main__":
    unittest.main()
