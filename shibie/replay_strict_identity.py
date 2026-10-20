from __future__ import annotations
"""Re-score frozen individual tracks with strict ID continuity and verify GT."""
import argparse
import json
from pathlib import Path
import numpy as np
from synthetic_capture_8k import CaptureScene,camera_matrices,_truth_lines
from evaluate_yarn_track_identity import projected_truth_curves,evaluate_local_tracks
from evaluate_strict_yarn_identity import strict_trajectory_id_match

SCENES={
"holdout_twill21_wave028":dict(
    name="holdout_twill21_wave028",weave="twill_2_1",
    fabric_rotation_deg=-13,seed=931129,warp_density_cm=30,
    weft_density_cm=25,contrast_polarity="mixed",wave_fraction=.28,
    shift_reflection_x=1.8,noise_sigma=4.),
"holdout_twill31_wave028":dict(
    name="holdout_twill31_wave028",weave="twill_3_1",
    fabric_rotation_deg=18,seed=931130,warp_density_cm=30,
    weft_density_cm=25,contrast_polarity="bright",wave_fraction=.28,
    shift_reflection_x=1.8,noise_sigma=4.),
"medium_twill21_wave014_fresh":dict(
    name="medium_twill21_wave014_fresh",weave="twill_2_1",
    fabric_rotation_deg=-16,seed=938444,warp_density_cm=30,
    weft_density_cm=25,contrast_polarity="mixed",wave_fraction=.14,
    shift_reflection_x=1.8,noise_sigma=4.),
}


def main(artifacts:Path, out:Path):
    paths=sorted(artifacts.rglob("report.json"))
    if len(paths)!=3:raise RuntimeError("THREE_COMPLETE_FROZEN_SOURCES_REQUIRED")
    out.mkdir(parents=True,exist_ok=True)
    records=[];overview=[]
    for path in paths:
        data=json.loads(path.read_text(encoding="utf-8"))
        case=data["case"]
        if case not in SCENES:raise RuntimeError("UNRECOGNIZED_FROZEN_CASE")
        scene=CaptureScene(**SCENES[case])
        H,_=camera_matrices(scene)
        truth={"physical_yarn_centerlines":_truth_lines(scene,H)}
        for row in data["windows"]:
            fam=row["family"]
            pred=row["individual"]
            tracks=pred.get("tracks",[]) if pred["status"]=="PASS" else []
            sample=np.linspace(520/14,520-520/14,7)
            gt=projected_truth_curves(truth,fam,np.asarray(row["H"],np.float64),520,sample)
            pitch=10/(getattr(scene,fam+"_density_cm")*scene.mm_per_px)
            relaxed=evaluate_local_tracks(tracks,gt,fam,pitch)
            recorded=row["truth_identity_assessment_only"]
            if abs(relaxed["f1"]-recorded["f1"])>.00011:
                raise RuntimeError(f"RECONSTRUCTED_GT_MISMATCH: {case} {fam} {row['grid']} {relaxed['f1']} {recorded['f1']}")
            strict=strict_trajectory_id_match(tracks,gt,fam,pitch)
            records.append({"case":case,"family":fam,"grid":row["grid"],
                   "relaxed_id_f1":relaxed["f1"],"strict_id_f1":strict["f1"],
                   "same_id_match_count":strict["matched_physical_ids"],
                   "ground_truth_yarn_count":len(gt),
                   "strict_rejected":strict["single_id_violations_or_incomplete_tracks"],
                   "potential_switch_events":strict["nearest_id_switch_events"]})
        for family in ("warp","weft"):
            subset=[x for x in records if x["case"]==case and x["family"]==family]
            overview.append({"case":case,"family":family,
                 "relaxed_f1":round(float(np.mean([x["relaxed_id_f1"] for x in subset])),4),
                 "strict_f1":round(float(np.mean([x["strict_id_f1"] for x in subset])),4),
                 "strict_rejected_count":sum(x["strict_rejected"] for x in subset),
                 "potential_switch_events":sum(x["potential_switch_events"] for x in subset)})
    lines=["# 修正8K物理纱线身份验收：严格连续性定义","",
      "旧7截线/逐根轨迹F1允许60%采样点对应同一根ID，因此属于宽松代理指标。",
      "严格评分要求至少85%有效截面对应**同一个唯一真值ID**，并否决明确对应另一根纱线的任何一次跳转。",
      "先重建合成物理真值，并逐窗口验证旧指标与冻结评分完全一致，避免真值模型或坐标系被误用。",
      "",
      "| 场景 | 方向 | 原宽松逐根ID-F1 | 严格逐根ID-F1 | 严格拒绝候选数 | 潜在ID切换事件 |",
      "|---|---|---:|---:|---:|---:|"]
    for x in overview:
        lines.append(f"| {x['case']} | {x['family']} | {x['relaxed_f1']:.4f} | "
             f"{x['strict_f1']:.4f} | {x['strict_rejected_count']} | "
             f"{x['potential_switch_events']} |")
    lines+=["","## 结论边界","",
      "严格口径越低，说明先前宽松评分越可能高估了跨截面同根连续性。",
      "本次只重新评估冻结的逐根轨迹；不能直接与先前未按严格口径评分的统一相位版本做相对优劣判断。",
      "物理真值仅由固定实验生成器在**推理后**重建，没有参与候选轨迹生成。",
      "真实R/T工位数据的物理身份与遮挡可见性仍待独立认证。",
      ""]
    (out/"REPORT.md").write_text("\n".join(lines),encoding="utf-8")
    (out/"strict_replay.json").write_text(json.dumps({
       "reconstructed_gt_validated":"ALL_OLD_RELAXED_WINDOW_SCORES_MATCH",
       "overview":overview,"windows":records,"scope":"SYNTHETIC_TILE_ID_ONLY"},
       ensure_ascii=False,indent=2),encoding="utf-8")
    print("STRICT_ID_REPLAY "+json.dumps(overview,ensure_ascii=False),flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--artifacts",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    main(a.artifacts,a.out)
