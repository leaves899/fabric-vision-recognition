"""Frozen synthetic physical-yarn experiment for phase-pitch guards.

Only uses synthetic scene metadata in the scorer after shibie inference. The
baseline and original (unguarded) dark-phase run are frozen in previous report.
"""
from __future__ import annotations
import csv
import json
from pathlib import Path
import numpy as np

import evaluate_synthetic_physical as ev
from synthetic_physical_fabric import SCENES, HOLDOUT_SCENES, synthesize

ROOT=Path(__file__).resolve().parent.parent
ev.OUT=ROOT/"experiments/shibie-phase-guard-20261020"
CANDIDATES={
 "guarded_dark": {
   "transmission_yarn_contrast_mode":"dark",
   "transmission_center_evidence_weight":.45,
   "transmission_phase_pitch_guard_ratio":.15,
 },
 "guarded_bright": {
   "transmission_yarn_contrast_mode":"bright",
   "transmission_center_evidence_weight":.45,
   "transmission_phase_pitch_guard_ratio":.15,
 },
}
BASE=ROOT/"experiments/shibie-synthetic-physics-20261020/synthetic_metrics.json"

def main():
    ev.OUT.mkdir(parents=True,exist_ok=True)
    originals=json.loads(BASE.read_text(encoding="utf-8"))
    trials=[]
    for scene in SCENES+HOLDOUT_SCENES:
        R,T,labels=synthesize(scene)
        for variant,params in CANDIDATES.items():
            rec=ev.evaluate(scene,variant,params,R,T,labels)
            trials.append(rec)
            print(json.dumps(rec,ensure_ascii=False),flush=True)
    with (ev.OUT/"results.csv").open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=list(trials[0]))
        w.writeheader();w.writerows(trials)
    (ev.OUT/"results.json").write_text(json.dumps(trials,indent=2,ensure_ascii=False),encoding="utf-8")
    lines=["# 已知真实纱线身份的合成数据：光学相位纱距保护",
       "","六张开发诊断图片+三张预先冻结的合成留出图片。真值从不输入推理。",
       "光学相位仅在与原版无相位筛选结果纱距差异≤15%的候选间产生排序贡献。",
       "真实图像未预先确定亮暗极性；不能把合成暗纱线作为自动规则。","",
       "| 场景 | 数据划分 | baseline F1 (两方向均值) | 旧dark F1 | guarded-dark F1 | guarded-bright F1 |",
       "|---|---|---:|---:|---:|---:|"]
    def base_record(case,variant):
        return next(x for x in originals if x["case"]==case and x["variant"]==variant)
    def guarded_record(case,variant):
        return next(x for x in trials if x["case"]==case and x["variant"]==variant)
    for scene in SCENES+HOLDOUT_SCENES:
        values=[base_record(scene.name,"v063_default")["mean_f1"],
                base_record(scene.name,"calibrated_dark_phase")["mean_f1"],
                guarded_record(scene.name,"guarded_dark")["mean_f1"],
                guarded_record(scene.name,"guarded_bright")["mean_f1"]]
        lines.append(f"| {scene.name} | {'holdout' if scene in HOLDOUT_SCENES else 'development'} | "+" | ".join(f"{x:.4f}" for x in values)+" |")
    lines.append("")
    for label,scenes in (("development",SCENES),("holdout",HOLDOUT_SCENES)):
        for var in CANDIDATES:
            v=np.mean([guarded_record(s.name,var)["mean_f1"] for s in scenes])
            lines.append(f"- {label}/{var}：平均中心线F1={v:.4f}")
    lines.extend(["","注意：一对一匹配仅按投影线位置，不保证跨遮挡完整轨迹。此分数仅对特定程序化生成分布有效。"])
    (ev.OUT/"report.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    # Contact sheet is measured/ground-truth overlays, never AI-generated imagery.
    import cv2
    tile=310
    sheet=np.full((len(SCENES+HOLDOUT_SCENES)*tile,3*tile,3),243,np.uint8)
    for ri,scene in enumerate(SCENES+HOLDOUT_SCENES):
        for ci,suff in enumerate(("GT_physical_yarns","guarded_dark","guarded_bright")):
            img=cv2.imread(str(ev.OUT/"visuals"/f"{scene.name}_{suff}.jpg"))
            if img is None:raise FileNotFoundError(f"{scene.name}_{suff}.jpg")
            img=cv2.resize(img,(tile,tile),interpolation=cv2.INTER_AREA)
            sheet[ri*tile:(ri+1)*tile,ci*tile:(ci+1)*tile]=img
            cv2.rectangle(sheet,(ci*tile,ri*tile),(ci*tile+tile-1,ri*tile+22),(240,240,240),-1)
            cv2.putText(sheet,f"{scene.name} {suff}",(ci*tile+4,ri*tile+16),
                cv2.FONT_HERSHEY_SIMPLEX,.37,(30,30,30),1,cv2.LINE_AA)
    cv2.imwrite(str(ev.OUT/"review_sheet.jpg"),sheet,[cv2.IMWRITE_JPEG_QUALITY,92])

if __name__=="__main__":
    main()
