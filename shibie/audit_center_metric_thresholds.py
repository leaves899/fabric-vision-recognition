from __future__ import annotations
"""Threshold-sensitivity audit on already frozen native-8k R/T predictions.

GT geometry is rebuilt deterministically from the 8k physical simulator's
frozen scene parameters *after* loading image-only inference artifacts. This
audit cannot modify inference output. Recomputed .32 F1 must match the original
label assessment or the entire audit is rejected.
"""
import argparse
import json
import math
from pathlib import Path
import numpy as np
from scipy.optimize import linear_sum_assignment
from synthetic_capture_8k import CaptureScene, camera_matrices, _truth_lines
from run_local_axis_experiment import raw_gt_projected

SCENES={
  "independent_15deg":dict(fabric_rotation_deg=15.,seed=812613,warp_density_cm=30.,weft_density_cm=25.,contrast_polarity="dark"),
  "same_fixture_0deg":dict(fabric_rotation_deg=0.,seed=812613,warp_density_cm=30.,weft_density_cm=25.,contrast_polarity="dark"),
  "plain_25_25_inverted":dict(fabric_rotation_deg=0.,seed=802602,warp_density_cm=25.,weft_density_cm=25.,contrast_polarity="bright"),
}
THRESHOLDS=(.20,.25,.30,.32,.35,.40,.45,.50)


def continuous_distances(pred,truth,pitch):
    a=np.asarray(pred,dtype=np.float64)
    b=np.asarray(truth,dtype=np.float64)
    if len(a)==0 or len(b)==0:
        return {"n_pred":len(a),"n_true":len(b),
          "distance_fraction_quantiles":None,
          "F1_by_threshold":{str(t):0. for t in THRESHOLDS}}
    D=np.abs(a[:,None]-b[None,:])
    idx1,idx2=linear_sum_assignment(D)
    errors=(D[idx1,idx2]/pitch).astype(float)
    # Assignment penalty is continuous, separate from arbitrary cutoff.
    score={}
    for limit in THRESHOLDS:
        hits=int(np.sum(errors<limit))
        score[str(limit)]=round(2*hits/(len(a)+len(b)),4)
    return {"n_pred":len(a),"n_true":len(b),
      "assignment_quantiles_fraction_pitch":{
          str(q):round(float(np.percentile(errors,q)),4) for q in (0,10,25,50,75,90,100)},
      "median_nearest_gt_fraction_pitch":round(float(np.median(np.min(D,axis=0)/pitch)),4),
      "mean_assigned_distance_fraction_pitch":round(float(np.mean(errors)),4),
      "F1_by_threshold":score}


def audit(artifacts:Path, output:Path):
    files=sorted(artifacts.rglob("comparison.json"))
    if len(files)!=3:raise RuntimeError("THREE_FROZEN_AB_CASES_REQUIRED")
    output.mkdir(parents=True,exist_ok=True)
    details=[]
    for file in files:
        recorded=json.loads(file.read_text(encoding="utf-8"))
        scene_name=recorded["case"]
        scene=CaptureScene(name=scene_name,**SCENES[scene_name])
        H,_=camera_matrices(scene)
        truth={"physical_yarn_centerlines":_truth_lines(scene,H)}
        for item in recorded["windows"]:
            family=item["family"]
            pitch=10/(getattr(scene,family+"_density_cm")*scene.mm_per_px)
            M=np.asarray(item["raw_to_tile"],np.float64)
            real=raw_gt_projected(truth,family,M,520)
            results={}
            for variant in ("old","new","midline"):
                proposal=item[variant]
                points=proposal.get("center_positions_px",[]) if proposal.get("status")=="PASS" else []
                results[variant]=continuous_distances(points,real,pitch)
                found=results[variant]["F1_by_threshold"]["0.32"]
                frozen=item["truth_assessment_only"][variant]["f1_proxy"]
                if abs(found-frozen)>0.00011:
                    raise RuntimeError(f"GT_REPRODUCTION_MISMATCH {scene_name} {family} {item['grid']} {variant}: {found} vs {frozen}")
            details.append({"case":scene_name,"family":family,"grid":item["grid"],
                            "pitch_px_truth_evaluation_only":pitch,"results":results})
    lines=["# 8K纱线中心F1阈值稳定性独立复核","",
       "使用冻结的推理输出；重新构造种子固定的物理纱线真值，只在事后评分。",
       "先检查每个窗口的0.32纱距F1与原始评分完全一致，防止真值重构错误。",
       "指标：匈牙利一对一配对；不同阈值计算F1；另记录连续距离分位数。",
       "",
       "| 场景 | 纱线族 | 窗口 | 方法 | F1 @0.25 | F1 @0.32 | F1 @0.40 | 距离中位数/纱距 |",
       "|---|---|---|---|---:|---:|---:|---:|"]
    for item in details:
        if item["case"]=="independent_15deg" and item["family"]=="weft" and item["grid"]==[0,2]:
            for method in ("old","new","midline"):
                d=item["results"][method]
                lines.append(f"| {item['case']} | {item['family']} | {item['grid']} | {method} | "
                    f"{d['F1_by_threshold']['0.25']:.4f} | {d['F1_by_threshold']['0.32']:.4f} | "
                    f"{d['F1_by_threshold']['0.4']:.4f} | "
                    f"{d.get('assignment_quantiles_fraction_pitch',{}).get('50','—')} |")
    (output/"metric_sensitivity.json").write_text(
        json.dumps({"thresholds":THRESHOLDS,"windows":details,
                    "verification":"ALL_FROZEN_0_32_F1_VALUES_REPRODUCED",
                    "scope":"SYNTHETIC_ONLY_NOT_COMPLETE_PHYSICAL_ID_F1"},ensure_ascii=False,indent=2),encoding="utf-8")
    (output/"REPORT.md").write_text("\n".join(lines),encoding="utf-8")
    critical=next(x for x in details if x["case"]=="independent_15deg" and
                  x["family"]=="weft" and x["grid"]==[0,2])
    print("FROZEN_THRESHOLD_SENSITIVITY "+json.dumps({
          "checked_windows":len(details),"critical_case":critical,
          "verification":"ALL_0_32_MATCH"},ensure_ascii=False),flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--artifacts",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    args=p.parse_args()
    audit(args.artifacts,args.out)
