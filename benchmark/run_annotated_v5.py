"""Run unchanged V5 on actually operator-reviewed two-point references.

A reviewed INPUT direction is not independent ground truth. The independent
check segments (when supplied) are diagnostics only, not official accuracy.
"""
from __future__ import annotations

import argparse
import base64
import csv
import json
import math
import sys
from pathlib import Path

from benchmark.manual_annotation import (
    DEFAULT_FOLDER, audit, image_stats, samples, segment_axis_deg, validate_annotation,
)
from benchmark.metrics import axis_error_deg

FIELDS = ("sample_id", "eligibility", "status", "reference_axis_deg",
          "check_same_axis_deg", "check_cross_axis_deg",
          "v5_family_a_deg", "v5_family_b_deg",
          "independent_same_error_deg", "independent_cross_error_deg",
          "family_identity", "result_json", "three_panel", "error")


def check_segments(result: dict, annotation: dict) -> dict:
    """Compare frozen candidate axes with OTHER marked physical yarn segments."""
    evidence = result.get("direction_evidence") or {}
    seg = annotation.get("segments") or {}
    outputs = {}
    for kind, family, error_name in (
        ("check_same", "family_a_deg", "independent_same_error_deg"),
        ("check_cross", "family_b_deg", "independent_cross_error_deg"),
    ):
        coords = seg.get(kind)
        if not coords:
            outputs[error_name] = None
            continue
        value = evidence.get(family)
        if value is None or not math.isfinite(float(value)):
            outputs[error_name] = None
        else:
            outputs[error_name] = round(axis_error_deg(float(value), segment_axis_deg(coords)), 4)
    return outputs


def reviewed_inputs(root: Path, ids: list[str] | None = None):
    mapping = samples(root)
    explicit = set(ids) if ids else None
    if explicit and (explicit - set(mapping)):
        raise ValueError("unknown sample IDs: " + ",".join(sorted(explicit - set(mapping))))
    for sid, row in mapping.items():
        if explicit is not None and sid not in explicit:
            continue
        path = root / DEFAULT_FOLDER / (sid + ".json")
        if not path.is_file():
            continue
        data = validate_annotation(root, json.loads(path.read_text(encoding="utf-8")))
        if data["eligibility"] == "NEGATIVE_NON_DENIM":
            continue
        if data["review_state"] != "OPERATOR_REVIEWED" or not data["reference_confirmed"]:
            continue
        if not data["segments"]["reference"]:
            continue
        yield row, data


def run(root: Path, out: Path, ids: list[str] | None, max_images: int) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    plan = list(reviewed_inputs(root, ids))
    selected = plan[:max_images] if max_images > 0 else plan
    records = []
    if selected:
        sys.path.insert(0, str(root / "demo/v5"))
        from v4_analysis import analyze  # exact original V5, no changes or auto-directions
    for row, manual in selected:
        sid = manual["sample_id"]
        record = {key: "" for key in FIELDS}
        record.update(sample_id=sid, eligibility=manual["eligibility"],
                      family_identity=manual["reference_family"],
                      reference_axis_deg=round(segment_axis_deg(manual["segments"]["reference"]), 4))
        try:
            original_path = root / row["image_path"]
            source_bytes = original_path.read_bytes()
            # EXIF display-pixel coordinates must agree with the existing V5 decoder.
            import cv2
            import numpy as np
            decoded = cv2.imdecode(np.frombuffer(source_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
            if decoded is None or decoded.shape[1] != manual["image_width"] or decoded.shape[0] != manual["image_height"]:
                raise ValueError("image display orientation differs from V5 OpenCV; re-annotate with a canonical orientation")
            warp_family = ("A" if manual["reference_family"] == "WARP" else
                           ("B" if manual["reference_family"] == "WEFT" else None))
            result, visuals = analyze(
                source_bytes, corners=None, confirm_corners=False,
                reference_points=manual["segments"]["reference"],
                confirm_reference=True, warp_family=warp_family,
                weave_override=None, confirm_weave=False,
            )
            folder = out / sid
            folder.mkdir(parents=True, exist_ok=True)
            rel_result = str((folder / "v5_result.json").relative_to(root)) if folder.is_relative_to(root) else str(folder / "v5_result.json")
            (folder / "v5_result.json").write_text(json.dumps({"result": result}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            uri = visuals.get("three_panel", "")
            if not uri.startswith("data:image/jpeg;base64,"):
                raise ValueError("V5 did not return the JPEG evidence panel")
            (folder / "v5_three_panel.jpg").write_bytes(base64.b64decode(uri.split(",", 1)[1], validate=True))
            scores = check_segments(result, manual)
            record.update(
                status="CANDIDATE_DIAGNOSTIC",
                v5_family_a_deg=result["direction_evidence"]["family_a_deg"] or "",
                v5_family_b_deg=result["direction_evidence"]["family_b_deg"] or "",
                independent_same_error_deg=scores["independent_same_error_deg"] if scores["independent_same_error_deg"] is not None else "",
                independent_cross_error_deg=scores["independent_cross_error_deg"] if scores["independent_cross_error_deg"] is not None else "",
                check_same_axis_deg=round(segment_axis_deg(manual["segments"]["check_same"]),4) if manual["segments"]["check_same"] else "",
                check_cross_axis_deg=round(segment_axis_deg(manual["segments"]["check_cross"]),4) if manual["segments"]["check_cross"] else "",
                result_json=str(folder / "v5_result.json"),
                three_panel=str(folder / "v5_three_panel.jpg"),
            )
        except Exception as exc:
            record["status"] = "FAILED"
            record["error"] = f"{type(exc).__name__}: {str(exc)[:400]}"
        records.append(record)
    output = out / "comparison.csv"
    with output.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)
    summary = {
        "status": "CANDIDATES_REQUIRING_REVIEW" if any(r["status"]=="CANDIDATE_DIAGNOSTIC" for r in records) else "NOT_EVALUATED",
        "available_human_reviewed_inputs": len(plan), "run_count": len(selected),
        "completed": sum(r["status"]=="CANDIDATE_DIAGNOSTIC" for r in records),
        "failed": sum(r["status"]=="FAILED" for r in records),
        "different_same_direction_check_count": sum(r["independent_same_error_deg"] != "" for r in records),
        "different_cross_direction_check_count": sum(r["independent_cross_error_deg"] != "" for r in records),
        "note": "V5 input angle is operator supplied. Diagnostics compare candidate group A/B to DIFFERENT manually chosen yarn segments, not to the input itself. Not an automated-direction or physical-density accuracy certificate.",
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    return summary


def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description="Run frozen V5 on operator-reviewed reference photo annotations")
    parser.add_argument("--ids",nargs="*",help="registered public photo IDs such as T001 T004")
    parser.add_argument("--max-images",type=int,default=1,help="safety cap; 0 means all reviewed")
    parser.add_argument("--out",type=Path,default=Path("experiments/v5-manual-round1"))
    args=parser.parse_args(argv)
    root=Path(__file__).resolve().parents[1]
    output = args.out if args.out.is_absolute() else root / args.out
    try:
        result=run(root,output,args.ids,args.max_images)
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as exc:
        print(f"ANNOTATION_ERROR: {exc}")
        return 2
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result["completed"] else 3


if __name__=="__main__":
    raise SystemExit(main())
