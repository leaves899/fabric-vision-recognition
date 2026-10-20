from __future__ import annotations
"""Re-score immutable R/T inference artifacts; never tune with truth."""
import argparse
import json
from pathlib import Path
import numpy as np
from synthetic_capture_8k import CaptureScene,camera_matrices,_truth_lines
from run_local_axis_experiment import raw_gt_projected
from evaluate_center_matching import cardinality_gated_yarn_match
from audit_center_metric_thresholds import SCENES


def replay(source:Path,out:Path):
    files=sorted(source.rglob("comparison.json"))
    if len(files)!=3:raise RuntimeError("FROZEN_THREE_CASE_REPLAY_REQUIRED")
    out.mkdir(parents=True,exist_ok=True)
    records=[]
    averages=[]
    for file in files:
        run=json.loads(file.read_text(encoding="utf-8"))
        case=run["case"]
        scene=CaptureScene(name=case,**SCENES[case])
        H,_=camera_matrices(scene)
        truth={"physical_yarn_centerlines":_truth_lines(scene,H)}
        for family in ("warp","weft"):
            subset=[]
            for row in run["windows"]:
                if row["family"]!=family:continue
                pitch=10/(getattr(scene,family+"_density_cm")*scene.mm_per_px)
                b=raw_gt_projected(truth,family,np.asarray(row["raw_to_tile"],float),520)
                oldrow={"case":case,"family":family,"grid":row["grid"],
                        "true_pitch_px_evaluation_only":pitch}
                for label in ("old","new","midline"):
                    prediction=row[label]
                    positions=prediction.get("center_positions_px",[]) if prediction["status"]=="PASS" else []
                    score=cardinality_gated_yarn_match(positions,b,pitch)
                    oldrow[label]={"score":score,
                      "f1_from_old_unbounded_scorer":row["truth_assessment_only"][label]["f1_proxy"],
                      "status":prediction["status"]}
                subset.append(oldrow)
                records.append(oldrow)
            averages.append({"case":case,"family":family,
                 **{label+"_gated_f1":round(float(np.mean([q[label]["score"]["f1"] for q in subset])),4)
                    for label in ("old","new","midline")},
                 **{label+"_old_report_f1":round(float(np.mean([
                     q[label]["f1_from_old_unbounded_scorer"] for q in subset])),4)
                    for label in ("old","new","midline")}})
    critical=next(q for q in records if q["case"]=="independent_15deg"
                 and q["family"]=="weft" and q["grid"]==[0,2])
    report={"frozen_run_id":39437637934,
      "scorer":"MAXIMUM_WITHIN_GATE_CARDINALITY_THEN_DISTANCE_TIEBREAK",
      "threshold_fraction_pitch":.32,"summary":averages,"critical_window":critical,
      "all_windows":records,
      "limits":["STILL_ONLY_LOCAL_CROSS_SECTION_MATCHING",
                "NO_VISIBILITY_OR_YARN_ID_CONTINUITY_F1",
                "TRUE_SYNTHETIC_GEOMETRY_ONLY_AFTER_FROZEN_INFERENCE",
                "NOT_REAL_R_T_VALIDATION"]}
    (out/"corrected_scores.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    lines=["# 原生8K纱线物理中心：更正一对一F1评估器","",
      "所有推理结果来自已经冻结的真实8K程序运行；未修改检测出的任何中心线。",
      "旧评估器最小化无约束总L1距离后再设置匹配门限，可能令周期性纱线发生整个纱距的假配对。",
      "新评估器先限制每个候选仅可匹配门限内的真实物理纱线，以最大一对一匹配数为优先，再以距离作为微小次级项。",
      "",
      "| 场景 | 经/纬 | 旧检测+旧计分 | 浮点+旧计分 | 浮点+新计分 | 中段+新计分 | 旧检测+新计分 |",
      "|---|---|---:|---:|---:|---:|---:|"]
    for q in averages:
        lines.append(f"| {q['case']} | {q['family']} | "
            f"{q['old_old_report_f1']:.4f} | {q['new_old_report_f1']:.4f} | "
            f"{q['new_gated_f1']:.4f} | {q['midline_gated_f1']:.4f} | "
            f"{q['old_gated_f1']:.4f} |")
    lines.extend(["","## 关键反例（15°旋转，窗口[0,2]，纬纱）","",
      f"- 旧方法最初F1：{critical['old']['f1_from_old_unbounded_scorer']:.4f}；新合理匹配F1：{critical['old']['score']['f1']:.4f}。",
      f"- 浮点方法最初F1：{critical['new']['f1_from_old_unbounded_scorer']:.4f}；新合理匹配F1：{critical['new']['score']['f1']:.4f}。",
      f"- 中段锚定最初F1：{critical['midline']['f1_from_old_unbounded_scorer']:.4f}；新合理匹配F1：{critical['midline']['score']['f1']:.4f}。",
      "","## 验收边界","",
      "本计分修复不等同于识别算法改进。新计分是物理纱线中心在一个截面的有限门内一对一位置匹配，尚未评价遮挡跨越、纱线物理ID连续性。",
      "不能用此前存在错误配对风险的0.32F1结果判定算法优劣。",
      "不将算法或评估器合并到main，需在更全面数据中独立核验。",
      ""])
    (out/"REPORT.md").write_text("\n".join(lines),encoding="utf-8")
    print("CORRECTED_PHYSICAL_YARN_MATCHING "+json.dumps({
       "summary":averages,"critical":critical},ensure_ascii=False),flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--artifacts",required=True,type=Path)
    p.add_argument("--out",required=True,type=Path)
    a=p.parse_args()
    replay(a.artifacts,a.out)
