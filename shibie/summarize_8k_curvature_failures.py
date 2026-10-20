from __future__ import annotations
"""Archive (do not alter) two already completed high-curvature native8k runs."""
import argparse
import json
import shutil
from pathlib import Path


def main(input_dir:Path,out:Path):
    rows={}
    paths={}
    for path in input_dir.rglob("report.json"):
        data=json.loads(path.read_text(encoding="utf-8"))
        case=data["case"]
        if case in rows:raise RuntimeError("DUPLICATE_CASE")
        rows[case]=data;paths[case]=path
    wanted={"holdout_twill21_wave028","holdout_twill31_wave028"}
    if set(rows)!=wanted:raise RuntimeError("INCOMPLETE_NATIVE8K_HOLDOUT: "+repr(set(rows)))
    out.mkdir(parents=True,exist_ok=True)
    lines=["# 原生8K高曲率独立留出：真实程序实测失败记录","",
      "固定同一个识别算法与身份评估器，不针对这两个新种子调整阈值。",
      "两组为程序化织物，包含0.28倍纱距的中心弯曲幅度、R/T轻微错位、斜纹交织及独立旋转。",
      "全部以8000×6000原生像素构造，并在520px局部窗口评估多截线同物理ID关联。",
      "",
      "| 场景 | 方向 | 直线浮点F1 | 7截线F1 | 7截线PASS/9 | 潜在跨真值ID切换（直线/7截线） |",
      "|---|---|---:|---:|---:|---:|"]
    negatives=[]
    for case in sorted(rows):
        d=rows[case]
        image=paths[case].parent/"true_id_trajectory_comparison.jpg"
        if not image.is_file():raise RuntimeError("OVERLAY_MISSING: "+case)
        shutil.copy2(image,out/(case+"_physical_identity_overlay.jpg"))
        for fam in ("warp","weft"):
            stats=d["summary"][fam]
            fl=stats["float"];se=stats["seven"]
            lines.append(f"| {case} | {fam} | {fl['mean_id_trajectory_f1']:.4f} | "
              f"{se['mean_id_trajectory_f1']:.4f} | {se['passing_windows']}/9 | "
              f"{fl['potential_gt_id_switches']}/{se['potential_gt_id_switches']} |")
            if se["mean_id_trajectory_f1"]<.90:
                negatives.append({"case":case,"family":fam,"reason":"ID_F1_BELOW_TARGET",
                  "f1":se["mean_id_trajectory_f1"],
                  "possible_identity_switches":se["potential_gt_id_switches"]})
    lines+=["","## 失败归因审查","",
       "- 现有模型对两组高曲率样本全部未通过0.90目标，**不能**声称多截线算法已可适应强弯曲。",
       "- 统一相位逐截面调整假定同族相邻纱线共享局部位移；真实独立实体可能具有不同弯曲，相位模型不足。",
       "- 所报告的最近物理ID跳变需结合真实轨迹进一步核验，不能直接解释为已追踪到错误纱线的数量。",
       "- 已冻结完整9窗口结果与真实程序绘制的真值/直线/曲线重叠图；留出失败不能用作继续调参后重新宣称独立留出。",
       "- 局部同ID F1不是交织遮挡的可见轨迹覆盖F1，仍无真实手机8K R/T工位黄金标注。",
       "",
       "## 工程结论","",
       "只将此次压力测试和未通过的证据保存在独立分支，不修改main、不部署。下一阶段应研究每根物理纱线分别以局部像素实体证据追踪，不能把整组纱线共同平移当作多根独立物理纱线。"]
    (out/"REPORT.md").write_text("\n".join(lines),encoding="utf-8")
    (out/"metrics.json").write_text(json.dumps({
       "source_workflow_run":39444581720,"scenarios":{
         k:{p:v for p,v in d.items() if p!="windows"} for k,d in rows.items()},
       "failed_conditions":negatives,
       "scope":"NATIVE8K_SYNTHETIC_LOCAL_IDENTITY_ONLY"},ensure_ascii=False,indent=2),encoding="utf-8")
    print("HIGH_CURVATURE_HOLDOUT "+json.dumps(negatives,ensure_ascii=False),flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--artifacts",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    main(a.artifacts,a.out)
