"""Tests for the strict ZIP batch preflight and no-ground-truth-leak scoring."""
import csv
import io
import json
import sys
import tempfile
import unittest
import zipfile
from argparse import Namespace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_dataset as sut


class BatchAuditTests(unittest.TestCase):
    def test_safe_zip_enumeration_never_extracts_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "inputs.zip"
            with zipfile.ZipFile(path, "w") as z:
                z.writestr("../traversal.jpg", b"badjpeg")
                z.writestr("nested/a.PNG", b"png")
                z.writestr("nested/readme.txt", "ignore")
                z.writestr("nested/config.yaml", "ignore")
            with zipfile.ZipFile(path) as z:
                entries = sut._image_entries(z)
            self.assertEqual(len(entries), 2)
            self.assertEqual({x.filename for x in entries},
                             {"../traversal.jpg", "nested/a.PNG"})
            self.assertFalse((Path(temp).parent / "traversal.jpg").exists())

    def test_labels_only_score_after_predictions(self):
        pred = {"image": "img.jpg", "warp_density_per_cm": 40.0,
                "weft_density_per_cm": 30.0,
                "weave_candidate": "3/1"}
        gt = {"img.jpg": {"warp_density_per_cm": "44",
                          "weft_density_per_cm": "30", "weave": "3/1"}}
        sut._annotate_truth(pred, gt)
        self.assertEqual(pred["both_density_within_10pct"], 1)
        self.assertAlmostEqual(pred["warp_rel_error_pct"], 9.09091)
        self.assertEqual(pred["weave_exact_match"], 1)
        pred2 = {"image": "no label", "warp_density_per_cm": 99}
        sut._annotate_truth(pred2, gt)
        self.assertNotIn("both_density_within_10pct", pred2)

    def test_unresolved_does_not_become_correct(self):
        pred = {"image": "x.jpg", "warp_density_per_cm": None,
                "weft_density_per_cm": None, "weave_candidate": None}
        sut._annotate_truth(pred, {"x.jpg": {
            "warp_density_per_cm": "30", "weft_density_per_cm": "40",
            "weave": "plain_1_1"
        }})
        self.assertIsNone(pred.get("both_density_within_10pct"))
        self.assertIsNone(pred.get("weave_exact_match"))

    def test_bad_and_good_images_are_both_reported(self):
        import cv2
        import numpy as np
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)
            archive = p / "input.zip"
            img = np.full((90, 120, 3), 160, dtype=np.uint8)
            encoded = cv2.imencode(".png", img)[1].tobytes()
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("good/sample.png", encoded)
                z.writestr("bad/corrupt.jpg", b"not an image")
                z.writestr("not_image/data.txt", "data")
            args = Namespace(archive=archive, out=p / "output",
                             truth_csv=None, pairs_csv=None,
                             mm_x=None, mm_y=None,
                             assume_axes_aligned=False,
                             inventory_only=True, rois=1)
            result = sut.run(args)
            self.assertEqual(result["samples"], 2)
            with (p / "output" / "all_images.csv").open(
                encoding="utf-8-sig", newline=""
            ) as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(len(rows), 2)
            good = next(r for r in rows if r["image"] == "good/sample.png")
            self.assertEqual(good["width_px"], "120")
            self.assertEqual(good["height_px"], "90")
            self.assertEqual(good["density_status"],
                             "NOT_RUN_MISSING_PHYSICAL_CALIBRATION")
            corrupt = next(r for r in rows if r["image"] == "bad/corrupt.jpg")
            self.assertEqual(corrupt["density_status"], "ERROR")
            self.assertIn("IMAGE_DECODE_FAILED", corrupt["density_error"])
            self.assertEqual(result["scored_density_n"], 0)
            self.assertEqual(result["scored_weave_n"], 0)

    def test_calibration_is_required_for_pixel_density(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)
            zfile = p / "one.zip"
            with zipfile.ZipFile(zfile, "w") as z:
                z.writestr("img.png", b"corrupt")
            args = Namespace(archive=zfile, out=p / "out",
                             truth_csv=None, pairs_csv=None,
                             mm_x=0.01, mm_y=None,
                             assume_axes_aligned=True,
                             inventory_only=True, rois=1)
            with self.assertRaisesRegex(ValueError, "BOTH_MM"):
                sut.run(args)

    def test_explicit_pairing_rejects_missing_image(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)
            pairs_csv = p / "pairs.csv"
            pairs_csv.write_text(
                "sample_id,reflection,transmission\n"
                "a,front.jpg,missing.jpg\n", encoding="utf-8"
            )
            pair_rows = sut._load_pairs(pairs_csv)
            with zipfile.ZipFile(p / "photos.zip", "w") as z:
                z.writestr("front.jpg", b"fake")
            with zipfile.ZipFile(p / "photos.zip") as z:
                entries = sut._image_entries(z)
            with self.assertRaisesRegex(ValueError, "PAIR_IMAGE_NOT_FOUND"):
                sut._jobs(entries, pair_rows)


if __name__ == "__main__":
    unittest.main()
