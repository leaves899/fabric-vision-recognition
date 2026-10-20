from __future__ import annotations
"""Offline A/B/C conflict audit using finished GitHub Action artifacts."""
import argparse
import json
import shutil
from pathlib import Path
from engine.phase_conflict_audit import audit_center_hypotheses


def run(artifacts: Path, output: Path):
    output.mkdir(parents=True,exist_ok=True)
    source=sorted(artifacts.rglob("comparison.json"))
    if len(source)!=3:
        raise RuntimeError("EXPECTED_THREE_NATIVE8K_SCENE_REPORTS")
    records=[]
    for file in source:
        data=json.loads(file.read_text(encoding="utf-8"))
        sample=data["case"]
        overlay=file.parent/"real_algorithm_visual_comparison.jpg"
        if not overlay.is_file():
            raise RuntimeError("MISSING_PROGRAM_RENDERED_OVERLAY: "+sample)
        shutil.copy2(overlay,output/(sample+"_three_algorithms.jpg"))
        # Inference reports were frozen before 'truth_assessment_only' existed.
        # The decision function sees ONLY old/new inference, never assessment.
        for row in data["windows"]:
            decision=audit_center_hypotheses(row["old"],row["new"])
            old=row["truth_assessment_only"]["old"]["f1_proxy"]
            new=row["truth_assessment_only"]["new"]["f1_proxy"]
            mid=row["truth_assessment_only"]["midline"]["f1_proxy"]
            records.append({"scene":sample,"grid":row["grid"],"family":row["family"],
              "decision":decision,"old_f1":old,"float_f1":new,"midline_f1":mid,
              "float_drop_gt_0_1_EVALUATION_ONLY": bool(old-new>.1),
              "midline_drop_gt_0_1_EVALUATION_ONLY": bool(old-mid>.1)})
    n_harm=sum(x["float_drop_gt_0_1_EVALUATION_ONLY"] for x in records)
    n_flag=sum(x["decision"]["status"]=="LOW_CONFIDENCE" for x in records)
    caught=sum(x["float_drop_gt_0_1_EVALUATION_ONLY"] and
               x["decision"]["status"]=="LOW_CONFIDENCE" for x in records)
    false_flag=sum(not x["float_drop_gt_0_1_EVALUATION_ONLY"] and
                   x["decision"]["status"]=="LOW_CONFIDENCE" for x in records)
    flagged=[x for x in records if x["decision"]["status"]=="LOW_CONFIDENCE" or
                              x["float_drop_gt_0_1_EVALUATION_ONLY"]]
    summary={"n_windows":len(records),"harmful_windows":n_harm,
       "uncertainty_flagged_windows":n_flag,"harmful_caught":caught,
       "nonharmful_flagged":false_flag,
       "limitations":["F1_IS_MID_CROSS_SECTION_PROXY_NOT_IDENTITY",
         "THREE_SYNTHETIC_SCENES_ONLY","NO_INFERENCE_FROM_GT","NOT_REAL_R_T_CERTIFIED"],
       "cases":{case:next((r for r in records if r["scene"]==case),None)
                for case in sorted({x["scene"] for x in records})},
       "review_windows":flagged}
    (output/"phase_conflict_audit.json").write_text(
        json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    markdown=[
       "# 8K物理中心候选冲突审计（第三轮）","",
       "将旧整数周期、浮点周期和中心截面重新锚定三条路径放在相同像素/真实标签上评分。",
       "冲突审计只读取推理产生的候选，不读取任何真值；下列危害窗口标签仅用于事后复核。",
       "",
       f"- 总窗口（包含经纬两族）：**{len(records)}**。",
       f"- 浮点版相比整数版F1下降超过0.10的窗口：**{n_harm}**。",
       f"- 物理宽度缩放冲突审计发出低置信警报：**{n_flag}**。",
       f"- 其中命中明显F1下降窗口：**{caught}/{n_harm}**。",
       f"- 对未出现明显下降的窗口发出警报：**{false_flag}**。",
       "",
       "**注意**：检测到不一致并不说明旧版或新版哪个是正确纱线。不能靠此审计自动纠正物理身份。",
       "",
       "| 场景 | 经/纬 | 窗格 | 旧F1 | 浮点F1 | 中段F1 | 冲突状态 | q90位移(px)/允许(px) |",
       "|---|---|---|---:|---:|---:|---|---|"
    ]
    for r in flagged:
        d=r["decision"]
        markdown.append(f"| {r['scene']} | {r['family']} | {r['grid']} | "
            f"{r['old_f1']:.4f} | {r['float_f1']:.4f} | {r['midline_f1']:.4f} | "
            f"{d['status']} | {d.get('nearest_displacement_q90_px','—')} / "
            f"{d.get('allowed_displacement_px','—')} |")
    markdown += ["","## 裁决",
       "未通过真正双模态8K实拍数据前，正式pipeline保持冻结。若冲突审计漏报明显退化，记录失败、不得把其结果作为安全性保证。",
       "所有图片均直接复制于GitHub Actions实际推理产生的覆盖图，不使用图像生成。"]
    (output/"REPORT.md").write_text("\n".join(markdown),encoding="utf-8")
    print("PHYSICAL_CENTRE_CONFLICT_AUDIT "+json.dumps({
         "total":len(records),"harm":n_harm,"flags":n_flag,"caught":caught,
         "nonharmful_flags":false_flag,"critical":flagged[:8]
    },ensure_ascii=False),flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--artifacts",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    args=p.parse_args()
    run(args.artifacts,args.out)
