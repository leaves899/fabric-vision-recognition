from __future__ import annotations
"""Collect actual 8k trajectory experiments, no recomputed or invented scores."""
import argparse
import json
import shutil
from pathlib import Path

FROZEN={
    "rotation15_development":"DEVELOPMENT",
    "zero_development":"DEVELOPMENT",
    "twill21_angleholdout":"INDEPENDENT_HOLDOUT",
    "bright_angleholdout":"INDEPENDENT_HOLDOUT",
}


def summarize(artifacts:Path, out:Path):
    files=sorted(artifacts.rglob("report.json"))
    found={}
    source_by_case={}
    for f in files:
        row=json.loads(f.read_text(encoding="utf-8"))
        case=row["case"]
        if case in found:raise RuntimeError("DUPLICATE_SCENE_"+case)
        found[case]=row
        source_by_case[case]=f
    if set(found)!=set(FROZEN):
        raise RuntimeError("MISSING_CASES: "+repr(set(FROZEN)-set(found)))
    out.mkdir(parents=True,exist_ok=True)
    lines=["# 原生8K R/T多截线物理纱线身份研究：程序实测",
           "",
           "四组各为直接8000×6000物理坐标合成，不是缩小图片放大；其中2组固定开发，2组固定留出。",
           "所有变换、纹理方向、纱距、相位和7截线候选均在读取任何真值前确定。",
           "每根候选轨迹只有持续接近**同一个物理纱线ID**才可在后验轨迹评分中算匹配。",
           "但仍是高分辨率局部520px窗口，不等于全标定框跨窗口身份关联；也没有真实可见/遮挡逐像素GT。",
           "",
           "| 划分 | 场景 | 方向 | 原整数直线身份F1 | 浮点直线身份F1 | 7截线曲线身份F1 | 7截线有效窗/9 | 潜在跨ID切换(直/曲) |",
           "|---|---|---|---:|---:|---:|---:|---:|"]
    declines=[]
    for case,split in FROZEN.items():
        row=found[case]
        source=source_by_case[case]
        im=source.parent/"true_id_trajectory_comparison.jpg"
        if not im.exists():raise RuntimeError("MISSING_ALGORITHM_OVERLAY_"+case)
        shutil.copy2(im,out/(case+"_real_tracking_overlay.jpg"))
        for fam in ("warp","weft"):
            metrics=row["summary"][fam]
            base=metrics["float"]["mean_id_trajectory_f1"]
            new=metrics["seven"]["mean_id_trajectory_f1"]
            lines.append(f"| {split} | {case} | {fam} | "
              f"{metrics['old']['mean_id_trajectory_f1']:.4f} | "
              f"{base:.4f} | {new:.4f} | "
              f"{metrics['seven']['passing_windows']}/9 | "
              f"{metrics['float']['potential_gt_id_switches']}/"
              f"{metrics['seven']['potential_gt_id_switches']} |")
            if new<base-.01:
                declines.append({"case":case,"family":fam,
                    "float_f1":base,"seven_f1":new,
                    "delta":round(new-base,4)})
    lines.extend(["","## 负面结果（不忽略）","",
      "比较每个场景的7截线曲线与原浮点直线。观察到的退化如下：",""])
    if declines:
        for d in declines:
            lines.append(f"- {d['case']} / {d['family']}："
              f"{d['float_f1']:.4f} → {d['seven_f1']:.4f} (Δ{d['delta']:+.4f})")
    else:
        lines.append("- 在本次测试的场景平均值上没有超过0.01的F1退化。")
    lines.extend(["","## 诚实的边界","",
      "- 轨迹评分要求一个候选在多截面保持同一物理纱线ID，不再把每个截面的最近纱线独立认作同根。",
      "- 这些是合成样本评估；测试集结果不能用于回传选择参数，留出集仅用于一次性验收。",
      "- 没有在真实标定8K R/T照片上得到物理ID真值；不做真实精度承诺。",
      "- 若新算法损害任一留出类别的关键指标，不进入默认pipeline、也不合并main。",
      "- 捕获分辨率、运行时间和RSS仅反映云端 runner，不代表RK3576。",
      ""])
    (out/"REPORT.md").write_text("\n".join(lines),encoding="utf-8")
    (out/"summary.json").write_text(json.dumps({
         "splits":FROZEN,
         "cases":{k:{x:y for x,y in v.items() if x!="windows"} for k,v in found.items()},
         "declines":declines,
         "full_window_details_only_in_actions_artifacts":True,
         "scoring_limit":"SAMPLED_LOCAL_ID_NOT_FULL_IMAGE_OR_OCCLUSION_VISIBILITY"
       },ensure_ascii=False,indent=2),encoding="utf-8")
    print("EVALUATED_NATIVE8K_IDENTITY "+json.dumps({
         "cases":list(found),"declines":declines},ensure_ascii=False),flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--artifacts",required=True,type=Path)
    parser.add_argument("--out",required=True,type=Path)
    a=parser.parse_args()
    summarize(a.artifacts,a.out)
