#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Blind, reproducible ZIP-to-image audit and candidate inference.

This is an experiment harness, not a claim that every physical yarn or
crossing is recognized. Labels are read ONLY after both inference stages.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
import time
import zipfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
FIELDS = [
    "image", "source_sha256", "transmission_source_sha256", "width_px", "height_px", "input_mode",
    "density_status", "density_error", "warp_density_per_cm",
    "weft_density_per_cm", "warp_observed_trace_count",
    "weft_observed_trace_count", "warp_pitch_px", "weft_pitch_px",
    "warp_count_spacing_disagreement_pct",
    "weft_count_spacing_disagreement_pct", "weave_status",
    "weave_candidate", "weave_physical_0_1_verified", "weave_error",
    "truth_warp_density_per_cm", "truth_weft_density_per_cm",
    "truth_weave", "warp_rel_error_pct", "weft_rel_error_pct",
    "both_density_within_10pct", "weave_exact_match", "elapsed_s",
]


def _image_entries(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    # Do not extract arbitrary archive paths. Read each image in memory
    # and assign a controlled local output name.
    images = sorted(
        (info for info in archive.infolist()
         if not info.is_dir() and Path(info.filename).suffix.lower() in IMAGE_EXTS),
        key=lambda info: info.filename.casefold(),
    )
    names = [info.filename for info in images]
    if len(names) != len(set(names)):
        raise ValueError("DUPLICATE_ARCHIVE_IMAGE_PATH")
    return images


def _safe_id(index: int, path: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_-]+", "_", Path(path).stem).strip("_")
    return f"{index:05d}_{name[:45] or 'image'}"


def _load_truth(path: Path | None) -> dict[str, dict]:
    if path is None:
        return {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise ValueError("EMPTY_TRUTH_CSV")
    if "image" not in rows[0]:
        raise ValueError("TRUTH_CSV_MUST_HAVE_IMAGE_COLUMN")
    truth = {}
    for row in rows:
        key = (row.get("image") or "").replace("\\", "/")
        if key in truth:
            raise ValueError(f"DUPLICATE_TRUTH_IMAGE:{key}")
        truth[key] = row
    return truth


def _to_float(value):
    if value is None or str(value).strip() == "":
        return None
    return float(value)


def _annotate_truth(row: dict, truth: dict[str, dict]):
    # A label is NEVER passed into the inference functions.
    gt = truth.get(row["image"])
    if gt is None:
        return
    for fam in ("warp", "weft"):
        ref = _to_float(gt.get(f"{fam}_density_per_cm"))
        pred = row.get(f"{fam}_density_per_cm")
        row[f"truth_{fam}_density_per_cm"] = ref
        row[f"{fam}_rel_error_pct"] = (
            round(100 * abs(float(pred) - ref) / ref, 5)
            if pred is not None and ref is not None and ref > 0 else None
        )
    a, b = row.get("warp_rel_error_pct"), row.get("weft_rel_error_pct")
    if a is not None and b is not None:
        row["both_density_within_10pct"] = int(a <= 10 and b <= 10)
    truth_weave = (gt.get("weave") or "").strip()
    row["truth_weave"] = truth_weave or None
    if truth_weave and row.get("weave_candidate"):
        row["weave_exact_match"] = int(
            str(row["weave_candidate"]).strip().casefold() == truth_weave.casefold()
        )


def _cv2():
    import cv2
    import numpy as np
    return cv2, np


def _decode(raw: bytes):
    cv2, np = _cv2()
    frame = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError("IMAGE_DECODE_FAILED")
    return frame


def _write_image(path: Path, image, encode_params=None):
    # cv2.imwrite sometimes fails with Chinese Windows output paths.
    cv2, _ = _cv2()
    path.parent.mkdir(parents=True, exist_ok=True)
    success, encoded = cv2.imencode(path.suffix, image, encode_params or [])
    if not success:
        raise OSError(f"IMAGE_ENCODING_FAILED:{path.name}")
    path.write_bytes(encoded.tobytes())


def _paint(frame, warp_paths, weft_paths, label):
    cv2, np = _cv2()
    overlay = frame.copy()
    counts = {}
    for fam, paths, color in (
        ("warp", warp_paths, (0, 0, 255)),
        ("weft", weft_paths, (255, 240, 0)),
    ):
        valid = 0
        for line in paths:
            pts = np.asarray(line, dtype=np.float32)
            if pts.ndim != 2 or pts.shape[1] != 2 or len(pts) < 2:
                continue
            cv2.polylines(overlay, [np.rint(pts).astype(np.int32)],
                          False, color, 1, cv2.LINE_AA)
            valid += 1
        counts[fam] = valid
    cv2.rectangle(overlay, (0, 0), (overlay.shape[1] - 1, 27),
                  (25, 25, 25), -1)
    cv2.putText(overlay, label[:110], (6, 18),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1,
                cv2.LINE_AA)
    return overlay, counts


def _single_photo_density(frame, mm_x, mm_y, out: Path, sample_id: str):
    """Historical horizontal-twice baseline. Applicable to aligned images only."""
    cv2, np = _cv2()
    shibie_dir = str(ROOT / "shibie")
    if shibie_dir not in sys.path:
        sys.path.insert(0, shibie_dir)
    from engine import pipeline
    from engine.config import DEFAULT_CONFIG
    from engine.normalization import normalize_transmission
    from engine.width import map_centerlines_to_reflection

    result = {}
    for fam, photo, px_mm_x, px_mm_y in (
        ("weft", frame, mm_x, mm_y),
        ("warp", cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE), mm_y, mm_x),
    ):
        normalized, meta = normalize_transmission(photo, DEFAULT_CONFIG)
        scale = float(meta["resize_scale"])
        run = pipeline._run_direction(
            normalized, 0.0, px_mm_x / scale, px_mm_y / scale
        )
        paths = map_centerlines_to_reflection(
            run["_width_seed"], meta, np.eye(2, 3, dtype=np.float32)
        )
        if fam == "warp":
            h = frame.shape[0]
            paths = [np.column_stack((np.asarray(p)[:, 1],
                                      h - 1 - np.asarray(p)[:, 0]))
                     for p in paths]
        result[fam] = {"run": run, "paths": paths}
    statuses = [result[x]["run"]["confidence"]["status"] for x in ("warp", "weft")]
    state = "FAIL" if "FAIL" in statuses else (
        "PASS" if statuses == ["PASS", "PASS"] else "LOW_CONFIDENCE"
    )
    overlay, counts = _paint(
        frame, result["warp"]["paths"], result["weft"]["paths"],
        f"{sample_id} red=warp cyan=weft {state}"
    )
    out.mkdir(parents=True, exist_ok=True)
    _write_image(out / f"{sample_id}.jpg", overlay,
                 [cv2.IMWRITE_JPEG_QUALITY, 92])
    row = {"density_status": state}
    for fam in ("warp", "weft"):
        run = result[fam]["run"]
        row[f"{fam}_density_per_cm"] = round(
            float(run["density"]["density_per_cm"]), 5
        )
        row[f"{fam}_observed_trace_count"] = counts[fam]
        row[f"{fam}_pitch_px"] = round(
            float(run["centerline"]["median_center_spacing_px"]), 5
        )
        row[f"{fam}_count_spacing_disagreement_pct"] = round(
            float(run["density"]["path_diff_pct"]), 5
        )
    return row


def _paired_photo_density(front, back, mm_x, mm_y, out: Path, sample_id: str):
    """Real paired R/T input: preserves Shibie engine's calibration and gates."""
    shibie_dir = str(ROOT / "shibie")
    if shibie_dir not in sys.path:
        sys.path.insert(0, shibie_dir)
    from engine.pipeline import run_measurement
    cv2, np = _cv2()
    result = run_measurement(
        cv2.imencode(".png", front)[1].tobytes(),
        cv2.imencode(".png", back)[1].tobytes(),
        mm_per_px_x=mm_x, mm_per_px_y=mm_y,
        evidence_output_dir=str(out / sample_id),
        sample_id=sample_id,
    )
    row = {"density_status": result.get("status", "FAIL")}
    if row["density_status"] == "FAIL":
        row["density_error"] = "|".join(result.get("failure_reasons", []))
        return row
    for fam in ("warp", "weft"):
        row[f"{fam}_density_per_cm"] = result.get(f"{fam}_density_per_cm")
        detail = (result.get("density_debug") or {}).get(fam) or {}
        row[f"{fam}_observed_trace_count"] = (
            (detail.get("centerline") or {}).get("valid_centerline_count")
        )
        row[f"{fam}_pitch_px"] = (
            (detail.get("centerline") or {}).get("median_center_spacing_px")
        )
        row[f"{fam}_count_spacing_disagreement_pct"] = (
            (detail.get("density") or {}).get("path_diff_pct")
        )
    evidence = result.get("centerline_evidence") or {}
    canvas, _ = _paint(
        front, evidence.get("warp") or [], evidence.get("weft") or [],
        f"{sample_id} paired RT red=warp cyan=weft"
    )
    (out / "overlays").mkdir(exist_ok=True, parents=True)
    _write_image(out / "overlays" / f"{sample_id}.jpg", canvas)
    return row


def _weave_candidate(frame, out: Path, sample_id: str, rois: int):
    if min(frame.shape[:2]) < 640:
        return {"weave_status": "UNRESOLVED_IMAGE_TOO_SMALL"}
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from modules.image_recognition.weave_v5 import run
    cv2, _ = _cv2()
    path = out / "inputs" / f"{sample_id}.png"
    path.parent.mkdir(exist_ok=True, parents=True)
    _write_image(path, frame)
    report = run(path, out / "weave" / sample_id, rois=rois)
    summary = report["summary"]
    return {
        "weave_status": summary.get("status", "unresolved"),
        "weave_candidate": summary.get("organization_candidate"),
        "weave_physical_0_1_verified": bool(
            summary.get("physical_0_1_verified", False)
        ),
    }


def _load_pairs(path: Path | None):
    if path is None:
        return None
    with path.open(encoding="utf-8-sig", newline="") as f:
        pairs = list(csv.DictReader(f))
    required = {"sample_id", "reflection", "transmission"}
    if not pairs or not required.issubset(pairs[0]):
        raise ValueError("PAIRS_CSV_REQUIRES_sample_id_reflection_transmission")
    return pairs


def _jobs(entries, pairs):
    if pairs is None:
        return [{"sample_id": _safe_id(i, item.filename),
                 "reflection": item.filename, "transmission": None}
                for i, item in enumerate(entries, 1)]
    files = {x.filename for x in entries}
    seen = set()
    used = set()
    jobs = []
    for pair in pairs:
        a, b, sid = pair["reflection"], pair["transmission"], pair["sample_id"]
        if not sid or sid in seen:
            raise ValueError(f"EMPTY_OR_DUPLICATE_PAIR_ID:{sid}")
        if a not in files or b not in files:
            raise ValueError(f"PAIR_IMAGE_NOT_FOUND:{sid}")
        if a == b or a in used or b in used:
            raise ValueError(f"DUPLICATE_OR_SELF_PAIR_IMAGE:{sid}")
        seen.add(sid)
        used.update((a, b))
        jobs.append(pair)
    # Never silently drop an image that is absent from the pairing manifest.
    for image_name in sorted(files - used):
        jobs.append({"sample_id": _safe_id(len(jobs) + 1, image_name),
                     "reflection": image_name, "transmission": None,
                     "unpaired": True})
    return jobs


def run(args):
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    truth = _load_truth(args.truth_csv)
    pairs = _load_pairs(args.pairs_csv)
    if (args.mm_x is None) != (args.mm_y is None):
        raise ValueError("CALIBRATION_REQUIRES_BOTH_MM_PER_PIXEL_AXES")
    if args.mm_x is not None and min(args.mm_x, args.mm_y) <= 0:
        raise ValueError("CALIBRATION_MUST_BE_POSITIVE")
    if pairs is None and args.mm_x is not None and not args.assume_axes_aligned:
        raise ValueError("SINGLE_PHOTO_MODE_REQUIRES_EXPLICIT_ALIGNED_AXES")
    rows = []
    with zipfile.ZipFile(args.archive) as archive:
        entries = _image_entries(archive)
        if not entries:
            raise ValueError("NO_IMAGES_IN_ARCHIVE")
        jobs = _jobs(entries, pairs)
        for index, job in enumerate(jobs, 1):
            start = time.monotonic()
            image_name = job["reflection"]
            row = {k: None for k in FIELDS}
            row.update(
                image=image_name,
                input_mode="DECLARED_PAIRED_RT" if job.get("transmission") else
                           ("UNPAIRED_IMAGE" if job.get("unpaired")
                            else "SINGLE_PHOTO_NOT_REAL_RT"),
                density_status=("NOT_RUN_UNPAIRED" if job.get("unpaired")
                                else "NOT_RUN_MISSING_PHYSICAL_CALIBRATION"),
                weave_status="NOT_RUN",
            )
            try:
                with archive.open(image_name) as f:
                    raw = f.read()
                row["source_sha256"] = hashlib.sha256(raw).hexdigest()
                frame = _decode(raw)
                row["width_px"], row["height_px"] = frame.shape[1], frame.shape[0]
                sid = _safe_id(index, job.get("sample_id") or image_name)
                if args.mm_x is not None and not args.inventory_only and not job.get("unpaired"):
                    if job.get("transmission"):
                        with archive.open(job["transmission"]) as f:
                            other_raw = f.read()
                        row["transmission_source_sha256"] = hashlib.sha256(
                            other_raw
                        ).hexdigest()
                        other = _decode(other_raw)
                        row.update(_paired_photo_density(
                            frame, other, args.mm_x, args.mm_y,
                            out / "density", sid
                        ))
                    else:
                        row.update(_single_photo_density(
                            frame, args.mm_x, args.mm_y,
                            out / "density" / "overlays", sid
                        ))
                if not args.inventory_only:
                    try:
                        row.update(_weave_candidate(
                            frame, out, sid, args.rois
                        ))
                    except Exception as exc:
                        row.update(weave_status="ERROR",
                                   weave_error=f"{type(exc).__name__}:{exc}")
            except Exception as exc:
                row.update(density_status="ERROR",
                           density_error=f"{type(exc).__name__}:{exc}",
                           weave_status="ERROR" if row["weave_status"] == "NOT_RUN"
                           else row["weave_status"])
            row["elapsed_s"] = round(time.monotonic() - start, 4)
            _annotate_truth(row, truth)
            rows.append(row)
            print(f"[{index}/{len(jobs)}] {image_name} "
                  f"density={row['density_status']} weave={row['weave_status']}",
                  flush=True)
    with (out / "all_images.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as f:
        writer = csv.DictWriter(f, FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    both = [r["both_density_within_10pct"] for r in rows
            if r["both_density_within_10pct"] is not None]
    weave = [r["weave_exact_match"] for r in rows
             if r["weave_exact_match"] is not None]
    summary = {
        "archive": args.archive.name,
        "samples": len(rows),
        "unpaired_images_n": sum(r["input_mode"] == "UNPAIRED_IMAGE" for r in rows),
        "inference_mode": "INVENTORY_ONLY" if args.inventory_only else
                          ("PAIRED_R_T" if pairs else "SINGLE_PHOTO_COMPATIBILITY"),
        "density_status_counts": dict(Counter(
            r["density_status"] for r in rows
        )),
        "weave_status_counts": dict(Counter(
            r["weave_status"] for r in rows
        )),
        "scored_density_n": len(both),
        "both_density_within_10pct_n": sum(both),
        "scored_weave_n": len(weave),
        "weave_exact_match_n": sum(weave),
        "caution": [
            "Prediction candidates are not verified physical yarn identities",
            "Observed traces are not necessarily distinct complete yarns",
            "V5 weave candidate is not a verified physical over-under matrix",
            "GT is read only for scoring after inference",
            "Single-photo mode only replicates the historical aligned horizontal-twice baseline",
            "No density is calculated without externally verified mm-per-pixel calibration",
            "Non-numeric or unlabelled predictions are never counted as correct",
        ],
    }
    (out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    return summary


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--truth-csv", type=Path)
    p.add_argument("--pairs-csv", type=Path,
                   help="CSV with sample_id,reflection,transmission")
    p.add_argument("--mm-x", type=float,
                   help="Measured original-image millimeters per pixel on X")
    p.add_argument("--mm-y", type=float,
                   help="Measured original-image millimeters per pixel on Y")
    p.add_argument("--assume-axes-aligned", action="store_true",
                   help="Required for historical single-image horizontal twice")
    p.add_argument("--rois", type=int, choices=[1, 3], default=3)
    p.add_argument("--inventory-only", action="store_true")
    args = p.parse_args(argv)
    print(json.dumps(run(args), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
