from __future__ import annotations

"""Frozen-baseline vs ACF rescue: replay on physically distinct fabric images.

Single-image files are duplicated ONLY for a diagnostic to satisfy the old
two-input API. They cannot validate cross-modal registration/physical densities.
Never train or select on the holdout U02/U06.
"""
import csv
import dataclasses
import json
import math
import sys
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from engine.config import EngineConfig
from engine import pipeline
from engine.width import map_centerlines_to_reflection

OUT = ROOT / "experiments" / "shibie-acf-holdout-20261020"
DENIM = ROOT / "datasets/user_contributed/2026-10-13-six-fabric-images/images"
ANN = ROOT / "datasets/annotations/drafts"
FABRIC = HERE / "tmp/user_samples"

REAL_NAMES = tuple(f"U20261013_{k:02d}" for k in range(1, 7))
FABRIC_NAMES = ("W012", "W032", "W088", "W114")
CASES = REAL_NAMES + FABRIC_NAMES

CANDIDATE = {
    "density_min_per_cm": 10.0,
    "steerable_quality_close_margin": 0.22,
    "steerable_periodicity_tiebreak_floor": 0.08,
}
VARIANTS = {"baseline": {}, "acf_rescue": CANDIDATE}


def circular_delta(a, b):
    return abs((float(a)-float(b)+90.0)%180.0-90.0)


def operator_axes(name):
    path = ANN / (name + ".json")
    if not path.is_file():
        return None
    d = json.loads(path.read_text(encoding="utf-8"))
    if d.get("annotation_target") != "PHYSICAL_YARN_REFERENCE" or not d.get("reference_confirmed"):
        return None
    s = d["segments"]
    def ang(p):
        return float(math.degrees(math.atan2(p[1][1]-p[0][1],p[1][0]-p[0][0]))%180.0)
    g1 = sorted(ang(s[k]) for k in ("reference","check_same","holdout_same") if k in s)
    g2 = sorted(ang(s[k]) for k in ("check_cross","check_cross_second") if k in s)
    if not g1 or not g2:
        return None
    return (float(np.median(g1)),float(np.median(g2)))


def dir_error(orientation, axes):
    if not axes or not orientation:
        return None
    a,b=orientation.get("direction_a_deg"),orientation.get("direction_b_deg")
    if a is None or b is None:
        return None
    direct=(circular_delta(a,axes[0])+circular_delta(b,axes[1]))/2
    swapped=(circular_delta(a,axes[1])+circular_delta(b,axes[0]))/2
    return round(min(direct,swapped),3)


def case_path(name):
    return (DENIM if name.startswith("U") else FABRIC) / (name + ".jpg")


