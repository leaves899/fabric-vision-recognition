from __future__ import annotations

"""Frozen synthetic R/T benchmark for shibie, with real 1-to-1 centerline scoring.

All physical labels are held by evaluator; the engine gets R and T image bytes
and simulator mm/px only. This score says nothing about real-photograph accuracy.
"""

import csv
import dataclasses
import json
import math
import sys
from pathlib import Path

import cv2
import numpy as np
from scipy.optimize import linear_sum_assignment

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
sys.path.insert(0,str(HERE))
from engine import pipeline
from engine.config import EngineConfig
from engine.width import map_centerlines_to_reflection
from synthetic_physical_fabric import SCENES,synthesize

OUT=ROOT/"experiments/shibie-synthetic-physics-20261020"

# Predictable, frozen POC variants; physical labels cannot influence parameters.
VARIANTS={
 "v063_default": {},
 "acf_candidate": {
     "density_min_per_cm": 10.0,
     "steerable_quality_close_margin": 0.22,
     "steerable_periodicity_tiebreak_floor": 0.08,
 },
}


def angle_error(a,b):
    return abs((float(a)-float(b)+90)%180-90)


def center_coordinates(lines, normal_deg, size):
    # Position at central transverse axis: small yarn waviness is averaged out.
    normal=np.asarray([math.cos(math.radians(normal_deg+90)),
                       math.sin(math.radians(normal_deg+90))],np.float64)
    center=np.asarray([size/2,size/2],np.float64)
    result=[]
    for line in lines:
        pts=np.asarray(line,dtype=np.float64)
        if len(pts)<2:
            continue
        central=(pts[:,0]>.12*size)&(pts[:,0]<.88*size)&(pts[:,1]>.12*size)&(pts[:,1]<.88*size)
        samples=pts[central] if np.any(central) else pts
        if len(samples)<2:continue
        dist=np.median((samples-center[None,:])@normal)
        if abs(dist)<=size*.30:result.append(float(dist))
    return result


def count_accuracy(pred_lines, reference_curves, expected_deg, estimated_deg, pitch, size):
    theta_error=angle_error(estimated_deg,expected_deg) if estimated_deg is not None else 90.
    ref_coords=center_coordinates([item["points"] for item in reference_curves],expected_deg,size)
    pred_coords=center_coordinates(pred_lines,expected_deg,size)
    if theta_error>10 or not pred_coords or not ref_coords:
        return {
          "predicted":len(pred_coords),"truth":len(ref_coords),
          "matched":0,"precision":0.,"recall":0.,"f1":0.,"direction_error_deg":round(theta_error,3),
          "match_tolerance_px":round(.32*pitch,3),
        }
    dist=np.abs(np.asarray(pred_coords)[:,None]-np.asarray(ref_coords)[None,:])
    r,c=linear_sum_assignment(dist)
    matched=sum(float(dist[i,j])<=pitch*.32 for i,j in zip(r,c))
    nearest=np.min(dist,axis=1)
    nearest_fraction=float(np.median(nearest)/pitch)
    closest=np.argmin(dist,axis=1)
    signed_offsets=np.asarray(pred_coords)-np.asarray(ref_coords)[closest]
    precision=matched/max(len(pred_coords),1)
    recall=matched/max(len(ref_coords),1)
    f1=2*precision*recall/max(precision+recall,1e-9)
    return {
      "predicted":len(pred_coords),"truth":len(ref_coords),"matched":matched,
      "precision":round(precision,4),"recall":round(recall,4),"f1":round(f1,4),
      "direction_error_deg":round(theta_error,3),"match_tolerance_px":round(.32*pitch,3),
      "median_nearest_gt_px":round(float(np.median(nearest)),3),
      "median_offset_fraction_of_pitch":round(nearest_fraction,3),
      "signed_phase_offset_px":round(float(np.median(signed_offsets)),3),
    }


def encode(image):
    ok,data=cv2.imencode(".png",image)
    if not ok:raise RuntimeError("ENCODE_FAIL")
    return data.tobytes()


