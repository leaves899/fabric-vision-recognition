#!/usr/bin/env python3
"""FabricNET same-horizontal ablation (five controls, 130 real photos each).

Experimental factors (frozen Shibie V0.6.3 _run_direction, no edits):
  F0 DIRECT_FIXED:        original 90deg warp + original 0deg weft.
  F1 ROT90_FIXED:         original 0deg weft + 90CW 0deg warp.
  E0 DIRECT_ESTIMATED:    original vertical-ish warp + original horizontal-ish weft,
                          each chosen by nearest-axis tensor candidate, no pair ranking.
  E1 ROT90_ESTIMATED:     original horizontal-ish weft + 90CW horizontal-ish warp,
                          each independently estimated, no pair ranking.
  F2 ROT270_FIXED:       180deg original horizontal weft + 270CW original horizontal warp.
Do not substitute measured warp/weft names based on orientation results.
Excel labels are only read/attached AFTER inference.
This is NOT genuine R/T, and not a physical yarn-ID accuracy test.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import time
import traceback
from pathlib import Path

import cv2
import numpy as np
from engine import pipeline
from engine.config import DEFAULT_CONFIG
from engine.gate2 import gate2
from engine.normalization import normalize_transmission
from engine.orientation import structure_tensor_directions, angular_distance
from engine.width import map_centerlines_to_reflection
from validate_fabricnet_latest_20261021 import fetch_dataset, parse_ground_truth

ARMS = ("DIRECT_FIXED","ROT90_FIXED","DIRECT_ESTIMATED",
        "ROT90_ESTIMATED","ROT270_FIXED")
FIELDS = (
 "image","sha256","arm","input_mode","truth_texture","gate2","status",
 "warp_status","weft_status","warp_error_reason","weft_error_reason",
 "warp_angle_used","weft_angle_used","warp_angle_from_input",
 "weft_angle_from_input","warp_density","weft_density",
 "warp_pitch","weft_pitch","warp_lines","weft_lines",
 "warp_count_density","weft_count_density","warp_spacing_density",
 "weft_spacing_density","warp_path_diff_pct","weft_path_diff_pct",
 "warp_spacing_cv","weft_spacing_cv","truth_warp","truth_weft",
 "warp_signed_error","weft_signed_error","warp_abs_error","weft_abs_error",
 "warp_abs_pct","weft_abs_pct","both10","duration_s"
)
def rotate(frame,deg):
    return frame if deg==0 else cv2.rotate(frame,{
       90:cv2.ROTATE_90_CLOCKWISE,
       180:cv2.ROTATE_180,
       270:cv2.ROTATE_90_COUNTERCLOCKWISE}[deg])
def source_poly(pts, deg, oh, ow):
    arr=np.asarray(pts,dtype=np.float32)
    if arr.ndim!=2 or arr.shape[1]!=2 or len(arr)<2:return None
    x,y=arr[:,0],arr[:,1]
    if deg==0: return arr
    if deg==90: return np.column_stack([y,oh-1-x]).astype(np.float32)
    if deg==180: return np.column_stack([ow-1-x,oh-1-y]).astype(np.float32)
    if deg==270: return np.column_stack([ow-1-y,x]).astype(np.float32)
    raise ValueError(deg)

def single_axis(turned, scale_x, scale_y, target_angle, estimated):
    norm,meta=normalize_transmission(turned,DEFAULT_CONFIG)
    angle=float(target_angle)
    if estimated:
        orientation=structure_tensor_directions(norm,DEFAULT_CONFIG)
        candidates=orientation.get("direction_candidates") or []
        # Do not use truth, density or any downstream candidate performance to pick angle.
        if not candidates:raise RuntimeError("TENSOR_NO_DIRECTION_CANDIDATES")
        angle=min((float(x["angle_deg"]) for x in candidates),
                  key=lambda v: angular_distance(v,float(target_angle)))
    run=pipeline._run_direction(norm,angle,
                  float(scale_x)/float(meta["resize_scale"]),
                  float(scale_y)/float(meta["resize_scale"]))
    lines=map_centerlines_to_reflection(run["_width_seed"],meta,
                                        np.eye(2,3,dtype=np.float32))
    return run,lines,angle

def process_one(photo_path,arm,output):
    tic=time.monotonic()
    src=photo_path.read_bytes()
    frame=cv2.imdecode(np.frombuffer(src,np.uint8),cv2.IMREAD_COLOR)
    if frame is None or frame.shape[:2]!=(480,640):
        raise RuntimeError("EXPECTED_640_X_480_MICROSCOPE_PHOTO")
    hh,ww=frame.shape[:2]
    xscale,yscale=5.0/640.0,4.0/480.0
    g2=gate2(frame,frame,xscale,yscale,DEFAULT_CONFIG)
    estimated=arm in ("DIRECT_ESTIMATED","ROT90_ESTIMATED")
    # For DIRECT the two source directions are different; for ROTATED BOTH
    # are actually measured by the identical 0-degree horizontal branch.
    degrees={"DIRECT_FIXED":{"warp":0,"weft":0},
             "DIRECT_ESTIMATED":{"warp":0,"weft":0},
             "ROT90_FIXED":{"warp":90,"weft":0},
             "ROT90_ESTIMATED":{"warp":90,"weft":0},
             "ROT270_FIXED":{"warp":270,"weft":180}}[arm]
    row={"image":photo_path.name,"sha256":hashlib.sha256(src).hexdigest(),
         "arm":arm,"gate2":g2["status"],
         "input_mode":"SINGLE_FABRICNET_MICROSCOPE_PHOTO_NOT_GENUINE_RT"}
    tracks={}
    for fam in ("weft","warp"):
        deg=degrees[fam]
        turned=rotate(frame,deg)
        is_vertical=(fam=="warp" and arm in ("DIRECT_FIXED","DIRECT_ESTIMATED"))
        goal=90.0 if is_vertical else 0.0
        mmx,mmy=(yscale,xscale) if deg in (90,270) else (xscale,yscale)
        try:
            run,source_lines,angle=single_axis(turned,mmx,mmy,goal,estimated)
            tracks[fam]=[source_poly(p,deg,hh,ww) for p in source_lines]
            tracks[fam]=[v for v in tracks[fam] if v is not None]
            row[fam+"_angle_used"]=round(angle,4)
            row[fam+"_angle_from_input"]=round((angle-deg)%180,4)
            row[fam+"_status"]=run["confidence"]["status"]
            row[fam+"_error_reason"]="|".join(run["confidence"].get("reasons") or [])
            row[fam+"_density"]=round(float(run["density"]["density_per_cm"]),5)
            row[fam+"_pitch"]=round(float(run["centerline"]["median_center_spacing_px"]),5)
            row[fam+"_count_density"]=run["density"].get("count_density_per_cm")
            row[fam+"_spacing_density"]=run["density"].get("spacing_density_per_cm")
            row[fam+"_path_diff_pct"]=round(float(run["density"]["path_diff_pct"]),4)
            row[fam+"_spacing_cv"]=round(float(run["centerline"]["spacing_cv"]),4)
        except Exception as ex:
            tracks[fam]=[]
            row[fam+"_status"]="FAIL"
            row[fam+"_error_reason"]=str(ex)
            row[fam+"_density"]=None
            print("AXIS_FAIL",photo_path.name,arm,fam,str(ex),flush=True)
        row[fam+"_lines"]=len(tracks[fam])

    states=(g2["status"],row["warp_status"],row["weft_status"])
    row["status"]="FAIL" if "FAIL" in states else ("PASS" if all(x=="PASS" for x in states) else "LOW_CONFIDENCE")
    canvas=frame.copy()
    for fam,color in (("warp",(0,0,255)),("weft",(255,255,0))):
        for poly in tracks[fam]:
            cv2.polylines(canvas,[np.rint(poly).astype(np.int32)],False,color,1,cv2.LINE_AA)
    cv2.rectangle(canvas,(0,0),(ww-1,26),(20,20,20),-1)
    cv2.putText(canvas,f"{photo_path.stem} {arm} RED=warp CYAN=weft",
                (4,18),cv2.FONT_HERSHEY_SIMPLEX,.42,(255,255,255),1,cv2.LINE_AA)
    dest=output/"overlays"/photo_path.name
    dest.parent.mkdir(exist_ok=True,parents=True)
    if not cv2.imwrite(str(dest),canvas,[cv2.IMWRITE_JPEG_QUALITY,94]):
        raise RuntimeError("OVERLAY_WRITE_FAILED")
    row["duration_s"]=round(time.monotonic()-tic,4)
    return row

def attach_truth(row,groundtruth):
    truth=groundtruth.get(row["image"]) or {}
    row["truth_texture"]=truth.get("texture")
    for fam in ("warp","weft"):
        predicted=row.get(fam+"_density")
        true=truth.get(fam)
        row["truth_"+fam]=true
        if predicted is None or true is None:
            row[fam+"_signed_error"]=None;row[fam+"_abs_error"]=None;row[fam+"_abs_pct"]=None
        else:
            d=float(predicted)-float(true)
            row[fam+"_signed_error"]=round(d,5)
            row[fam+"_abs_error"]=round(abs(d),5)
            row[fam+"_abs_pct"]=round(100*abs(d)/float(true),5)
    x,y=row.get("warp_abs_pct"),row.get("weft_abs_pct")
    row["both10"]=int(x<=10 and y<=10) if x is not None and y is not None else None
    return row

def avg(vals):
    x=[float(v) for v in vals if v is not None]
    return round(float(np.mean(x)),5) if x else None

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--arm",required=True,choices=ARMS)
    ap.add_argument("--out",required=True,type=Path)
    ap.add_argument("--dataset",type=Path,default=Path("/tmp/fabricnet_ablation_20261021"))
    args=ap.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    images=fetch_dataset(args.dataset)
    gts,schema=parse_ground_truth(args.dataset/"FabricNet_parameters.xlsx")
    if len(images)!=130 or len(gts)!=130:raise RuntimeError("130_TRUTH_OR_IMAGE_MISMATCH")
    records=[]
    for n,image in enumerate(images,1):
        try:
            record=process_one(image,args.arm,args.out)
        except Exception as ex:
            print("IMAGE_FAIL",image.name,args.arm,repr(ex),flush=True)
            traceback.print_exc()
            record={key:None for key in FIELDS}
            record.update(image=image.name,sha256=hashlib.sha256(image.read_bytes()).hexdigest(),
                          arm=args.arm,status="FAIL",warp_status="FAIL",weft_status="FAIL",
                          warp_error_reason=str(ex),weft_error_reason=str(ex))
        records.append(attach_truth(record,gts))
        print(f"[{n}/130] {image.name} {args.arm} status={record['status']} "
              f"warp={record.get('warp_density')} weft={record.get('weft_density')}",flush=True)
    with (args.out/"metrics.csv").open("w",encoding="utf-8-sig",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=FIELDS,extrasaction="ignore")
        writer.writeheader();writer.writerows(records)
    valid=[r for r in records if r["warp_abs_error"] is not None and r["weft_abs_error"] is not None]
    stats={"arm":args.arm,"n":len(records),"n_valid_two_densities":len(valid),
           "warp_mae":avg([r["warp_abs_error"] for r in valid]),
           "weft_mae":avg([r["weft_abs_error"] for r in valid]),
           "warp_mape":avg([r["warp_abs_pct"] for r in valid]),
           "weft_mape":avg([r["weft_abs_pct"] for r in valid]),
           "both10":sum(r.get("both10")==1 for r in records),
           "pass_and_both10":sum(r["status"]=="PASS" and r.get("both10")==1 for r in records),
           "status":{s:sum(r["status"]==s for r in records) for s in ("PASS","LOW_CONFIDENCE","FAIL")},
           "truth_schema":schema,
           "cautions":["No genuine R/T or 8K calibration fixture",
             "Only the historical _run_direction is reused, no edits",
             "Estimated orientations use nearest-axis tensor candidates independently",
             "FabricNET cannot establish per physical yarn-ID accuracy",
             "Original fixed angle follows image axes, not independently labeled orientations",
             "No label information enters detector or candidate selection"]}
    (args.out/"summary.json").write_text(json.dumps(stats,indent=2,ensure_ascii=False),encoding="utf-8")
    print("ABLATION_RESULT "+json.dumps({k:v for k,v in stats.items() if k!="truth_schema"},ensure_ascii=False),flush=True)
if __name__=="__main__":
    main()
