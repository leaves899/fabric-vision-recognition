"""Unchanged V5 vs opt-in G1.2; PR16 annotation lines used for metrics ONLY."""
from __future__ import annotations
import argparse,hashlib,json,shutil,sys
from pathlib import Path
import cv2
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"demo/v5"))
from v4_adapter import run_v4
from v4_scoremap_probe import read_original_model_scores
from v51_g12_refinement import refine_v5_g12
from benchmark.v5_pr16_local_evidence_audit import run as audit
from benchmark.manual_annotation import validate_annotation

KEYS=("local_strokes_covered_at_least_60pct_within_5px",
      "local_strokes_covered_at_least_60pct_within_10px",
      "local_strokes_covered_at_least_60pct_within_quarter_pitch",
      "local_strokes_covered_at_least_60pct_within_half_pitch")

def evaluate(sid,base_dir,out_dir):
    out_dir.mkdir(parents=True,exist_ok=True)
    metadata=json.loads((base_dir/"v5_result.json").read_text(encoding="utf-8"))
    ann=validate_annotation(ROOT,json.loads((ROOT/"datasets/annotations/drafts"/(sid+".json")).read_text(encoding="utf-8")))
    source=(ROOT/ann["image_path"]).read_bytes()
    meta=metadata["original_image_provenance"]
    if hashlib.sha256(source).hexdigest()!=meta["original_image_sha256"]:
        raise ValueError("Source photo changed; refuse comparison")
    photo=cv2.imdecode(np.frombuffer(source,np.uint8),cv2.IMREAD_COLOR)
    x0,y0,x1,y1=meta["crop_xyxy_original_px"]
    roi=photo[y0:y1,x0:x1]
    if [roi.shape[1],roi.shape[0]]!=meta["cropped_pixel_size_px"]:
        raise ValueError("ROI geometry mismatch")
    angle=float(metadata["result"]["direction_evidence"]["v4_adapter_rotation_deg"])
    baseline=run_v4(roi,angle)
    scores=read_original_model_scores(roi,angle)
    if scores["frozen_sha256"]!=baseline["frozen_sha256"]:
        raise ValueError("Frozen source digest mismatch")
    output=refine_v5_g12(roi,baseline,scores)
    assert len(output["first"])==len(baseline["first"])
    assert len(output["second"])==len(baseline["second"])
    if not (base_dir/"pr16_local_evidence_v5_audit.json").exists():
        audit(sid,base_dir)
    old=json.loads((base_dir/"pr16_local_evidence_v5_audit.json").read_text(encoding="utf-8"))
    shutil.copy2(base_dir/"v5_result.json",out_dir/"v5_result.json")
    new=audit(sid,out_dir,track_override=output)
    def before_after(label):
        a,b=old[label],new[label]
        return {"n_image_only_draft_strokes":a["parallel_and_inside_roi"],
                "baseline":{key:a[key] for key in KEYS},
                "proposed":{key:b[key] for key in KEYS},
                "difference":{key:b[key]-a[key] for key in KEYS},
                "baseline_median_nearest_track_px":a["median_nearest_track_px"],
                "proposed_median_nearest_track_px":b["median_nearest_track_px"]}
    if (base_dir/"pr16_local_strokes_overlay.jpg").exists() and (out_dir/"pr16_local_strokes_overlay.jpg").exists():
        left=cv2.imread(str(base_dir/"pr16_local_strokes_overlay.jpg"))
        right=cv2.imread(str(out_dir/"pr16_local_strokes_overlay.jpg"))
        if left is not None and right is not None:
            if left.shape!=right.shape:
                right=cv2.resize(right,(left.shape[1],left.shape[0]))
            cv2.imwrite(str(out_dir/"g12_frozen_v5_side_by_side.jpg"),np.hstack([left,right]))
    report={"sample_id":sid,"status":"UNVALIDATED_MODEL_PHOTO_GATED_REFINEMENT",
            "frozen_v4":baseline["frozen_sha256"],"v5_code_unchanged":True,
            "scores_read_only":scores["model_score_source"],
            "A":{"count":len(output["first"]),"changed":output["first_report"]["changed"],
                 "abstained":output["first_report"]["abstained"]},
            "B":{"count":len(output["second"]),"changed":output["second_report"]["changed"],
                 "abstained":output["second_report"]["abstained"]},
            "visible_yarn":before_after("apparent_visible_yarn"),
            "twill_pattern":before_after("twill_pattern"),
            "same_track_relation":{"original":old["relations"],"new":new["relations"]},
            "model_training_not_modified":True,
            "operator_labels_used_during_localization":False,
            "accuracy_claim":None,"physical_yarn_count_verified":False}
    (out_dir/"v51_g12_report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (out_dir/"v51_g12_tracks_and_evidence.json").write_text(json.dumps({
        "first":output["first"],"second":output["second"],
        "A":output["first_report"],"B":output["second_report"],
        "no_operator_data_in_inference":True},ensure_ascii=False),encoding="utf-8")
    print("G12_RESULT_JSON="+json.dumps(report,ensure_ascii=False,sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--id",required=True)
    p.add_argument("--baseline-dir",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    evaluate(a.id,ROOT/a.baseline_dir,ROOT/a.out)
