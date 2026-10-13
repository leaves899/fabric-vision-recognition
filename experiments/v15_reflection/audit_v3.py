"""Reproducible real-photo DEV diagnostic for V1.5 FFT+ACF v2 vs v3.

No eligible physical 5cm frame / per-axis yarn count GT is present; never
report real density precision, G2 compliance, or held-out TEST accuracy here.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import time
from pathlib import Path

from PIL import Image

from experiments.v15_reflection.engine import axis_angle
from experiments.v15_reflection.orient_v2 import propose_axes as old_axes
from experiments.v15_reflection.orient_v3 import propose_axes as new_axes, axis_distance


def audit(root: Path, rotations=(0,90,180,270)):
    rows = list(csv.DictReader((root/"datasets/manifest.csv").open(encoding="utf-8")))
    labels = {}
    for p in (root/"datasets/annotations/drafts").glob("*.json"):
        x = json.loads(p.read_text(encoding="utf-8"))
        if x.get("review_state")=="OPERATOR_REVIEWED" and x.get("reference_confirmed") is True:
            labels[x["sample_id"]] = x
    cases = []
    for item in rows:
        sid = item["position_id"]
        path = root/item["image_path"]
        case = {"sample_id": sid, "fabric_id": item["fabric_id"],
                "split": item["split"], "frame_confirmed": item["frame_confirmed"],
                "image_path": item["image_path"],
                "physical_gt": "NOT_EVALUATED", "rotation_checks": []}
        if not path.is_file():
            case["status"] = "MISSING_IMAGE"
            cases.append(case)
            continue
        label = labels.get(sid)
        if label and label.get("image_sha256"):
            if hashlib.sha256(path.read_bytes()).hexdigest()!=label["image_sha256"]:
                case["status"] = "SHA_MISMATCH"
                cases.append(case)
                continue
        operator = axis_angle(label["segments"]["reference"]) if label else None
        case["operator_reference_deg"] = round(operator,3) if operator is not None else None
        try:
            with Image.open(path) as image:
                for deg in rotations if operator is not None else (0,):
                    sample = image.rotate(deg,expand=True) if deg else image
                    t0 = time.perf_counter()
                    old = old_axes(sample)
                    old_ms = round((time.perf_counter()-t0)*1000,2)
                    t0 = time.perf_counter()
                    new = new_axes(sample)
                    new_ms = round((time.perf_counter()-t0)*1000,2)
                    ref = (operator+deg)%90 if operator is not None else None
                    def measure(r):
                        theta = r.get("unlabelled_axes_deg")
                        return round(axis_distance(theta[0],ref),3) if theta and ref is not None else None
                    case["rotation_checks"].append({
                        "deg": deg,
                        "v2_status": old["status"], "v2_reason": old.get("reason"),
                        "v2_angle_deg": (old.get("unlabelled_axes_deg") or [None])[0],
                        "v2_operator_error_deg": measure(old), "v2_runtime_ms": old_ms,
                        "v3_status": new["status"], "v3_reason": new.get("reason"),
                        "v3_angle_deg": (new.get("unlabelled_axes_deg") or [None])[0],
                        "v3_operator_error_deg": measure(new), "v3_runtime_ms": new_ms})
            case["status"] = "DIAGNOSTIC_ONLY"
        except (OSError, ValueError, MemoryError) as e:
            case["status"] = "ERROR"
            case["reason"] = str(e)[:180]
        cases.append(case)
    eligible = [x for x in cases if x["status"]=="DIAGNOSTIC_ONLY"]
    reviewed = [x for x in eligible if x["operator_reference_deg"] is not None]
    summary = {"schema": "v15-v3-dev-orientation-1",
        "g2": "NOT_EVALUATED",
        "explanation": "All photos DEV; no independent TEST fabric set / confirmed frame / multi-cutline yarn-count GT",
        "images": len(cases), "readable": len(eligible),
        "distinct_fabric_ids": len({x["fabric_id"] for x in eligible}),
        "reviewed_reference_photos": len(reviewed),
        "frame_confirmed": sum(x["frame_confirmed"]=="YES" for x in eligible),
        "test_images": sum(x["split"]=="TEST" for x in eligible),
        "mean_density_mape": None, "coverage_g2": None,
        "comparisons": {}, "cases": cases}
    for key in ("v2","v3"):
        candidates = [c for c in eligible
                      if c["rotation_checks"][0][key+"_status"]=="PROPOSED_NOT_VALIDATED"]
        audited = [c for c in reviewed
                   if c["rotation_checks"][0][key+"_status"]=="PROPOSED_NOT_VALIDATED"]
        errors = [c["rotation_checks"][0][key+"_operator_error_deg"] for c in audited]
        rotation_consistent = sum(
            all(t[key+"_status"]=="PROPOSED_NOT_VALIDATED" and
                axis_distance(t[key+"_angle_deg"],
                              c["rotation_checks"][0][key+"_angle_deg"])<=3
                for t in c["rotation_checks"][1:])
            for c in reviewed if c["rotation_checks"][0][key+"_status"]=="PROPOSED_NOT_VALIDATED")
        summary["comparisons"][key] = {
            "candidate_count": len(candidates),
            "proposal_fraction": round(len(candidates)/max(len(eligible),1),4),
            "reviewed_candidates": len(audited),
            "reviewed_errors_deg": errors,
            "reviewed_errors_over_5deg": sum(v>5 for v in errors),
            "rotation_consistent_reviewed_candidates": rotation_consistent}
    return summary


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",type=Path,default=Path("."))
    ap.add_argument("--out",type=Path,
                    default=Path("experiments/v15_reflection/output/v3_dev_audit.json"))
    args=ap.parse_args()
    result=audit(args.root)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k!="cases"},
                     ensure_ascii=False,indent=2))
    for c in result["cases"]:
        if c.get("operator_reference_deg") is not None:
            r=c["rotation_checks"][0]
            print(c["sample_id"],r["v2_status"],r["v2_operator_error_deg"],
                  "=>",r["v3_status"],r["v3_operator_error_deg"])
    return 0 if result["readable"]==result["images"] else 2


if __name__=="__main__":
    raise SystemExit(main())
