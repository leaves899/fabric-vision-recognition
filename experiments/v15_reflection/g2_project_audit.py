"""Evaluate independent auto-orientation and rotation robustness with existing repo.

Ground-truth is operator-clicked axis directions, never used to infer a photo.
All 66 manifest records are DEV / uncalibrated; NO test accuracy certification.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from PIL import Image

from experiments.v15_reflection.engine import _fft_orientation, axis_angle
from experiments.v15_reflection.orient_v2 import propose_axes, _canonical_delta


def _angles(theta,human):
    return round(_canonical_delta(theta,human),3) if theta is not None else None


def evaluate(root:Path,rotations=(0,90,180,270),limit=None):
    manifest=list(csv.DictReader((root/"datasets/manifest.csv").open(encoding="utf-8")))
    # Every row in this inventory is a separate photo but NOT certified GT.
    annotation_dir=root/"datasets/annotations/drafts"
    labels={}
    for p in annotation_dir.glob("*.json"):
        raw=json.loads(p.read_text(encoding="utf-8"))
        if raw.get("review_state")=="OPERATOR_REVIEWED" and raw.get("reference_confirmed") is True:
            labels[raw["sample_id"]]=raw
    results=[]
    for record in manifest[:limit]:
        path=root/record["image_path"]
        entry={"sample_id":record["position_id"],"fabric_id":record["fabric_id"],
               "split":record["split"],"image_path":record["image_path"],
               "frame_confirmed":record["frame_confirmed"],
               "gt_status":"NOT_EVALUATED","physical_density_per_cm":None}
        if not path.is_file():
            entry.update(status="MISSING_IMAGE")
            results.append(entry)
            continue
        label=labels.get(record["position_id"])
        if label is not None and label.get("image_sha256"):
            if label["image_sha256"]!=hashlib.sha256(path.read_bytes()).hexdigest():
                entry.update(status="SHA_MISMATCH")
                results.append(entry)
                continue
        try:
            with Image.open(path) as original:
                original.load()
                reference=axis_angle(label["segments"]["reference"]) if label else None
                entry["operator_reviewed_reference_deg"]=round(reference,3) if reference is not None else None
                out=[]
                # Rotate audited photos at 0,90,180,270; unreviewed once to
                # avoid conflating self-consistency with independent GT.
                degrees=rotations if label else (0,)
                for deg in degrees:
                    img=original.rotate(deg,expand=True) if deg else original
                    v2=propose_axes(img)
                    old,disp=_fft_orientation(img)
                    expected=((reference+deg)%90) if reference is not None else None
                    out.append({"rotation_deg":deg,
                                "v2":v2,
                                "v2_operator_error_deg":(
                                   _angles(v2["unlabelled_axes_deg"][0],expected)
                                   if v2["unlabelled_axes_deg"] is not None else None),
                                "fft_raw_axis_deg":round(old,3) if old is not None else None,
                                "fft_dispersion_deg":round(disp,3) if disp is not None else None,
                                "fft_operator_error_deg":_angles(old,expected)})
                baseline=out[0]["v2"]
                comparison=[_angles(o["v2"]["unlabelled_axes_deg"][0],
                                   baseline["unlabelled_axes_deg"][0])
                            for o in out[1:]
                            if baseline["unlabelled_axes_deg"] is not None
                            and o["v2"]["unlabelled_axes_deg"] is not None]
                entry.update(status="DIAGNOSTIC_ONLY",orientation=out,
                             rotation_max_disagreement_deg=max(comparison,default=None))
        except (OSError,ValueError,MemoryError) as e:
            entry.update(status="ERROR",reason=f"{type(e).__name__}: {str(e)[:200]}")
        results.append(entry)
        if len(results)%10==0: print(f"processed {len(results)}/{len(manifest[:limit])}",flush=True)
    annotated=[r for r in results if r.get("operator_reviewed_reference_deg") is not None]
    usable=[r for r in results if r.get("status")=="DIAGNOSTIC_ONLY"]
    proposals=[r for r in usable if r["orientation"][0]["v2"]["status"]=="PROPOSED_NOT_VALIDATED"]
    accepted_with_review=[r for r in annotated
          if r["orientation"][0]["v2"]["status"]=="PROPOSED_NOT_VALIDATED"]
    report={"goal":"G2","certified":"NOT_EVALUATED",
            "reason":"No confirmed physical frame/count GT and all manifest rows are DEV",
            "total_manifest_images":len(manifest),
            "audited":len(results),"readable":len(usable),
            "reviewed_reference_count":len(annotated),
            "confirmed_gt_rows":0,
            "confirmed_frame_rows":sum(r["frame_confirmed"]=="YES" for r in manifest),
            "manifest_split_counts":{key:sum(r["split"]==key for r in manifest)
                                     for key in ("DEV","VALIDATION","TEST")},
            "auto_proposals":len(proposals),
            "operator_reviewed_proposals":len(accepted_with_review),
            "operator_reviewed_angular_errors_deg":[
                r["orientation"][0]["v2_operator_error_deg"] for r in accepted_with_review],
            "rotation_max_error_deg":max((r["rotation_max_disagreement_deg"]
                    for r in annotated if r.get("rotation_max_disagreement_deg") is not None),default=None),
            "results":results}
    return report


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("--root",type=Path,default=Path("."))
    parser.add_argument("--out",type=Path,default=Path("experiments/v15_reflection/output/g2_project_images.json"))
    parser.add_argument("--limit",type=int,default=None)
    args=parser.parse_args(argv)
    r=evaluate(args.root,limit=args.limit)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(r,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in r.items() if k!="results"},ensure_ascii=False,indent=2))
    for sample in r["results"]:
        if sample.get("operator_reviewed_reference_deg") is not None:
            v=sample["orientation"][0]
            print(json.dumps({"sample":sample["sample_id"],
                  "new_state":v["v2"]["status"],"reason":v["v2"].get("reason"),
                  "new_err":v["v2_operator_error_deg"],
                  "old_err":v["fft_operator_error_deg"],
                  "rotation_disagreement":sample["rotation_max_disagreement_deg"]}))
    return 0 if len(r["results"])==len(r["results"]) and not any(
        x["status"] in ("MISSING_IMAGE","SHA_MISMATCH","ERROR") for x in r["results"]) else 2


if __name__=="__main__":
    raise SystemExit(main())
