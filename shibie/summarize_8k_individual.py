from __future__ import annotations
"""Aggregate finished individual per-yarn tracker experiment and its failures."""
import argparse
import json
import shutil
from pathlib import Path

SPLITS={
 "holdout_twill21_wave028":"KNOWN_ADVERSARIAL_REGRESSION",
 "holdout_twill31_wave028":"KNOWN_ADVERSARIAL_REGRESSION",
 "medium_twill21_wave014_fresh":"ONE_TIME_FROZEN_HOLDOUT",
}


def main(source:Path,out:Path):
    scenes={};files={}
    for path in source.rglob("report.json"):
        rec=json.loads(path.read_text(encoding="utf-8"))
        case=rec["case"]
        if case in scenes:raise RuntimeError("DUPLICATE_SCENE")
        scenes[case]=rec;files[case]=path
    if set(scenes)!=set(SPLITS):
        raise RuntimeError("INCOMPLETE_SCENE_SET: "+str(set(SPLITS)-set(scenes)))
    out.mkdir(parents=True,exist_ok=True)
    lines=["# 单根独立光学追踪：原生8K程序实测与失败报告","",
     "R/T反射透射同一块独立物理纱线几何渲染；每组8000×6000原生分辨率。",
     "R/T局部单根光学追踪、原浮点固定直线、原7截线共同相位三种算法使用相同输入和物理ID真值。",
     "两种强弯曲纹理已是上一轮失败场景，本轮只能作回归，**不能重新称为独立留出**。",
     "仅新种子的0.14纱距弯曲场景属于一次性冻结留出。",
     "",
     "| 场景 | 方向 | 浮点直线ID-F1 | 共同相位7截线ID-F1 | 新逐根光学ID-F1 | 新版PASS窗 | 新版潜在ID跳变 |",
     "|---|---|---:|---:|---:|---:|---:|"]
    degradation=[];total_runtime=[]
    for case in SPLITS:
        rec=scenes[case]
        pic=files[case].parent/"independent_entity_visual_comparison.jpg"
        if not pic.is_file():raise RuntimeError("SOURCE_IMAGE_MISSING_"+case)
        shutil.copy2(pic,out/(case+"_independent_algorithm_overlay.jpg"))
        total_runtime.append((case,rec["algorithm_only_runtime_seconds"],
                                  rec["process_peak_rss_mib"]))
        for family in ("warp","weft"):
            m=rec["summary"][family]
            new=m["independent_per_yarn"]
            base=m["frozen_common_phase_seven"]
            lines.append(f"| {case} | {family} | "
              f"{m['frozen_float']['mean_id_trajectory_f1']:.4f} | "
              f"{base['mean_id_trajectory_f1']:.4f} | "
              f"{new['mean_id_trajectory_f1']:.4f} | "
              f"{new['passing_windows']}/9 | {new['potential_gt_id_switches']} |")
            if new["mean_id_trajectory_f1"]<base["mean_id_trajectory_f1"]-.01:
                degradation.append({"case":case,"family":family,
                    "old":base["mean_id_trajectory_f1"],"new":new["mean_id_trajectory_f1"]})
    lines.extend(["","## 分场景失败与边界","",
       "新方法低于原7截线版本超过0.01的条件："])
    for q in degradation:lines.append(f"- {q['case']} {q['family']}: {q['old']:.4f} → {q['new']:.4f}")
    if not degradation:lines.append("- 本轮没有F1退化超过0.01的方向族。")
    lines+=["","独立追踪的局部像素光学证据与人工设定的真值参数完全隔离；所有GT在推理结束后读取。",
      "这些局部ID仍不等于原生50mm全幅长纱线轨迹，尚未评价真实交织遮挡的可见片段连续性。",
      "单根R/T独立核验只有合成数据，没有真实8K R/T人工物理身份真值；因此不能把结果作为实际可部署精度保证。",
      "",
      "计算性能为ubuntu GitHub Runner运行所测，未验证RK3576和4GB共享前端场景。",
      ""]
    (out/"REPORT.md").write_text("\n".join(lines),encoding="utf-8")
    (out/"summary.json").write_text(json.dumps({
       "split":SPLITS,"runs":{k:{x:y for x,y in v.items() if x!="windows"} for k,v in scenes.items()},
       "degradation":degradation,"runtime_memory":total_runtime,
       "limitations":["SYNTHETIC_ONLY","REGRESSION_SCENES_NOT_NEW_HOLDOUT",
                      "NOT_PHYSICAL_ID_COVERAGE_BENEATH_OCCLUSION"]},
       ensure_ascii=False,indent=2),encoding="utf-8")
    print("INDIVIDUAL_ENTITY_HOLDOUT "+json.dumps({"degradation":degradation,
           "scenes":list(scenes)},ensure_ascii=False),flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--artifacts",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args();main(a.artifacts,a.out)
