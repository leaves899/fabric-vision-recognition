"""Independent DEV diagnostics against operator physical-yarn *direction* labels.

Uses latest main's native 2x unmarked images with image SHA256 verification.
The annotations are references to full physical yarn direction, NOT confirmed
pixel-level visible yarn segments or 5 cm metric-density truth.
Never evaluate seam-map pixel recall or pitch accuracy from these annotations.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import cv2
import numpy as np

from .symmetric_valley_user_v2 import detect_true_yarn_directions_v2
from .symmetric_valley_user_v3 import detect_and_verify_physical_yarns_v3

IDS = ("U20261013_01", "U20261013_02", "U20261013_03",
       "U20261013_05", "U20261013_06")
BASE = "datasets/annotations/drafts"


def diff180(a, b):
    return abs((float(a)-float(b)+90.)%180.-90.)


def axis(p, q):
    return float(math.degrees(math.atan2(q[1]-p[1],q[0]-p[0]))%180.)


def family_axis(segments):
    z = np.mean(np.exp(2j*np.deg2rad(segments)))
    return float(np.rad2deg(np.angle(z))/2%180.)


def reference_pair(meta):
    group_a=[axis(*meta["segments"][name]) for name in
             ("reference","check_same","holdout_same")]
    group_b=[axis(*meta["segments"][name]) for name in
             ("check_cross","check_cross_second")]
    return (family_axis(group_a),family_axis(group_b)), {
        "same_raw_angles_deg":group_a,"cross_raw_angles_deg":group_b,
        "same_dispersion_deg":max(diff180(a,family_axis(group_a)) for a in group_a),
        "cross_dispersion_deg":max(diff180(a,family_axis(group_b)) for a in group_b),
    }


def audit(root: Path):
    rows=[]
    for sample_id in IDS:
        p=root / BASE / (sample_id+".json")
        meta=json.loads(p.read_text(encoding="utf8"))
        assert meta["annotation_target"]=="PHYSICAL_YARN_REFERENCE",sample_id
        assert meta["reference_confirmed"] is True,sample_id
        assert meta["visible_pixel_gt_confirmed"] is False,sample_id
        assert meta["centerline_pixel_gt_confirmed"] is False,sample_id
        im_path=root / meta["image_path"]
        data=im_path.read_bytes()
        digest=hashlib.sha256(data).hexdigest()
        assert digest == meta["image_sha256"],sample_id
        image=cv2.imdecode(np.frombuffer(data,np.uint8),cv2.IMREAD_COLOR)
        assert image is not None and image.shape[1]==meta["image_width"] and image.shape[0]==meta["image_height"],sample_id
        axes,details=reference_pair(meta)
        run_v2=detect_true_yarn_directions_v2(image)
        run_v3=detect_and_verify_physical_yarns_v3(image)
        row={"sample_id":sample_id,"image_sha256_verified":True,
             "reference_angles_deg":tuple(round(a,3) for a in axes),
             "reference_meta":details}
        for name,r in (("v2",run_v2),("v3",run_v3)):
            accepted=bool(r["accepted"])
            candidate=r["warp_or_dom_deg"] if accepted else None
            row[name]={"accepted":accepted,
                       "image_axis_candidate_deg":candidate,
                       "error_to_nearest_physical_yarn_family_deg":
                        round(min(diff180(candidate,a) for a in axes),3)
                        if candidate is not None else None,
                       "macro_texture_angle_deg":round(float(r["pattern_deg"]),3),
                       "macro_pattern_separation_deg":
                        round(diff180(candidate,r["pattern_deg"]),3)
                        if candidate is not None else None}
            if name=="v3":
                row[name]["raw_reject_reason"]=r.get("reject_reason")
                row[name]["raw_pitch_proxy_px"]=r.get("estimated_yarn_pitch_px")
                row[name]["physical_pitch_proven"]=False
                row[name]["cross_occlusion_identity_verified"]=False
        rows.append(row)
    summary={"eligible_operator_reviewed_samples":len(rows),"excluded_no_operator_reference":["U20261013_04"]}
    for ver in ("v2","v3"):
        accepted=[r[ver] for r in rows if r[ver]["accepted"]]
        error=[r["error_to_nearest_physical_yarn_family_deg"] for r in accepted]
        summary[ver]={
            "accepted":len(accepted),
            "coverage":len(accepted)/len(rows),
            "angle_error_mean_deg":round(float(np.mean(error)),3) if error else None,
            "angle_error_max_deg":round(max(error),3) if error else None,
            "accepted_within_3deg":sum(e<=3 for e in error),
            "accepted_within_5deg":sum(e<=5 for e in error),
            "accepted_over_8deg":sum(e>8 for e in error),
            "macro_pattern_within_8deg":sum(r["macro_pattern_separation_deg"]<=8 for r in accepted)
        }
    return {"status":"RESEARCH_DIAGNOSTIC_NOT_RELEASE_CERTIFICATION",
            "reference_semantics":"Operator-confirmed physical-yarn direction, NOT visible centerline-pixel labels",
            "physical_yarn_pitch_ground_truth":False,
            "metric_5cm_frame_confirmed":False,
            "samples":rows,"summary":summary}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--dataset-root",required=True,type=Path)
    parser.add_argument("--out",required=True,type=Path)
    a=parser.parse_args()
    report=audit(a.dataset_root)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    print(json.dumps(report["summary"],ensure_ascii=False,indent=2))
    for r in report["samples"]:
        print(r["sample_id"],"truth",r["reference_angles_deg"],
              "V2",r["v2"]["image_axis_candidate_deg"],r["v2"]["error_to_nearest_physical_yarn_family_deg"],
              "V3",r["v3"]["image_axis_candidate_deg"],r["v3"]["error_to_nearest_physical_yarn_family_deg"])

if __name__=="__main__":
    main()
