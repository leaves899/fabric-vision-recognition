#!/usr/bin/env python3
"""Blind 0/90/180/270 exact quarter-turn FabricNET benchmark.

Runs frozen Shibie V0.6.3 source and compares *physical* warp/weft after
inverting image rotations. Single FabricNET image is duplicated only to satisfy
legacy two-input API; NEVER report genuine R/T performance.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import sys
import time
import traceback
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from validate_fabricnet_latest_20261021 import fetch_dataset, parse_ground_truth
from engine import pipeline
from engine.width import map_centerlines_to_reflection

DEGREES = (0, 90, 180, 270)
FIELDS = (
    "image", "source_sha256", "angle", "input_mode", "status", "failure_reasons",
    "warp_axis_hint", "mm_per_px_x", "mm_per_px_y", "warp_direction_rotated",
    "weft_direction_rotated", "warp_direction_original", "weft_direction_original",
    "warp_density_per_cm", "weft_density_per_cm", "truth_warp", "truth_weft",
    "warp_signed_error", "weft_signed_error", "warp_abs_error", "weft_abs_error",
    "warp_rel_error_pct", "weft_rel_error_pct", "both_within_10pct",
    "warp_lines", "weft_lines", "gate3", "width_status", "truth_texture",
    "elapsed_seconds"
)

def rotate_90(image, angle):
    if angle == 0:
        return image
    flags = {90: cv2.ROTATE_90_CLOCKWISE,
             180: cv2.ROTATE_180,
             270: cv2.ROTATE_90_COUNTERCLOCKWISE}
    return cv2.rotate(image, flags[angle])

def original_coordinates(image, angle):
    return rotate_90(image, (360 - angle) % 360)

def _candidate_lines(result, selected_runs):
    out = {"warp": [], "weft": []}
    orient = result.get("orientation") or {}
    norm = result.get("normalization") or {}
    public = result.get("centerline_evidence") or {}
    for family in out:
        lines = public.get(family) or []
        if not lines and norm:
            angle = orient.get(family + "_direction_deg")
            seed = selected_runs.get(round(float(angle) % 180, 4)) if angle is not None else None
            if seed and "_width_seed" in seed:
                try:
                    lines = map_centerlines_to_reflection(
                        seed["_width_seed"], norm, np.eye(2, 3, dtype=np.float32))
                except Exception:
                    lines = []
        out[family] = lines
    return out

def draw_original_overlay(original, rotated_frame, result, selected_runs, angle, filename):
    picture = rotated_frame.copy()
    lengths = {}
    detected_lines = _candidate_lines(result, selected_runs)
    for family, color in (("warp", (0, 15, 255)), ("weft", (255, 255, 0))):
        count = 0
        for poly in detected_lines[family]:
            vertices = np.asarray(poly, dtype=np.float32)
            if vertices.ndim == 2 and vertices.shape[1] == 2 and len(vertices) >= 2:
                cv2.polylines(picture, [np.rint(vertices).astype(np.int32)], False,
                              color, 1, cv2.LINE_AA)
                count += 1
        lengths[family] = count
    restored = original_coordinates(picture, angle)
    if restored.shape != original.shape:
        raise AssertionError("ORIGINAL_COORDINATE_INVERSE_FAILED")
    cv2.rectangle(restored, (0, 0), (restored.shape[1]-1, 24), (24, 24, 24), -1)
    cv2.putText(restored, f"{filename} {angle}deg RED=WARP CYAN=WEFT",
                (3, 17), cv2.FONT_HERSHEY_SIMPLEX, .42,
                (255, 255, 255), 1, cv2.LINE_AA)
    return restored, lengths

def numeric(value):
    try:
        x = float(value)
        return x if np.isfinite(x) else None
    except (ValueError, TypeError):
        return None

def infer(image_path, angle, output):
    started = time.monotonic()
    original_bytes = image_path.read_bytes()
    original = cv2.imdecode(np.frombuffer(original_bytes, np.uint8), cv2.IMREAD_COLOR)
    if original is None:
        raise RuntimeError("BAD_ORIGINAL_IMAGE")
    if original.shape[:2] != (480, 640):
        raise RuntimeError("UNEXPECTED_FABRICNET_GEOMETRY_" + str(original.shape))
    rotated = rotate_90(original, angle)
    # For 0 use original compressed bytes for bit-identical baseline to
    # 2026-10-21 V0.6.3 replay; for rotations use lossless PNG.
    if angle == 0:
        input_bytes = original_bytes
    else:
        success, encoded = cv2.imencode(".png", rotated)
        if not success:
            raise RuntimeError("ROTATED_PNG_ENCODING_FAILED")
        input_bytes = encoded.tobytes()
    x_mm = 5.0 / 640.0
    y_mm = 4.0 / 480.0
    if angle in (90, 270):
        x_mm, y_mm = y_mm, x_mm
    warp_hint = "horizontal" if angle in (90, 270) else "vertical"

    selected_runs = {}
    actual = pipeline._run_direction
    def record(normalized, direction_deg, mmx, mmy):
        candidate = actual(normalized, direction_deg, mmx, mmy)
        selected_runs[round(float(direction_deg) % 180.0, 4)] = candidate
        return candidate
    pipeline._run_direction = record
    try:
        result = pipeline.run_measurement(
            input_bytes, input_bytes,
            mm_per_px_x=x_mm, mm_per_px_y=y_mm,
            warp_axis_hint=warp_hint)
    finally:
        pipeline._run_direction = actual

    overlay, counts = draw_original_overlay(original, rotated, result, selected_runs,
                                            angle, image_path.stem)
    (output / "overlays_original_coords").mkdir(parents=True, exist_ok=True)
    ok = cv2.imwrite(str(output / "overlays_original_coords" / image_path.name),
                     overlay, [cv2.IMWRITE_JPEG_QUALITY, 95])
    if not ok:
        raise RuntimeError("OVERLAY_WRITE_FAILED")
    orientation = result.get("orientation") or {}
    record_data = {
        "image": image_path.name,
        "source_sha256": hashlib.sha256(original_bytes).hexdigest(),
        "angle": angle,
        "input_mode": "DUPLICATED_SINGLE_MICROSCOPE_IMAGE_NOT_TRUE_RT",
        "status": result.get("status"),
        "failure_reasons": "|".join(result.get("failure_reasons") or []),
        "warp_axis_hint": warp_hint,
        "mm_per_px_x": x_mm,
        "mm_per_px_y": y_mm,
        "warp_density_per_cm": numeric(result.get("warp_density_per_cm")),
        "weft_density_per_cm": numeric(result.get("weft_density_per_cm")),
        "warp_lines": counts["warp"],
        "weft_lines": counts["weft"],
        "gate3": (result.get("gate3") or {}).get("status"),
        "width_status": (result.get("apparent_width") or {}).get("status"),
        "elapsed_seconds": round(time.monotonic()-started, 3),
    }
    for fam in ("warp", "weft"):
        rot = numeric(orientation.get(fam + "_direction_deg"))
        record_data[fam + "_direction_rotated"] = rot
        record_data[fam + "_direction_original"] = (
            round((rot - angle) % 180.0, 4) if rot is not None else None)
    return record_data

def attach_truth(record, truth):
    reference = truth.get(record["image"]) or {}
    record["truth_texture"] = reference.get("texture")
    for fam in ("warp", "weft"):
        target = numeric(reference.get(fam))
        prediction = numeric(record.get(fam + "_density_per_cm"))
        record["truth_"+fam] = target
        error = prediction - target if prediction is not None and target is not None else None
        record[fam + "_signed_error"] = round(error, 4) if error is not None else None
        record[fam + "_abs_error"] = round(abs(error), 4) if error is not None else None
        record[fam + "_rel_error_pct"] = (
            round(100.0*abs(error)/target, 4) if error is not None and target and target>0 else None)
    a,b = record["warp_rel_error_pct"],record["weft_rel_error_pct"]
    record["both_within_10pct"] = int(a<=10 and b<=10) if a is not None and b is not None else None
    return record

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--angle", required=True, choices=DEGREES, type=int)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--dataset", type=Path, default=Path("/tmp/fabricnet_public_rotation_dataset"))
    ap.add_argument("--engine-revision", default="UNVERIFIED")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    images = fetch_dataset(args.dataset)
    # Extract workbook schema now but *never* give any truth value to inference.
    truth, schema = parse_ground_truth(args.dataset / "FabricNet_parameters.xlsx")
    if len(truth) != 130:
        raise RuntimeError("GROUND_TRUTH_SCHEMA_PARSE_INCOMPLETE: " + json.dumps(schema))
    records = []
    for index, path in enumerate(images, 1):
        try:
            row = infer(path, args.angle, args.out)
        except Exception as exc:
            traceback.print_exc()
            print(f"ERROR [{index}/130] {path.name}: {exc}", flush=True)
            row = {k: None for k in FIELDS}
            row.update(image=path.name, source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                       angle=args.angle, status="EXCEPTION", failure_reasons=str(exc),
                       input_mode="DUPLICATED_SINGLE_MICROSCOPE_IMAGE_NOT_TRUE_RT")
        records.append(attach_truth(row, truth))
        print(f"[{index}/130] {path.name} angle={args.angle} "
              f"status={row['status']} warp={row.get('warp_density_per_cm')} "
              f"weft={row.get('weft_density_per_cm')}", flush=True)

    with (args.out / "metrics.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(FIELDS), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
    if len(records) != 130:
        raise RuntimeError("INCOMPLETE_130_IMAGE_RESULT")
    published = [r for r in records if r["warp_rel_error_pct"] is not None and r["weft_rel_error_pct"] is not None]
    mean = lambda arr: float(np.mean(arr)) if arr else None
    summary = {
        "angle": args.angle,
        "engine_revision": args.engine_revision,
        "n_total": len(records),
        "n_numeric": len(published),
        "n_pass": sum(r["status"] == "PASS" for r in records),
        "n_low_confidence": sum(r["status"] == "LOW_CONFIDENCE" for r in records),
        "n_fail_or_exception": sum(r["status"] not in ("PASS","LOW_CONFIDENCE") for r in records),
        "warp_mae": mean([r["warp_abs_error"] for r in published]),
        "weft_mae": mean([r["weft_abs_error"] for r in published]),
        "warp_mape": mean([r["warp_rel_error_pct"] for r in published]),
        "weft_mape": mean([r["weft_rel_error_pct"] for r in published]),
        "both_10": sum(r["both_within_10pct"] == 1 for r in records),
        "pass_both_10": sum(r["both_within_10pct"] == 1 and r["status"] == "PASS" for r in records),
        "input_and_calibration": {
            "input_mode": "ONE_MICROSCOPE_PHOTO_DUPLICATED_NOT_GENUINE_RT",
            "rotation": "PIXEL_EXACT_90_DEGREE_ROTATE_NO_RESIZE",
            "90_270_axes_and_mm_per_px_swapped": True,
            "warp_weft_names_follow_PHYSICAL_yarn_identity": True,
            "no_ground_truth_entered_in_detector": True,
            "no_physical_centerline_gt": True,
            "overlays_inverse_rotated_to_original_photo": True,
        }
    }
    (args.out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                           encoding="utf-8")
    print("ROTATION_SUMMARY " + json.dumps(summary, ensure_ascii=False), flush=True)

if __name__ == "__main__":
    main()