def run_one(name,variant,params):
    path=case_path(name)
    raw=path.read_bytes()
    frame=cv2.imdecode(np.frombuffer(raw,np.uint8),cv2.IMREAD_COLOR)
    if frame is None:
        raise RuntimeError("INVALID_INPUT:"+name)
    cfg=dataclasses.replace(EngineConfig(),**params)
    pipeline.DEFAULT_CONFIG=cfg
    selected_runs={}
    orig=pipeline._run_direction
    def record(img,angle,mmx,mmy):
        value=orig(img,angle,mmx,mmy)
        selected_runs[round(float(angle)%180,4)]=value
        return value
    pipeline._run_direction=record
    try:
        r=pipeline.run_measurement(raw,raw,
            mm_per_px_x=0.0125,mm_per_px_y=0.0125,
            warp_axis_hint="vertical")
    finally:
        pipeline._run_direction=orig
        pipeline.DEFAULT_CONFIG=EngineConfig()
    orient=r.get("orientation") or {}
    density=r.get("density_debug") or {}
    norm=r.get("normalization") or {}
    image=frame.copy()
    found={}
    if norm:
        for key,color in (("warp",(0,15,255)),("weft",(255,250,0))):
            angle=orient.get(f"{key}_direction_deg")
            info=selected_runs.get(round(float(angle)%180.0,4)) if angle is not None else None
            lines=map_centerlines_to_reflection(info["_width_seed"],norm,
                np.array([[1.,0.,0.],[0.,1.,0.]],np.float32)) if info else []
            found[key]=len(lines)
            for pts in lines:
                if len(pts)>1:
                    cv2.polylines(image,[np.rint(pts).astype(np.int32)],False,color,2,cv2.LINE_AA)

    h,w=image.shape[:2]
    side=int(min(h,w)*0.65)
    x=(w-side)//2;y=(h-side)//2
    tile=image[y:y+side,x:x+side]
    thumb=cv2.resize(tile,(640,640),interpolation=cv2.INTER_AREA)
    (OUT/"review").mkdir(parents=True,exist_ok=True)
    cv2.imwrite(str(OUT/"review"/f"{name}_{variant}.jpg"),thumb,[cv2.IMWRITE_JPEG_QUALITY,95])
    a1=operator_axes(name)
    def dbg(key,subkey):
        return ((density.get(key) or {}).get(subkey) or {})
    return {
      "name":name,"variant":variant,
      "split":"holdout" if name in ("U20261013_02","U20261013_06") else "development_diagnostic",
      "input_mode":"DUPLICATED_SINGLE_IMAGE_NOT_RT",
      "status":r.get("status"),"gate3":(r.get("gate3") or {}).get("status"),
      "warp_dir":orient.get("warp_direction_deg"),"weft_dir":orient.get("weft_direction_deg"),
      "operator_axis_error_deg_evaluation_only":dir_error(orient,a1),
      "warp_count":found.get("warp"),"weft_count":found.get("weft"),
      "warp_pitch_px":dbg("warp","centerline").get("median_center_spacing_px"),
      "weft_pitch_px":dbg("weft","centerline").get("median_center_spacing_px"),
      "warp_acf_px":dbg("warp","periodicity").get("spacing_px"),
      "weft_acf_px":dbg("weft","periodicity").get("spacing_px"),
      "warp_conf":dbg("warp","confidence").get("status"),
      "weft_conf":dbg("weft","confidence").get("status"),
      "warp_reasons":"|".join(dbg("warp","confidence").get("reasons") or []),
      "weft_reasons":"|".join(dbg("weft","confidence").get("reasons") or []),
    }


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    rows=[]
    for name in CASES:
        for variant,params in VARIANTS.items():
            record=run_one(name,variant,params)
            rows.append(record)
            print(json.dumps(record,ensure_ascii=False),flush=True)
    with (OUT/"comparison.csv").open("w",newline="",encoding="utf-8-sig") as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]))
        writer.writeheader();writer.writerows(rows)
    (OUT/"comparison.json").write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding="utf-8")
    lines=[
        "# ACF 强约束修复候选：跨布料回归检查",
        "",
        "本轮 10 张单图原始样本各运行两版，共 20 次识别（包括开发样本、独立留出 U02/U06）。",
        "均复制同一单图满足历史 R/T API：只能诊断方向、候选计数和结构稳定性，不可称双模态或绝对密度精度。",
        "人为纱线角仅用于事后比较，从未传入推理。",
        f"候选更改：`{CANDIDATE}`。",
        "",
        "| 图 | baseline warp/weft 条数 | 候选 warp/weft 条数 | baseline 角差 | 候选角差 |",
        "|---|---:|---:|---:|---:|",
    ]
    for name in CASES:
        b,c=(next(r for r in rows if r["name"]==name and r["variant"]==tag) for tag in ("baseline","acf_rescue"))
        lines.append(f"| {name} | {b['warp_count']}/{b['weft_count']} | {c['warp_count']}/{c['weft_count']} | {b['operator_axis_error_deg_evaluation_only']} | {c['operator_axis_error_deg_evaluation_only']} |")
    lines.extend(["",
      "数目增加不等于正确率提高，必须逐张查看 review/ 下真实照片覆盖线。",
      "图像为 65% 中心局部，直接来自原始输入的二维裁剪与缩放展示；缩略图不是推理输入。",
      "未经真实标尺、独立真实根数及真实 R/T Golden Dataset 证据，不允许自动将候选参数提升为正式参数。",
    ])
    (OUT/"report.md").write_text("\n".join(lines)+"\n",encoding="utf-8")


if __name__ == "__main__":
    main()
