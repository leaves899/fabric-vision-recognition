"""Experimental native-pixel ROI around human reviewed segments.

This is NOT a full-image V5 result. ROI clipping preserves pixel scale but
changes context and candidate counts. It never modifies the frozen V4/V5 source.
"""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import math
import sys
from pathlib import Path

from benchmark.manual_annotation import samples, segment_axis_deg, validate_annotation
from benchmark.run_annotated_v5 import check_segments


def crop_window(data: dict, margin: int):
    """Return (x0,y0,x1,y1) enclosing all supplied human-labeled segments."""
    if not isinstance(margin, int) or margin < 0:
        raise ValueError("nonnegative integer margin required")
    pts = [xy for points in data["segments"].values() if points for xy in points]
    if len(pts) < 2:
        raise ValueError("at least one complete reference is required")
    w, h = data["image_width"], data["image_height"]
    x0 = max(0, math.floor(min(p[0] for p in pts)) - margin)
    y0 = max(0, math.floor(min(p[1] for p in pts)) - margin)
    x1 = min(w, math.ceil(max(p[0] for p in pts)) + margin)
    y1 = min(h, math.ceil(max(p[1] for p in pts)) + margin)
    if x1 - x0 < 128 or y1 - y0 < 128:
        raise ValueError("selected crop is too small for V4")
    return x0, y0, x1, y1


def run(root: Path, sid: str, out: Path, *, margin_px: int = 380,
        max_pixels: int = 3_000_000) -> dict:
    mapping = samples(root)
    if sid not in mapping:
        raise ValueError(f"unknown public sample ID: {sid}")
    annotation_path = root / "datasets/annotations/drafts" / (sid + ".json")
    if not annotation_path.is_file():
        raise ValueError("missing operator annotation: " + sid)
    manual = validate_annotation(root, json.loads(annotation_path.read_text(encoding="utf-8")))
    if manual["review_state"] != "OPERATOR_REVIEWED" or not manual["reference_confirmed"]:
        raise ValueError("operator has not confirmed a real-yarn reference")
    if manual["eligibility"] == "NEGATIVE_NON_DENIM":
        raise ValueError("non-denim negative sample excluded from denim main comparison")
    x0, y0, x1, y1 = crop_window(manual, margin_px)
    if (x1-x0)*(y1-y0) > max_pixels:
        raise ValueError(f"native-pixel crop exceeds safety limit {max_pixels} pixels")
    import cv2
    import numpy as np
    original = (root / mapping[sid]["image_path"]).read_bytes()
    img = cv2.imdecode(np.frombuffer(original, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None or tuple(img.shape[:2][::-1]) != (manual["image_width"], manual["image_height"]):
        raise ValueError("OpenCV image decode orientation differs from operator-reviewed coordinates")
    cropped = img[y0:y1, x0:x1].copy()
    ok, encoded = cv2.imencode(".png", cropped)
    if not ok:
        raise ValueError("failed to encode native scale ROI")
    rel_reference = [
        [round(point[0]-x0,3), round(point[1]-y0,3)]
        for point in manual["segments"]["reference"]
    ]
    from_v5 = root / "demo/v5"
    sys.path.insert(0,str(from_v5))
    from v4_analysis import analyze
    warp_family = ("A" if manual["reference_family"]=="WARP" else
                   ("B" if manual["reference_family"]=="WEFT" else None))
    output, visuals = analyze(encoded.tobytes(),corners=None,confirm_corners=False,
                              reference_points=rel_reference, confirm_reference=True,
                              warp_family=warp_family, weave_override=None,confirm_weave=False)
    errors=check_segments(output,manual)
    out.mkdir(parents=True,exist_ok=True)
    meta={
        "mode": "NATIVE_PIXEL_ROI_EXPERIMENT_NOT_FULL_PHOTO",
        "sample_id":sid, "original_image_sha256":hashlib.sha256(original).hexdigest(),
        "original_size_px":[img.shape[1],img.shape[0]],
        "crop_xyxy_original_px":[x0,y0,x1,y1],
        "cropped_pixel_size_px":[x1-x0,y1-y0],
        "pixel_scale_changed":False,
        "reference_points_original_px":manual["segments"]["reference"],
        "reference_points_crop_px":rel_reference,
        "note":"Image context was cropped around operator-confirmed segments. V4/V5 code is unchanged. Counts and lines cannot be extrapolated to full photo or cm.",
    }
    (out/"v5_result.json").write_text(
        json.dumps({"result":output,"original_image_provenance":meta},ensure_ascii=False,indent=2)+"\n",
        encoding="utf-8")
    uri=visuals.get("three_panel","")
    if not uri.startswith("data:image/jpeg;base64,"):
        raise ValueError("V5 did not return a JPEG three-panel evidence")
    (out/"v5_three_panel.jpg").write_bytes(base64.b64decode(uri.split(",",1)[1],validate=True))
    result={
        "sample_id":sid,"status":"CANDIDATE_ROI_ONLY","roi_original_xyxy":meta["crop_xyxy_original_px"],
        "original_width":img.shape[1], "original_height":img.shape[0],
        "roi_width":cropped.shape[1],"roi_height":cropped.shape[0],
        "operator_reference_axis_deg":round(segment_axis_deg(manual["segments"]["reference"]),4),
        "different_human_check_axis_deg":(
            round(segment_axis_deg(manual["segments"]["check_same"]),4)
            if manual["segments"]["check_same"] else None),
        "v5_family_a_axis_deg":output["direction_evidence"]["family_a_deg"],
        "v5_family_b_axis_deg":output["direction_evidence"]["family_b_deg"],
        "angle_error_vs_different_checked_yarn_deg":errors["independent_same_error_deg"],
        "v4_family_a_candidate_lines":output["v4"]["family_a_candidate_lines"],
        "v4_family_b_candidate_lines":output["v4"]["family_b_candidate_lines"],
        "confirmed_warp_or_weft":manual["reference_family"] if manual["identity_confirmed"] else "UNKNOWN",
        "physical_density_evaluable":False,
        "note":"Candidate angle follows human V5 reference; angle agreement is not proof of automatic direction recognition or individually real yarns.",
    }
    (out/"summary.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return result


def main(argv=None):
    p=argparse.ArgumentParser(description="Run frozen V5 on a clipped native-resolution ROI; NOT a full photo")
    p.add_argument("--id",required=True,help="reviewed source sample ID, e.g. T004")
    p.add_argument("--margin-px",type=int,default=380)
    p.add_argument("--max-pixels",type=int,default=3_000_000)
    p.add_argument("--out",type=Path,default=Path("experiments/v5-reviewed-roi"))
    args=p.parse_args(argv)
    root=Path(__file__).resolve().parents[1]
    out=args.out if args.out.is_absolute() else root/args.out
    try:
        result=run(root,args.id,out,margin_px=args.margin_px,max_pixels=args.max_pixels)
    except Exception as exc:
        print(f"V5_ROI_ERROR: {type(exc).__name__}: {str(exc)}")
        return 2
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
