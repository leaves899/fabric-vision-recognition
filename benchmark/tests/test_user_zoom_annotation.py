"""2x crop annotation is in the crop's native pixels, never original pixels."""
import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from benchmark.dataset import MANIFEST_FIELDS
from benchmark.manual_annotation import validate_annotation, samples


SAMPLE = "U20261013_01"
BASE = "datasets/user_contributed/2026-10-13-six-fabric-images"


class ZoomAnnotationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        folder = self.root / BASE
        (folder / "images").mkdir(parents=True)
        (folder / "zoom_unmarked").mkdir()
        original = folder / "images" / (SAMPLE + ".jpg")
        zoom = folder / "zoom_unmarked" / (SAMPLE + "_center_2x.jpg")
        Image.new("RGB", (400, 400), (50, 70, 90)).save(original)
        Image.new("RGB", (200, 200), (55, 75, 95)).save(zoom)
        self.original_hash = hashlib.sha256(original.read_bytes()).hexdigest()
        self.zoom_hash = hashlib.sha256(zoom.read_bytes()).hexdigest()
        manifest_path = self.root / "datasets/manifest.csv"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self.zoom_relative = BASE + "/zoom_unmarked/" + SAMPLE + "_center_2x.jpg"
        with manifest_path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=MANIFEST_FIELDS)
            writer.writeheader()
            writer.writerow({
                "fabric_id": "USER-" + SAMPLE, "position_id": SAMPLE,
                "face": "UNKNOWN", "split": "DEV", "capture_mode": "PHONE_UNKNOWN_LIGHTING",
                "image_path": self.zoom_relative, "result_json_path": "",
                "calibration_type": "NONE", "frame_confirmed": "NO", "notes": "synthetic",
            })
        self.provenance_path = folder / "image_provenance.json"
        self.provenance = {"images": [{
            "sample_id": SAMPLE, "zoom": "zoom_unmarked/" + SAMPLE + "_center_2x.jpg",
            "original": "images/" + SAMPLE + ".jpg",
            "zoom_sha256": self.zoom_hash, "original_sha256": self.original_hash,
            "crop_original_xyxy": [100, 120, 200, 220], "enlargement_scale": 2,
        }]}
        self.provenance_path.write_text(json.dumps(self.provenance), encoding="utf-8")
        self.label = {
            "schema_version": "1.0", "sample_id": SAMPLE,
            "image_path": self.zoom_relative,
            "reference_confirmed": True, "review_state": "OPERATOR_REVIEWED",
            "reference_family": "UNKNOWN", "identity_confirmed": False,
            "eligibility": "DENIM_CANDIDATE",
            "segments": {"reference": [[10, 30], [190, 30]], "check_same": None},
        }

    def test_saved_coordinates_remain_native_to_zoom(self):
        record = validate_annotation(self.root, self.label)
        self.assertEqual(record["image_path"], self.zoom_relative)
        self.assertEqual(record["image_sha256"], self.zoom_hash)
        self.assertEqual((record["image_width"], record["image_height"]), (200, 200))
        self.assertEqual(record["segments"]["reference"], [[10, 30], [190, 30]])
        self.assertEqual(record["annotation_image_kind"], "UNMARKED_2X_CENTER_CROP")
        self.assertEqual(record["coordinate_space"], "ZOOM_2X_NATIVE_PIXELS")
        self.assertEqual(record["original_image_sha256"], self.original_hash)
        self.assertEqual(record["crop_original_xyxy"], [100, 120, 200, 220])
        # Known inverse crop transform, not an independent physical yarn GT:
        self.assertEqual(
            [100 + record["segments"]["reference"][0][0] / 2,
             120 + record["segments"]["reference"][0][1] / 2], [105, 135])

    def test_old_original_coordinates_and_hash_are_rejected(self):
        self.label["image_path"] = BASE + "/images/" + SAMPLE + ".jpg"
        with self.assertRaisesRegex(ValueError, "does not match"):
            validate_annotation(self.root, self.label)
        self.label["image_path"] = self.zoom_relative
        self.label["image_sha256"] = self.original_hash
        with self.assertRaisesRegex(ValueError, "hash changed"):
            validate_annotation(self.root, self.label)

    def test_reject_oversized_coordinates_of_original_photo(self):
        self.label["segments"]["reference"] = [[10, 30], [250, 30]]
        with self.assertRaisesRegex(ValueError, "outside"):
            validate_annotation(self.root, self.label)

    def test_crop_provenance_size_mismatch_rejected(self):
        self.provenance["images"][0]["crop_original_xyxy"] = [100, 120, 210, 220]
        self.provenance_path.write_text(json.dumps(self.provenance), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "zoom dimensions"):
            validate_annotation(self.root, self.label)

    def test_actual_six_registered_as_zoom_without_duplicate_samples(self):
        real_root = Path(__file__).resolve().parents[2]
        registry = samples(real_root)
        base = real_root / BASE
        meta = json.loads((base / "image_provenance.json").read_text(encoding="utf-8"))
        self.assertEqual(len(meta["images"]), 6)
        self.assertEqual(meta["annotation_image_kind"], "UNMARKED_2X_CENTER_CROP")
        for item in meta["images"]:
            sid = item["sample_id"]
            path = BASE + "/" + item["zoom"]
            self.assertEqual(registry[sid]["image_path"], path)
            self.assertTrue((base / item["original"]).is_file())
            with Image.open(real_root / path) as img:
                x0, y0, x1, y1 = item["crop_original_xyxy"]
                self.assertEqual(img.size, ((x1 - x0) * 2, (y1 - y0) * 2))
            verified = validate_annotation(real_root, {
                "schema_version": "1.0", "sample_id": sid, "image_path": path,
                "review_state": "DRAFT", "reference_confirmed": False,
                "segments": {},
            })
            self.assertEqual(verified["coordinate_space"], "ZOOM_2X_NATIVE_PIXELS")


if __name__ == "__main__":
    unittest.main()
