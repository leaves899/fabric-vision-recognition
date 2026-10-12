from __future__ import annotations

import copy
import csv
import json
import tempfile
import unittest
from pathlib import Path

from benchmark.adapters.v5 import FROZEN_V4_SHA, parse_v5
from benchmark.dataset import GROUND_TRUTH_FIELDS, MANIFEST_FIELDS, load_csv, validate
from benchmark.metrics import axis_error_deg, density_error_pct, summarize
from benchmark.runner import benchmark, main


# All observations below are SYNTHETIC fixtures; NOT textile measurements.
def manifest(face="FRONT", split="DEV", calibrated="YES"):
    return dict(zip(MANIFEST_FIELDS, ["SYNTH-001", "P1", face, split,
        "PHONE_REFLECTION", "images/synth.png", "results/synth.json", "FRAME_5CM" if calibrated == "YES" else "NONE", calibrated, "synthetic only"]))


def truth(status="CONFIRMED"):
    return dict(zip(GROUND_TRUTH_FIELDS, ["SYNTH-001", "P1", "FRONT", status,
        "SYNTHETIC_TEST_ONLY", "179", "89", "40", "25", "3/1右斜纹", "synthetic only"]))


def synthetic_result():
    return {"result": {
        "demo_version": "0.3.0-v5", "image_sha256": "synthetic",
        "v4": {"frozen_sha256": FROZEN_V4_SHA},
        "manual_yarn_reference": {"source": "USER_TWO_POINT_SAME_REAL_YARN", "confirmed_by_operator": True},
        "family_assignment": {"warp_family": "A", "confirmed_by_human": True},
        "calibration": {"confirmed": True, "cm_per_px": 0.00555},
        "parameters": [
            {"id": 1, "status": "NEEDS_CONFIRMATION", "value": 1},
            {"id": 2, "status": "NEEDS_CONFIRMATION", "value": 91},
            {"id": 8, "status": "NEEDS_CONFIRMATION", "value": {"candidate_per_cm": 42}},
            {"id": 9, "status": "NEEDS_CONFIRMATION", "value": {"candidate_per_cm": 26}},
        ],
    }}


