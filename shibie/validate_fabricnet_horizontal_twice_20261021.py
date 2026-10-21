#!/usr/bin/env python3
"""Two calls to the SAME horizontal-only Shibie V0.6.3 module.

Original image horizontal -> physical weft; 90CW image horizontal ->
physical warp. GT enters only after inference. FabricNET is single-image
microscopy, NOT real reflected/transmitted 8K paired capture.
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
from engine.width import map_centerlines_to_reflection
from validate_fabricnet_latest_20261021 import fetch_dataset, parse_ground_truth

FIELDS = [
    "image","source_sha256","status","gate2","truth_texture",
    "warp_horizontal_rot90_status","weft_horizontal_original_status",
    "warp_reasons","weft_reasons","warp_density_per_cm","weft_density_per_cm",
    "warp_centerline_count","weft_centerline_count",
    "warp_pitch_px","weft_pitch_px","warp_count_density","weft_count_density",
    "warp_spacing_density","weft_spacing_density",
    "truth_warp","truth_weft","warp_abs_error","weft_abs_error",
    "warp_rel_error_pct","weft_rel_error_pct","both_within_10pct",
    "elapsed_seconds","input_mode"
]
def horizontal_only(frame, mm_x, mm_y):
    """Single fixed physical direction, NOT a dual-axis pair inference."""
    gray, meta=normalize_transmission(frame,DEFAULT_CONFIG)
    scale=float(meta["resize_scale"])
    run=pipeline._run_direction(gray,0.0,mm_x/scale,mm_y/scale)
    paths=map_centerlines_to_reflection(
        run["_width_seed"],meta,np.eye(2,3,dtype=np.float32))
    return run,paths

def recover_warp_lines(rotated_lines, h_original):
    # Inverse of exact 90deg clockwise: (x,y)original=(y_rot,Horig-1-x_rot).
    ret=[]
    for line in rotated_lines:
        arr=np.asarray(line,dtype=np.float32)
        if arr.ndim!=2 or arr.shape[1]!=2:continue
        ret.append(np.column_stack((arr[:,1],h_original-1-arr[:,0])).astype(np.float32))
    return ret

def paint(frame, warp_paths, weft_paths, name, status):
    image=frame.copy()
    counts={}
    for fam,lines,color in [("warp",warp_paths,(0,0,255)),("weft",weft_paths,(255,240,0))]:
        n=0
        for line in lines:
            pts=np.asarray(line,np.float32)
            if pts.ndim==2 and pts.shape[1]==2 and pts.shape[0]>=2:
                cv2.polylines(image,[np.rint(pts).astype(np.int32)],False,color,1,cv2.LINE_AA)
                n+=1
        counts[fam]=n
    cv2.rectangle(image,(0,0),(image.shape[1]-1,27),(22,22,22),-1)
    cv2.putText(image,f"{name}: H-horizontal-twice {status} red=warp cyan=weft",
                (4,18),cv2.FONT_HERSHEY_SIMPLEX,.42,(255,255,255),1,cv2.LINE_AA)
    return image,counts

def estimate(path, folder):
    start=time.monotonic()
    raw=path.read_bytes()
    frame=cv2.imdecode(np.frombuffer(raw,np.uint8),cv2.IMREAD_COLOR)
    if frame is None or frame.shape[:2]!=(480,640):
        raise ValueError("IMAGE_SHAPE_OR_DECODE_INVALID")
    turned=cv2.rotate(frame,cv2.ROTATE_90_CLOCKWISE)
    mx,my=5.0/640.0,4.0/480.0
    g2=gate2(frame,frame,mx,my,DEFAULT_CONFIG)
    detail={}
    for fam,photo,xs,ys in [
        ("weft",frame,mx,my),
        ("warp",turned,my,mx),
    ]:
        try:
            run,lines=horizontal_only(photo,xs,ys)
            detail[fam]={"run":run,"paths":lines,"status":run["confidence"]["status"],
                         "reasons":"|".join(run["confidence"].get("reasons",[]))}
        except Exception as e:
            print("DIRECTION_EXCEPTION",path.name,fam,type(e).__name__,str(e),flush=True)
            detail[fam]={"run":None,"paths":[],"status":"FAIL","reasons":str(e)}
    states=[g2["status"]]+[detail[x]["status"] for x in ("warp","weft")]
    status="FAIL" if "FAIL" in states else ("PASS" if states==["PASS","PASS","PASS"] else "LOW_CONFIDENCE")
    lines_warp=recover_warp_lines(detail["warp"]["paths"],frame.shape[0])
    overlay,count=paint(frame,lines_warp,detail["weft"]["paths"],path.stem,status)
    save=folder/"overlays_original"/path.name
    save.parent.mkdir(parents=True,exist_ok=True)
    if not cv2.imwrite(str(save),overlay,[cv2.IMWRITE_JPEG_QUALITY,94]):
        raise RuntimeError("OVERLAY_SAVE_FAILED")
    row={
        "image":path.name,"source_sha256":hashlib.sha256(raw).hexdigest(),
        "status":status,"gate2":g2["status"],
        "warp_horizontal_rot90_status":detail["warp"]["status"],
        "weft_horizontal_original_status":detail["weft"]["status"],
        "warp_reasons":detail["warp"]["reasons"],
        "weft_reasons":detail["weft"]["reasons"],
        "warp_centerline_count":count["warp"],"weft_centerline_count":count["weft"],
        "elapsed_seconds":round(time.monotonic()-start,3),
        "input_mode":"SINGLE_MICROSCOPE_IMAGE_NO_GENUINE_RT"
    }
    for fam in ("warp","weft"):
        run=detail[fam]["run"]
        for key,group,field in [
            ("density_per_cm","density","density_per_cm"),
            ("pitch_px","centerline","median_center_spacing_px"),
            ("count_density","density","density_count_path"),
            ("spacing_density","density","density_spacing_path"),
        ]:
            row[fam+"_"+key]=round(float(run[group][field]),5) if run is not None else None
    return row

def truth_after_inference(row, references):
    gt=references.get(row["image"],{})
    row["truth_texture"]=gt.get("texture")
    for fam in ("warp","weft"):
        pred=row.get(fam+"_density_per_cm");ref=gt.get(fam)
        row["truth_"+fam]=ref
        row[fam+"_abs_error"]=round(abs(pred-ref),5) if pred is not None and ref is not None else None
        row[fam+"_rel_error_pct"]=round(100*abs(pred-ref)/ref,5) if pred is not None and ref else None
    a,b=row["warp_rel_error_pct"],row["weft_rel_error_pct"]
    row["both_within_10pct"]=int(a<=10 and b<=10) if a is not None and b is not None else None
    return row

def avg(vals):
    v=[x for x in vals if x is not None]
    return round(float(np.mean(v)),5) if v else None

def summary(rows, original):
    scored=[r for r in rows if r["warp_abs_error"] is not None and r["weft_abs_error"] is not None]
    base={r["image"]:r for r in original}
    pair=[]
    for row in rows:
        b=base[row["image"]]
        if row["source_sha256"]!=b["source_sha256"]:raise RuntimeError("SAME_IMAGE_HASH_MISMATCH")
        entry={"image":row["image"],"weave":row["truth_texture"],
               "h2_status":row["status"],"original_status":b["status"],
               "h2_both10":row["both_within_10pct"],"original_both10":int(b["both_within_10pct"])}
        for fam in ("warp","weft"):
            current=row[fam+"_rel_error_pct"];prior=float(b[fam+"_rel_error_pct"])
            entry[fam+"_h2_density"]=row[fam+"_density_per_cm"]
            entry[fam+"_original_density"]=float(b[fam+"_density_per_cm"])
            entry[fam+"_h2_error_pct"]=current
            entry[fam+"_original_error_pct"]=prior
            entry[fam+"_improvement_points"]=round(prior-current,5) if current is not None else None
        pair.append(entry)
    old_vals={fam:avg([float(b[fam+"_abs_error"]) for b in original]) for fam in ("warp","weft")}
    data={"images":130,"both_predicted":len(scored),
          "status_hist":{x:sum(r["status"]==x for r in rows) for x in ("PASS","LOW_CONFIDENCE","FAIL")},
          "individual_horizontal_status":{
              fam:{x:sum(r[fam+("_horizontal_rot90_status" if fam=="warp" else "_horizontal_original_status")]==x for r in rows)
                   for x in ("PASS","LOW_CONFIDENCE","FAIL")} for fam in ("warp","weft")},
          "h2":{"warp_mae":avg([r["warp_abs_error"] for r in scored]),
                "weft_mae":avg([r["weft_abs_error"] for r in scored]),
                "warp_mape":avg([r["warp_rel_error_pct"] for r in scored]),
                "weft_mape":avg([r["weft_rel_error_pct"] for r in scored]),
                "both10":sum(r["both_within_10pct"]==1 for r in rows),
                "both10_and_pass":sum(r["both_within_10pct"]==1 and r["status"]=="PASS" for r in rows)},
          "old":{"warp_mae":old_vals["warp"],"weft_mae":old_vals["weft"],
                 "both10":sum(b["both_within_10pct"]=="1" for b in original),
                 "old_pass":sum(b["status"]=="PASS" for b in original)},
          "by_weave":{}, "limitations":[
              "Fixed image horizontal angle 0 deg, not a generalized rotated-weave orientation estimator",
              "The original _run_direction uses rotate_keep_size, truncating rectangular ROI under 90deg internal image transform",
              "Both PASS statuses are independent one-direction evidence; not directly comparable to original full pipeline overall PASS",
              "One microscope image rotated, not genuine reflected/transmitted 8K dual capture",
              "Per physical yarn centerline GT absent: no pixel-F1 or physical identity precision",
              "Ground truth was never used inside measurement, candidate or angle selection"
          ]}
    for fam in ("warp","weft"):
        data["h2"][fam+"_scoreable_count"]=sum(r[fam+"_density_per_cm"] is not None for r in rows)
    data["delta"]={"both10":data["h2"]["both10"]-data["old"]["both10"],
                   "warp_mae":round(data["h2"]["warp_mae"]-old_vals["warp"],5) if data["h2"]["warp_mae"] is not None else None,
                   "weft_mae":round(data["h2"]["weft_mae"]-old_vals["weft"],5) if data["h2"]["weft_mae"] is not None else None,
                   "new_pass_old_fail":sum(x["h2_both10"]==1 and x["original_both10"]==0 for x in pair),
                   "new_fail_old_pass":sum(x["h2_both10"]!=1 and x["original_both10"]==1 for x in pair),
                   "weft_better_n":sum(x["weft_improvement_points"] is not None and x["weft_improvement_points"]>0 for x in pair),
                   "warp_better_n":sum(x["warp_improvement_points"] is not None and x["warp_improvement_points"]>0 for x in pair)}
    for weave in ("plain","twill","satin"):
        z=[r for r in scored if r["truth_texture"]==weave]
        data["by_weave"][weave]={"n":len(z),
              "warp_mae":avg([r["warp_abs_error"] for r in z]),
              "weft_mae":avg([r["weft_abs_error"] for r in z]),
              "both10":sum(r["both_within_10pct"]==1 for r in z)}
    return data,pair

def save_contact(out, names, filename):
    tiles=[]
    for name in names:
        img=cv2.imread(str(out/"overlays_original"/name))
        if img is None:raise RuntimeError("OVERLAY_NOT_CREATED:"+name)
        tiles.append(img)
    while len(tiles)%2:tiles.append(np.full_like(tiles[0],240))
    strip=np.concatenate([np.concatenate(tiles[i:i+2],axis=1) for i in range(0,len(tiles),2)],axis=0)
    cv2.imwrite(str(out/filename),strip,[cv2.IMWRITE_JPEG_QUALITY,87])

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--out",required=True,type=Path)
    ap.add_argument("--dataset",type=Path,default=Path("/tmp/fabricnet_horizontal_twice"))
    ap.add_argument("--baseline",required=True,type=Path)
    args=ap.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    photos=fetch_dataset(args.dataset)
    gts,schema=parse_ground_truth(args.dataset/"FabricNet_parameters.xlsx")
    with args.baseline.open(encoding="utf-8-sig",newline="") as f:
        baseline=list(csv.DictReader(f))
    if len(photos)!=130 or len(gts)!=130 or len(baseline)!=130:
        raise RuntimeError("REQUIRED_130_IMAGE_INPUT_NOT_COMPLETE")
    rows=[]
    for index,path in enumerate(photos,1):
        try:
            row=estimate(path,args.out)
        except Exception as e:
            traceback.print_exc()
            row={k:None for k in FIELDS}
            row.update(image=path.name,source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                       status="FAIL",warp_reasons=str(e),weft_reasons=str(e))
        row=truth_after_inference(row,gts)
        rows.append(row)
        print(f"[{index}/130] {path.name} weft_H0={row.get('weft_density_per_cm')} "
              f"warp_H90={row.get('warp_density_per_cm')} status={row['status']}",flush=True)
    with (args.out/"horizontal_twice_metrics.csv").open("w",encoding="utf-8-sig",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=FIELDS,extrasaction="ignore")
        writer.writeheader();writer.writerows(rows)
    stats,joined=summary(rows,baseline)
    stats["truth_schema"]=schema
    (args.out/"horizontal_twice_summary.json").write_text(
       json.dumps(stats,ensure_ascii=False,indent=2),encoding="utf-8")
    with (args.out/"horizontal_twice_vs_original.csv").open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(joined[0]))
        w.writeheader();w.writerows(joined)
    priority=["W120.jpg","W115.jpg","W119.jpg","W035.jpg","W067.jpg","W095.jpg",
              "W105.jpg","W112.jpg","W032.jpg","W037.jpg"]
    save_contact(args.out,priority,"priority10_horizontal_twice.jpg")
    worst=sorted(joined,key=lambda x:max(x["warp_original_error_pct"],x["weft_original_error_pct"]),reverse=True)
    save_contact(args.out,[x["image"] for x in worst[:20]],"original_worst20_horizontal_twice.jpg")
    a,b=stats["old"],stats["h2"]
    md=[
      "# FabricNET horizontal-only twice: 0 deg horizontal, then rotated 90 deg horizontal",
      "",
      "This calls the SAME single-direction V0.6.3 Steerable/Ridge/Density detector twice. "
      "The original photo's horizontal evidence is physical WEFT; 90CW rotated horizontal evidence is physical WARP. "
      "No GT labels enter inference; the image is only rotated by exact cv2.rotate. "
      "Physical x/y mm/px calibration values are swapped in the second pass.",
      "",
      "| Metric | Frozen original dual-axis | HORIZONTAL-TWICE |",
      "|---|---:|---:|",
      f"| Warp MAE yarns/cm | {a['warp_mae']} | {b['warp_mae']} |",
      f"| Weft MAE yarns/cm | {a['weft_mae']} | {b['weft_mae']} |",
      f"| Both relative errors <=10% | {a['both10']}/130 | {b['both10']}/130 |",
      f"| Both directions returned density | 130/130 | {stats['both_predicted']}/130 |",
      f"| PASS (not same quality gate) | {a['old_pass']}/130 | {stats['status_hist']['PASS']}/130 |",
      "",
      "The angle is fixed at 0deg for BOTH detections; these microscope pictures are broadly aligned. "
      "This initial test isolates the identical horizontal detector rather than GT-guided orientation search. "
      "Do NOT treat detection on an artificially 90deg-rotated single image as genuine R/T dual capture.",
      "",
      "## By image label (not supplied to algorithm)",
      "| Label | Number | Warp MAE | Weft MAE | Both<=10% |",
      "|---|---:|---:|---:|---:|"
    ]
    for weave in ("plain","twill","satin"):
        x=stats["by_weave"][weave]
        md.append(f"| {weave} | {x['n']} | {x['warp_mae']} | {x['weft_mae']} | {x['both10']} |")
    md.extend([
       "","## Actual detector images",
       "- Overlays_original: every W001-W130 centerline trace drawn on original pixels; red=original warp, cyan=original weft.",
       "- priority10_horizontal_twice.jpg: 10 representative difficult cases.",
       "- original_worst20_horizontal_twice.jpg: 20 worst under the frozen original.",
       "- horizontal_twice_metrics.csv: all raw results including FAIL and LOW_CONFIDENCE.",
       "- horizontal_twice_vs_original.csv: per-image baseline comparison.",
       "",
       "Caution: no ground-truth centerline identities; picture-level density agreement cannot prove physically valid centers. "
       "Legacy keep-size internal 90deg transform may crop rectangular ROI and should be reviewed if this method fails.",
    ])
    (args.out/"REPORT.md").write_text("\n".join(md)+"\n",encoding="utf8")
    print("HORIZONTAL_TWICE_SUMMARY "+json.dumps({k:v for k,v in stats.items() if k!="truth_schema"},ensure_ascii=False),flush=True)
if __name__=="__main__":
    main()
