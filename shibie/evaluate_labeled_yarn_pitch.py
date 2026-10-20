from __future__ import annotations

"""Post-inference yarn-pitch validation using previously confirmed annotations.

No annotations are passed to run_measurement.  Each physical-yarn reference is
a whole yarn trajectory (may cross an occlusion), never a visible segment.
The annotation intervals count whole pitches and may be >1.
"""

import json
import math
import statistics
from pathlib import Path

import cv2
import numpy as np


REPO = Path(__file__).resolve().parents[1]
RESULTS = REPO / "experiments/shibie-acf-holdout-20261020"
LABELS = REPO / "datasets/annotations/drafts"
SOURCES = REPO / "datasets/user_contributed/2026-10-13-six-fabric-images/images"
SAMPLES = ("U20261013_01","U20261013_02","U20261013_03","U20261013_05","U20261013_06")


def theta(seg):
    (x0,y0),(x1,y1) = seg
    return math.degrees(math.atan2(y1-y0,x1-x0))%180.0


def delta(a,b):
    return abs((float(a)-float(b)+90.0)%180.0-90.0)


def marked_pitch(s, first, second, intervals, enlargement):
    a,b=s[first],s[second]
    dx=a[1][0]-a[0][0]
    dy=a[1][1]-a[0][1]
    norm=(-dy/math.hypot(dx,dy),dx/math.hypot(dx,dy))
    m0=((a[0][0]+a[1][0])/2., (a[0][1]+a[1][1])/2.)
    m1=((b[0][0]+b[1][0])/2., (b[0][1]+b[1][1])/2.)
    distance=abs((m1[0]-m0[0])*norm[0]+(m1[1]-m0[1])*norm[1])
    return distance/(float(intervals)*enlargement)


def physical_reference(sample):
    item=json.loads((LABELS/(sample+".json")).read_text(encoding="utf-8"))
    if (not item.get("reference_confirmed") or item.get("annotation_target")!="PHYSICAL_YARN_REFERENCE"
        or not item.get("same_family_intervals_confirmed") or not item.get("cross_family_intervals_confirmed")):
        raise ValueError(f"unconfirmed label: {sample}")
    segs=item["segments"]
    enlargement=float(item["enlargement_scale"])
    if enlargement<=0:
        raise ValueError("invalid enlargement")
    a=marked_pitch(segs,"reference","check_same",item["same_family_intervals"],enlargement)
    b=marked_pitch(segs,"check_cross","check_cross_second",item["cross_family_intervals"],enlargement)
    da=float(np.median([theta(segs[k]) for k in ("reference","check_same","holdout_same") if k in segs]))
    db=float(np.median([theta(segs[k]) for k in ("check_cross","check_cross_second") if k in segs]))
    return (a,b),(da,db)


def source_working_scale(sample,roi_ratio=0.90,max_side=2200):
    img=cv2.imread(str(SOURCES/(sample+".jpg")),cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError("photo unavailable: "+sample)
    h,w=img.shape[:2]
    ch=max(64,int(round(h*roi_ratio)))
    cw=max(64,int(round(w*roi_ratio)))
    return min(1.0,max_side/float(max(ch,cw)))


def main():
    src=RESULTS/"comparison.json"
    if not src.is_file():
        raise FileNotFoundError(src)
    candidates=json.loads(src.read_text(encoding="utf-8"))
    audit=[]
    for sample in SAMPLES:
        true_pitches,true_angles=physical_reference(sample)
        scale=source_working_scale(sample)
        for variant in ("baseline","acf_rescue"):
            item=next((z for z in candidates if z["name"]==sample and z["variant"]==variant),None)
            if item is None:
                raise ValueError("missing measurement: "+sample+"/"+variant)
            measured_angles=(item.get("warp_dir"),item.get("weft_dir"))
            measured_pitch=(item.get("warp_pitch_px"),item.get("weft_pitch_px"))
            record={"sample":sample,"variant":variant,
                "subset":"holdout" if sample in ("U20261013_02","U20261013_06") else "development",
                "source_resize_scale":scale,
                "reference_first_px":true_pitches[0],
                "reference_second_px":true_pitches[1],
                "ref_directions_deg":true_angles,
                "measured_directions_deg":measured_angles,
            }
            if all(v is not None for v in measured_angles+measured_pitch):
                direct=delta(measured_angles[0],true_angles[0])+delta(measured_angles[1],true_angles[1])
                reverse=delta(measured_angles[0],true_angles[1])+delta(measured_angles[1],true_angles[0])
                idx=(0,1) if direct<=reverse else (1,0)
                errors=[]
                for i,j in enumerate(idx):
                    gt=true_pitches[j]
                    pred=float(measured_pitch[i])/scale
                    errors.append(abs(pred-gt)/gt*100.)
                    record[f"measured_{i+1}_px"]=pred
                    record[f"matched_reference_{i+1}_px"]=gt
                    record[f"pitch_error_{i+1}_pct"]=errors[-1]
                record["mean_pitch_error_pct"]=float(np.mean(errors))
                record["mean_angle_error_deg"]=min(direct,reverse)/2
            else:
                record["mean_pitch_error_pct"]=None
                record["mean_angle_error_deg"]=None
            audit.append(record)

    lines=[
        "# 已确认物理纱线标注：推理后纱距几何核验",
        "",
        "标注仅供独立评价，不输入模型，也不是可见中心线的逐像素标注。",
        "同族两根不同物理纱线的法向距离 ÷ 人工确认的间隔数量 ÷ 2x 放大倍数 = 原始输入像素纱距。",
        "预测中心间距从算法 working pixel 按记录的 ROI 缩放系数还原为原图像素后比较。",
        "轴身份由已输出方向与标注方向最小角差配对，**不是改写算法输出**。",
        "本实验只有五张带确认标注的真实布料照片；每张有两组物理纱距参考，不代表完整纱线分割精度。",
        "",
        "| 图片 | 子集 | baseline平均纱距误差 | ACF候选平均纱距误差 | baseline角误差 | ACF角误差 |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for sample in SAMPLES:
        a,b=(next(x for x in audit if x["sample"]==sample and x["variant"]==variant)
            for variant in ("baseline","acf_rescue"))
        fmt=lambda value: "-" if value is None else f"{value:.2f}"
        lines.append(f"| {sample} | {a['subset']} | {fmt(a['mean_pitch_error_pct'])}% | {fmt(b['mean_pitch_error_pct'])}% | {fmt(a['mean_angle_error_deg'])}° | {fmt(b['mean_angle_error_deg'])}° |")
    lines.append("")
    for split in ("development","holdout"):
        lines.append(f"## {split}")
        for variant in ("baseline","acf_rescue"):
            vals=[x["mean_pitch_error_pct"] for x in audit if x["subset"]==split and x["variant"]==variant and x["mean_pitch_error_pct"] is not None]
            lines.append(f"- {variant}: 有效照片数={len(vals)}，平均每照片两轴纱距误差={float(np.mean(vals)):.2f}% " if vals else f"- {variant}: 无有效结果")
    lines.extend(["","此项目标为像素间距诊断；尚无 Camera Profile 和5cm实体框内角的验证，不输出真实根/cm。",
      "任何 U02/U06 留出集显著退化均应拒绝直接提升参数。"])
    (RESULTS/"manual_pitch_audit.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    (RESULTS/"manual_pitch_audit.json").write_text(json.dumps(audit,indent=2,ensure_ascii=False),encoding="utf-8")
    print("\n".join(lines))


if __name__=="__main__":
    main()