class DatasetTests(unittest.TestCase):
    def test_empty_skeleton_warns(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = validate([], [], Path(tmp))
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertIn("NO_SAMPLES", " ".join(result["warnings"]))

    def test_leakage_same_fabric_other_face(self):
        front = manifest()
        back = manifest(face="BACK", split="VALIDATION")
        with tempfile.TemporaryDirectory() as tmp:
            result = validate([front, back], [truth()], Path(tmp))
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any("leaked" in e for e in result["errors"]))

    def test_identity_and_calibration_constraints(self):
        m = manifest(calibrated="NO")
        m["frame_confirmed"] = "YES"
        with tempfile.TemporaryDirectory() as tmp:
            result = validate([m], [truth()], Path(tmp))
        self.assertEqual(result["status"], "FAIL")

    def test_missing_label_source_and_invalid_density(self):
        t = truth()
        t["gt_source"] = ""
        t["warp_density_per_cm"] = "0"
        with tempfile.TemporaryDirectory() as tmp:
            result = validate([manifest()], [t], Path(tmp))
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any("confirmed labels" in e for e in result["errors"]))

    def test_reject_absolute_or_traversing_paths(self):
        m = manifest()
        m["image_path"] = "../../private.png"
        with tempfile.TemporaryDirectory() as tmp:
            result = validate([m], [truth()], Path(tmp))
        self.assertTrue(any("escapes" in e for e in result["errors"]))

    def test_schema_header_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "manifest.csv"
            file.write_text("fabric_id,face\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "missing columns"):
                load_csv(file, MANIFEST_FIELDS)


class MetricTests(unittest.TestCase):
    def test_undirected_angles(self):
        self.assertAlmostEqual(axis_error_deg(179, 1), 2)
        self.assertAlmostEqual(axis_error_deg(0, 180), 0)
        self.assertAlmostEqual(axis_error_deg(90, 270), 0)

    def test_density_percentage_units(self):
        self.assertAlmostEqual(density_error_pct(42, 40), 5)
        with self.assertRaises(ValueError): density_error_pct(0, 0)

    def test_empty_summary_does_not_claim_zero_error(self):
        self.assertEqual(summarize([])["mean"], None)


class AdapterAndRunnerTests(unittest.TestCase):
    def test_saved_v5_candidates_are_not_certified(self):
        prediction = parse_v5(synthetic_result())
        self.assertEqual(prediction["review_status"], "CANDIDATE")
        self.assertEqual(prediction["warp_density_per_cm"], 42)

    def test_missing_confirmation_abstains(self):
        payload = synthetic_result()
        payload["result"]["family_assignment"]["confirmed_by_human"] = False
        output = parse_v5(payload)
        self.assertIsNone(output["warp_density_per_cm"])
        self.assertIsNone(output["warp_axis_deg"])
        self.assertIn("WARP_WEFT_NOT_CONFIRMED", output["reasons"])

    def test_missing_frame_abstains_density_but_not_direction(self):
        payload = synthetic_result()
        payload["result"]["calibration"]["confirmed"] = False
        output = parse_v5(payload)
        self.assertIsNone(output["warp_density_per_cm"])
        self.assertEqual(output["warp_axis_deg"], 1)

    def test_modified_frozen_hash_rejected(self):
        payload = synthetic_result()
        payload["result"]["v4"]["frozen_sha256"] = "bad"
        with self.assertRaisesRegex(ValueError, "hash"):
            parse_v5(payload)

    def test_ground_truth_never_inferred_from_unconfirmed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "results").mkdir()
            (root / "results/synth.json").write_text(json.dumps(synthetic_result()), encoding="utf-8")
            rows, summary = benchmark([manifest()], [truth("DRAFT")], root)
        self.assertEqual(rows[0]["status"], "NOT_EVALUATED")
        self.assertIsNone(summary["metrics"]["warp_density_error_pct"]["mean"])

    def test_synthetic_full_candidate_benchmark(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "results").mkdir()
            (root / "results/synth.json").write_text(json.dumps(synthetic_result()), encoding="utf-8")
            rows, summary = benchmark([manifest()], [truth()], root)
        self.assertEqual(rows[0]["status"], "EVALUATED_CANDIDATE")
        self.assertAlmostEqual(rows[0]["warp_axis_error_deg"], 2)
        self.assertAlmostEqual(rows[0]["warp_density_error_pct"], 5)
        self.assertEqual(summary["metrics"]["warp_density_error_pct"]["candidate_evaluated"], 1)
        self.assertEqual(summary["metrics"]["weft_density_error_pct"]["abstained"], 0)

    def test_missing_predictions_count_as_abstention(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows, summary = benchmark([manifest()], [truth()], root)
        self.assertEqual(rows[0]["status"], "ABSTAINED")
        self.assertEqual(summary["metrics"]["warp_density_error_pct"]["abstained"], 1)

    def test_empty_csv_cli_does_not_return_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            root.joinpath("manifest.csv").write_text(",".join(MANIFEST_FIELDS) + "\n", encoding="utf-8")
            root.joinpath("ground_truth.csv").write_text(",".join(GROUND_TRUTH_FIELDS) + "\n", encoding="utf-8")
            code = main(["--manifest", str(root / "manifest.csv"), "--ground-truth", str(root / "ground_truth.csv"),
                         "--root", str(root), "--out", str(root / "out")])
            summary = json.loads((root / "out/benchmark_summary.json").read_text(encoding="utf-8"))
        self.assertEqual(code, 3)
        self.assertEqual(summary["status"], "NOT_EVALUATED")


if __name__ == "__main__":
    unittest.main()
