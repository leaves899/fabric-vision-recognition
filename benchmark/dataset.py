"""Step 0 manifest/ground-truth contracts and anti-leakage validation.

No real-world measurements are inferred by this module. All sample rows must
be supplied by an operator; empty CSV templates are intentionally shipped.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

MANIFEST_FIELDS = (
    "fabric_id", "position_id", "face", "split", "capture_mode",
    "image_path", "result_json_path", "calibration_type", "frame_confirmed", "notes",
)
GROUND_TRUTH_FIELDS = (
    "fabric_id", "position_id", "face", "review_status", "gt_source",
    "warp_axis_deg", "weft_axis_deg", "warp_density_per_cm", "weft_density_per_cm",
    "weave_type", "notes",
)
FACES = {"FRONT", "BACK"}
SPLITS = {"DEV", "VALIDATION", "TEST"}
CAPTURE_MODES = {"PHONE_REFLECTION", "PHONE_UNKNOWN_LIGHTING"}
CALIBRATION_TYPES = {"NONE", "FRAME_5CM"}
REVIEW_STATUSES = {"NOT_EVALUATED", "DRAFT", "CONFIRMED"}
KEY = ("fabric_id", "position_id", "face")


def load_csv(path: Path, fields: tuple[str, ...]) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames is None or set(fields) - set(reader.fieldnames):
            missing = sorted(set(fields) - set(reader.fieldnames or []))
            raise ValueError(f"{path}: missing columns: {missing}")
        result = []
        for index, row in enumerate(reader, 2):
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"{path}:{index}: invalid CSV column count")
            result.append({field: row[field].strip() for field in fields})
        return result


def resolve_local(root: Path, relative: str) -> Path:
    """Accept repository-relative paths only; forbid traversal and absolute paths."""
    if not relative:
        raise ValueError("empty path")
    p = Path(relative)
    if p.is_absolute() or "\\" in relative or ":" in relative:
        raise ValueError(f"not a portable relative path: {relative}")
    result = (root.resolve() / p).resolve()
    if not result.is_relative_to(root.resolve()):
        raise ValueError(f"path escapes repository root: {relative}")
    return result


def validate(manifest: list[dict[str, str]], ground_truth: list[dict[str, str]],
             root: Path, check_images: bool = False) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    seen: set[tuple[str, str, str]] = set()
    split_by_fabric: dict[str, str] = {}
    for i, row in enumerate(manifest, 2):
        key = tuple(row[f] for f in KEY)
        if any(not v for v in key): errors.append(f"manifest:{i}: empty identity field")
        if key in seen: errors.append(f"manifest:{i}: duplicate key {key}")
        seen.add(key)
        if row["face"] not in FACES: errors.append(f"manifest:{i}: invalid face")
        if row["split"] not in SPLITS: errors.append(f"manifest:{i}: invalid split")
        if row["capture_mode"] not in CAPTURE_MODES: errors.append(f"manifest:{i}: invalid capture mode")
        if row["calibration_type"] not in CALIBRATION_TYPES: errors.append(f"manifest:{i}: invalid calibration type")
        if row["frame_confirmed"] not in {"YES", "NO"}: errors.append(f"manifest:{i}: frame_confirmed must be YES/NO")
        if row["frame_confirmed"] == "YES" and row["calibration_type"] != "FRAME_5CM":
            errors.append(f"manifest:{i}: confirmed frame requires FRAME_5CM")
        if row["fabric_id"] in split_by_fabric and split_by_fabric[row["fabric_id"]] != row["split"]:
            errors.append(f"manifest:{i}: fabric {row['fabric_id']} leaked across dataset splits")
        split_by_fabric[row["fabric_id"]] = row["split"]
        for col in ("image_path", "result_json_path"):
            if col == "image_path" and not row[col]:
                errors.append(f"manifest:{i}: image_path required")
            elif row[col]:
                try:
                    path = resolve_local(root, row[col])
                    if check_images and col == "image_path" and not path.is_file():
                        errors.append(f"manifest:{i}: missing image {row[col]}")
                    if col == "result_json_path" and not path.is_file():
                        warnings.append(f"manifest:{i}: prediction JSON not found: {row[col]}")
                except ValueError as exc: errors.append(f"manifest:{i}: {exc}")
    gt_seen: set[tuple[str, str, str]] = set()
    for i, row in enumerate(ground_truth, 2):
        key = tuple(row[f] for f in KEY)
        if any(not v for v in key): errors.append(f"ground_truth:{i}: empty identity field")
        if key in gt_seen: errors.append(f"ground_truth:{i}: duplicate key {key}")
        gt_seen.add(key)
        if key not in seen: errors.append(f"ground_truth:{i}: no matching manifest row {key}")
        if row["review_status"] not in REVIEW_STATUSES:
            errors.append(f"ground_truth:{i}: invalid review_status")
        if row["review_status"] == "CONFIRMED" and not row["gt_source"]:
            errors.append(f"ground_truth:{i}: confirmed labels must have gt_source")
        for column in ("warp_axis_deg", "weft_axis_deg", "warp_density_per_cm", "weft_density_per_cm"):
            if not row[column]: continue
            try: number = float(row[column])
            except ValueError:
                errors.append(f"ground_truth:{i}: {column} is not numeric")
                continue
            if not math.isfinite(number): errors.append(f"ground_truth:{i}: {column} must be finite")
            elif column.endswith("axis_deg") and not 0 <= number < 180:
                errors.append(f"ground_truth:{i}: {column} must be in [0, 180)")
            elif column.endswith("density_per_cm") and number <= 0:
                errors.append(f"ground_truth:{i}: {column} must be > 0")
    if not manifest: warnings.append("NO_SAMPLES: manifest has no images; no performance conclusion possible")
    if not ground_truth: warnings.append("NO_GROUND_TRUTH: no independent labeled reference data")
    if not any(row["review_status"] == "CONFIRMED" for row in ground_truth):
        warnings.append("NO_CONFIRMED_GROUND_TRUTH: do not publish accuracy claims")
    return {"status": "FAIL" if errors else ("INCOMPLETE" if warnings else "PASS"),
            "samples": len(manifest), "ground_truth_rows": len(ground_truth),
            "errors": errors, "warnings": warnings}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate textile dataset schema and fabric-level separation")
    parser.add_argument("--manifest", type=Path, default=Path("datasets/manifest.csv"))
    parser.add_argument("--ground-truth", type=Path, default=Path("datasets/ground_truth.csv"))
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--check-images", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = validate(load_csv(args.manifest, MANIFEST_FIELDS),
                          load_csv(args.ground_truth, GROUND_TRUTH_FIELDS),args.root,args.check_images)
    except (ValueError, OSError) as exc:
        print(json.dumps({"status": "FAIL", "errors": [str(exc)]}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 2 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
