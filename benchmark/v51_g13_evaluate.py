"""Independent A3 geometric holdout for optional A1/A2 assisted V5 grid.

Never use A3 or local apparent-yarn draft labels to calibrate/accept a model.
"""
from __future__ import annotations
import argparse,hashlib,json,shutil,sys
from pathlib import Path
import cv2
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"demo/v5"))
from v4_adapter import run_v4
from benchmark.manual_annotation import validate_annotation
from benchmark.yarn_phase_anchor import median_distance,normal_to_segment
from benchmark.v51_g13_assisted_lattice import assisted_first_family
from benchmark.v5_pr16_local_evidence_audit import run as local_audit

def run(sid,base,out):
    out.mkdir(parents=True,exist_ok=True)
    raw=json.loads((base/"v5_result.json").read_text(encoding="utf-8"))
    meta=raw["original_image_provenance"]
    ann=validate_annotation(ROOT,json.loads((ROOT/"datasets/annotations/drafts"/(sid+".json")).read_text(encoding="utf-8")))
    photo=(ROOT/ann["image_path"]).read_bytes()
    if hashlib.sha256(photo).hexdigest()!=meta["original_image_sha256"]:
        raise ValueError("Stale reference photo")
    image=cv2.imdecode(np.frombuffer(photo,np.uint8),cv2.IMREAD_COLOR)
    x0,y0,x1,y1=meta["crop_xyxy_original_px"]
    crop=image[y0:y1,x0:x1]
    angle=float(raw["result"]["direction_evidence"]["v4_adapter_rotation_deg"])
    tracks=run_v4(crop,angle)
    if not all(ann["segments"].get(k) for k in ("reference","check_same","holdout_same")):
        raise ValueError("Need separate A1, A2 and strictly held-out A3")
    def local(k):
        return (np.asarray(ann["segments"][k],float)-[x0,y0]).tolist()
    A1=local("reference");A2=local("check_same")
    # Important: A3 is NOT loaded or supplied to assisted_first_family.
    corrected,diag=assisted_first_family(
        tracks["first"],A1,A2,physical_intervals=ann.get("same_family_intervals"),
        confirmed=ann.get("same_family_intervals_confirmed") is True)
    A3=local("holdout_same")  # read ONLY after both candidate solutions fixed
    before=median_distance(A3,tracks["first"])
    after=median_distance(A3,corrected)
    normal=normal_to_segment(A1)
    physical_pitch=abs(float(np.dot(np.mean(np.asarray(A2)-np.asarray(A1),axis=0),normal)))/ann["same_family_intervals"]
    report={"sample_id":sid,"mode":"OPTIONAL_A1_A2_ASSISTED_NOT_AUTOMATIC",
            "source_frozen_v4_sha256":tracks["frozen_sha256"],
            "first_candidates_before":len(tracks["first"]),
            "first_candidates_after":len(corrected),
            "second_candidates_before_and_after":len(tracks["second"]),
            "assisted_algorithm":diag,
            "A3_holdout_measured_only_after_inference":True,
            "A3_baseline_median_distance_px":before,
            "A3_assisted_median_distance_px":after,
            "A3_difference_px":round(after-before,3) if before is not None and after is not None else None,
            "physical_operator_pitch_2x_px":round(physical_pitch,3),
            "A3_baseline_distance_as_fraction_of_operator_pitch":round(before/physical_pitch,3) if before is not None and physical_pitch>0 else None,
            "A3_assisted_distance_as_fraction_of_operator_pitch":round(after/physical_pitch,3) if after is not None and physical_pitch>0 else None,
            "A3_is_exact_pixel_center_truth":False,
            "actual_physical_yarn_count_verified":False,
            "note":"A3 is a separate approximate yarn reference through occlusion, NOT a visible-yarn pixel mask."}
    if (base/"pr16_local_evidence_v5_audit.json").exists():
        shutil.copy2(base/"v5_result.json",out/"v5_result.json")
        previous=json.loads((base/"pr16_local_evidence_v5_audit.json").read_text(encoding="utf-8"))
        post=local_audit(sid,out,track_override={"first":corrected,"second":tracks["second"]})
        keys=("local_strokes_covered_at_least_60pct_within_5px",
              "local_strokes_covered_at_least_60pct_within_half_pitch")
        report["draft_local_line_metrics_not_physical_GT"]={
          key:{"original":previous["apparent_visible_yarn"][key],
               "assisted":post["apparent_visible_yarn"][key]}
          for key in keys}
    (out/"g13_A3_holdout_report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (out/"g13_assisted_tracks.json").write_text(json.dumps({
        "A":corrected,"B_UNCHANGED":tracks["second"],
        "A3_used_to_calibrate":False},ensure_ascii=False),encoding="utf-8")
    print("G13_RESULT_JSON="+json.dumps(report,ensure_ascii=False,sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--id",required=True)
    p.add_argument("--baseline-dir",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    run(a.id,ROOT/a.baseline_dir,ROOT/a.out)
