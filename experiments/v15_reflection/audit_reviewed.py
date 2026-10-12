"""Non-certified real-photo audit on operator-reviewed source segments.

Never injects GT into prediction.  Auto FFT axes are checked *after* inference
against independently stored operator two-point segments. The manual-angle
branch is a conditional density/projection analysis, not auto-direction proof.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image

from benchmark.metrics import axis_error_deg
from experiments.v15_reflection.engine import _fft_orientation, axis_angle, measure


def audit(root: Path, annotation_dir: Path, limit: int | None = None):
    rows=[]
    paths=sorted(annotation_dir.glob("*.json"))
    for path in paths:
        label=json.loads(path.read_text(encoding="utf-8"))
        if (label.get("review_state")!="OPERATOR_REVIEWED"
                or label.get("reference_confirmed") is not True
                or not label.get("segments",{}).get("reference")):
            continue
        if limit is not None and len(rows)>=limit: break
        image_path=root/label["image_path"]
        record={"sample_id":label["sample_id"],"fabric_id":label.get("fabric_id"),
                "photo_path":label["image_path"],"review_state":label["review_state"],
                "physical_density_status":"NOT_EVALUATED",
                "reason":"MISSING_CONFIRMED_FRAME_AND_INDEPENDENT_YARN_COUNTS"}
        if not image_path.is_file():
            record["status"]="IMAGE_MISSING"
            rows.append(record)
            continue
        expected_sha=label.get("image_sha256")
        computed_sha=hashlib.sha256(image_path.read_bytes()).hexdigest()
        if expected_sha and expected_sha!=computed_sha:
            record["status"]="IMAGE_HASH_MISMATCH"
            rows.append(record)
            continue
        with Image.open(image_path) as img:
            manual_reference=label["segments"]["reference"]
            manual_deg=axis_angle(manual_reference)
            auto_deg,dispersion=_fft_orientation(img)
            auto_errors=([axis_error_deg(auto_deg,manual_deg),
                          axis_error_deg(auto_deg+90,manual_deg)]
                         if auto_deg is not None else [])
            independent=label["segments"].get("check_same")
            check_deg=axis_angle(independent) if independent else None
            projection=measure(img,manual_reference,True,warp_family=None)
            record.update({
                "status":"RECORDED",
                "manual_reference_axis_deg":round(manual_deg,4),
                "operator_check_same_deg":round(check_deg,4) if check_deg is not None else None,
                "operator_angular_disagreement_deg":round(
                    axis_error_deg(check_deg,manual_deg),4) if check_deg is not None else None,
                "auto_raw_fft_axis_deg":round(auto_deg,4) if auto_deg is not None else None,
                "auto_patch_dispersion_deg":round(dispersion,4) if dispersion is not None else None,
                "auto_output_state":("ABSTAINED" if auto_deg is None or dispersion>8
                                      else "PROPOSED_NOT_VALIDATED"),
                "auto_nearest_axis_error_deg":round(min(auto_errors),4) if auto_errors else None,
                "manual_conditioned_pitch_A_px":projection.get("axes",{}).get("A",{}).get("pitch_px"),
                "manual_conditioned_pitch_B_px":projection.get("axes",{}).get("B",{}).get("pitch_px"),
                "gate2":projection["gate2"]["status"],
                "manual_conditioned_gate3_A":projection.get("axes",{}).get("A",{}).get("gate3"),
                "manual_conditioned_gate3_B":projection.get("axes",{}).get("B",{}).get("gate3"),
                "measured_density_per_cm":None,
                "note":"Auto orientation checked against *operator clicked axis*; no physical yarn ID or density GT",
            })
        rows.append(record)
    proposed=[r for r in rows if r.get("auto_output_state")=="PROPOSED_NOT_VALIDATED"]
    judged=[r for r in rows if r.get("auto_nearest_axis_error_deg") is not None]
    result={"schema_version":"1.0",
            "status":"DIAGNOSTIC_ONLY_NOT_CERTIFIED",
            "operator_reviewed_images":len(rows),
            "auto_proposed":len(proposed),
            "auto_abstained":sum(r.get("auto_output_state")=="ABSTAINED" for r in rows),
            "hash_or_photo_failures":sum(r["status"]!="RECORDED" for r in rows),
            "max_nearest_axis_error_deg":max(
                (r["auto_nearest_axis_error_deg"] for r in judged),default=None),
            "warning":"Same-family operator axis is NOT independent physical-yarn instance GT",
            "results":rows}
    return result


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=Path("."))
    p.add_argument("--annotations",type=Path,default=Path("datasets/annotations/drafts"))
    p.add_argument("--out",type=Path,default=Path("experiments/v15_reflection/output/reviewed_audit.json"))
    p.add_argument("--limit",type=int,default=None)
    args=p.parse_args(argv)
    result=audit(args.root,args.root/args.annotations,args.limit)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k!="results"},ensure_ascii=False))
    for row in result["results"]:
        print(json.dumps({k:row.get(k) for k in ("sample_id","status","auto_output_state",
                          "auto_patch_dispersion_deg","auto_nearest_axis_error_deg",
                          "manual_conditioned_pitch_A_px","manual_conditioned_pitch_B_px")},
                         ensure_ascii=False))
    return 2 if result["hash_or_photo_failures"] else 0


if __name__=="__main__":
    raise SystemExit(main())