def evaluate(scene,name,overrides,reflected,transmitted,gt):
    config=dataclasses.replace(EngineConfig(),**overrides)
    pipeline.DEFAULT_CONFIG=config
    cache={}
    orig=pipeline._run_direction
    def cache_run(image,angle,scale_x,scale_y):
        result=orig(image,angle,scale_x,scale_y)
        cache[round(float(angle)%180,4)]=result
        return result
    pipeline._run_direction=cache_run
    try:
        m=pipeline.run_measurement(
            encode(reflected),encode(transmitted),
            mm_per_px_x=scene.mm_per_px,mm_per_px_y=scene.mm_per_px,
            sample_id=scene.name
        )
    finally:
        pipeline._run_direction=orig
        pipeline.DEFAULT_CONFIG=EngineConfig()
    orientation=m.get("orientation") or {}
    norm=m.get("normalization") or {}
    geometry=np.asarray([[1.,0.,0.],[0.,1.,0.]],np.float32)
    overlay=transmitted.copy()
    result={"case":scene.name,"variant":name,"weave_truth":scene.weave,
      "engine_status":m.get("status"),"gate3":(m.get("gate3") or {}).get("status"),
      "warp_pitch_gt":scene.warp_pitch_px,"weft_pitch_gt":scene.weft_pitch_px,
      "mm_per_px_simulated":scene.mm_per_px,
      "weave_candidate":(m.get("twill") or {}).get("weave_candidate"),
      "weave_status":(m.get("twill") or {}).get("weave_status")}
    allscores=[]
    for family,color in (("warp",(0,0,255)),("weft",(255,230,0))):
        deg=orientation.get(family+"_direction_deg")
        run=cache.get(round(float(deg)%180,4)) if deg is not None else None
        lines=map_centerlines_to_reflection(run["_width_seed"],norm,geometry) if run is not None else []
        for coords in lines:
            if len(coords)>1:cv2.polylines(overlay,[np.rint(coords).astype(np.int32)],False,color,2,cv2.LINE_AA)
        score=count_accuracy(lines,gt["physical_yarn_centerlines"][family],
          gt["true_direction_deg"][family],deg,
          scene.warp_pitch_px if family=="warp" else scene.weft_pitch_px,scene.size)
        allscores.append(score)
        result[family+"_f1"]=score["f1"]
        result[family+"_recall"]=score["recall"]
        result[family+"_precision"]=score["precision"]
        result[family+"_matched"]=score["matched"]
        result[family+"_predicted"]=score["predicted"]
        result[family+"_truth"]=score["truth"]
        result[family+"_direction_error_deg"]=score["direction_error_deg"]
        result[family+"_nearest_truth_offset_fraction"]=score.get("median_offset_fraction_of_pitch")
        result[family+"_nearest_truth_offset_px"]=score.get("median_nearest_gt_px")
        result[family+"_phase_signed_px"]=score.get("signed_phase_offset_px")
        observed=((m.get("density_debug") or {}).get(family) or {}).get("centerline") or {}
        result[family+"_pitch_measured_working_px"]=observed.get("median_center_spacing_px")
    result["mean_f1"]=round(float(np.mean([q["f1"] for q in allscores])),4)
    outdir=OUT/"visuals"
    outdir.mkdir(parents=True,exist_ok=True)
    cv2.imwrite(str(outdir/f"{scene.name}_{name}.jpg"),overlay,[cv2.IMWRITE_JPEG_QUALITY,93])
    # Ground-truth physical centers in a separate layer (independent from output).
    physical=transmitted.copy()
    for family,color in (("warp",(255,50,210)),("weft",(65,255,65))):
        for entity in gt["physical_yarn_centerlines"][family]:
            coords=np.rint(np.asarray(entity["points"],np.float32)).astype(np.int32)
            if len(coords)>1:cv2.polylines(physical,[coords],False,color,1,cv2.LINE_AA)
    cv2.imwrite(str(outdir/f"{scene.name}_GT_physical_yarns.jpg"),physical,[cv2.IMWRITE_JPEG_QUALITY,95])
    return result


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/"visuals").mkdir(exist_ok=True)
    results=[]
    for scene in SCENES:
        R,T,truth=synthesize(scene)
        cv2.imwrite(str(OUT/"visuals"/f"{scene.name}_reflection.jpg"),R,[cv2.IMWRITE_JPEG_QUALITY,92])
        cv2.imwrite(str(OUT/"visuals"/f"{scene.name}_transmission.jpg"),T,[cv2.IMWRITE_JPEG_QUALITY,92])
        (OUT/"visuals"/f"{scene.name}_truth.json").write_text(json.dumps(truth,indent=2,ensure_ascii=False),encoding="utf-8")
        for variant,config in VARIANTS.items():
            row=evaluate(scene,variant,config,R,T,truth)
            print(json.dumps(row,ensure_ascii=False),flush=True)
            results.append(row)
    with (OUT/"synthetic_metrics.csv").open("w",encoding="utf-8-sig",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(results[0]))
        writer.writeheader();writer.writerows(results)
    (OUT/"synthetic_metrics.json").write_text(json.dumps(results,indent=2,ensure_ascii=False),encoding="utf-8")
    lines=["# 合成物理机织布：真实纱线一对一合成标注与shibie回归","","",
      "输入为程序化合成、同场景双光照图片。标签只由评估器读取：算法仅收到R/T像素和模拟的mm/px。",
      "每根纱线中心线有持久的物理ID，过交织遮挡仍连续；可测单根线精确率、召回率、F1。",
      "匹配规则：沿实物纱线法向投影、一对一匈牙利匹配、容差为模拟纱距32%，且角度误差不超过10°。",
      "测试仅模拟简化的圆柱/扁平纱截面、拍摄模糊、光照、噪声、颜色斜纹干扰，不能表明真实布料精度。",
      "分数会受中心ROI筛选影响，与完整画面验收指标不是同一个量。","","| 场景 | 组织真值 | baseline Warp/Weft F1 | ACF Warp/Weft F1 | baseline 角误差 Warp/Weft | ACF 角误差 Warp/Weft |","|---|---|---|---|---|---|"]
    for scene in SCENES:
        b,a=(next(x for x in results if x["case"]==scene.name and x["variant"]==v) for v in VARIANTS)
        lines.append(f"| {scene.name} | {scene.weave} | {b['warp_f1']:.3f}/{b['weft_f1']:.3f} | {a['warp_f1']:.3f}/{a['weft_f1']:.3f} | {b['warp_direction_error_deg']:.2f}/{b['weft_direction_error_deg']:.2f}° | {a['warp_direction_error_deg']:.2f}/{a['weft_direction_error_deg']:.2f}° |")
    for v in VARIANTS:
        subset=[r for r in results if r["variant"]==v]
        avg=np.mean([r["mean_f1"] for r in subset])
        lines.append(f"\n- {v}：六类合成场景平均两组中心线 F1 = {avg:.4f} (仅合成分布)。")
    lines.append("\n**推广要求**：任何合成场景得分改善，都必须另用已标注真实手机照片和未参与调参的真实 R/T 双图确认。")
    (OUT/"report.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    # Easy-to-review, 3-row / 3-column contact sheet
    tile=350
    sheet=np.full((len(SCENES)*tile,3*tile,3),243,np.uint8)
    for ri,scene in enumerate(SCENES):
        for ci,suffix in enumerate(("transmission","v063_default","acf_candidate")):
            fname=f"{scene.name}_{suffix}.jpg"
            image=cv2.imread(str(OUT/"visuals"/fname))
            if image is None:continue
            img=cv2.resize(image,(tile,tile),interpolation=cv2.INTER_AREA)
            sheet[ri*tile:(ri+1)*tile,ci*tile:(ci+1)*tile]=img
            cv2.rectangle(sheet,(ci*tile,ri*tile),(ci*tile+349,ri*tile+24),(248,248,248),-1)
            cv2.putText(sheet,scene.name+" "+suffix,(ci*tile+3,ri*tile+17),
                cv2.FONT_HERSHEY_SIMPLEX,.45,(20,20,20),1,cv2.LINE_AA)
    cv2.imwrite(str(OUT/"review_sheet.jpg"),sheet,[cv2.IMWRITE_JPEG_QUALITY,90])


if __name__=="__main__":
    main()
