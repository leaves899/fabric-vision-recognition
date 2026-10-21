#!/usr/bin/env python3
"""Blind FabricNET 130-image replay of the checked-out Shibie engine.

Important: only single microscope images exist. We duplicate *identical bytes*
solely to satisfy the frozen two-input API. This is NOT R/T validation. Images
and all truth fields are loaded independently; labels never enter inference.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import os
import re
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "shibie"))
from engine import pipeline
from engine.width import map_centerlines_to_reflection

DATASET_BASE = "https://huggingface.co/datasets/acseckin/FabricNET/resolve/main/"
ID_PATTERN = re.compile(r"\bW?0*(\d{1,3})\b", re.I)
FIELDS = [
    "image","source_sha256","status","failure_reasons","warp_density_per_cm",
    "weft_density_per_cm","warp_direction_deg","weft_direction_deg","warp_lines",
    "weft_lines","gate3","width_status","truth_warp","truth_weft",
    "truth_texture","warp_abs_error","weft_abs_error","warp_rel_error_pct",
    "weft_rel_error_pct","both_within_10pct","runtime_s","input_mode",
]

def download_file(dest: Path, name: str):
    if dest.is_file() and dest.stat().st_size > 1024:
        return
    url = DATASET_BASE + name + "?download=true"
    last_error = None
    for attempt in range(4):
        try:
            r = requests.get(url, timeout=(20, 90), headers={"User-Agent":"FabricNET-blind-validation/1.0"})
            r.raise_for_status()
            if len(r.content) < 1024:
                raise RuntimeError("response too short")
            dest.write_bytes(r.content)
            return
        except Exception as e:
            last_error = e
            time.sleep(2.0 * (attempt + 1))
    raise RuntimeError(f"{name}: {last_error}")

def fetch_dataset(dataset: Path):
    dataset.mkdir(parents=True, exist_ok=True)
    files = [f"W{i:03d}.jpg" for i in range(1,131)] + ["FabricNet_parameters.xlsx"]
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(download_file, dataset / n, n):n for n in files}
        for future in as_completed(futures):
            future.result()
    image_files = sorted(dataset.glob("W*.jpg"))
    if len(image_files) != 130:
        raise RuntimeError(f"Expected 130 files; got {len(image_files)}")
    for image_file in image_files:
        if cv2.imread(str(image_file), cv2.IMREAD_COLOR) is None:
            raise RuntimeError("Not a decodable JPEG: "+str(image_file))
    return image_files

def select_column(columns, include, exclude=()):
    for col in columns:
        c = str(col).strip().lower()
        if all(s in c for s in include) and not any(s in c for s in exclude):
            return col
    return None

def parse_ground_truth(path: Path):
    sheets = pd.read_excel(path, sheet_name=None, engine="openpyxl")
    sheet_info = {}
    data = {}
    for name, df in sheets.items():
        df = df.dropna(how="all").copy()
        cols = list(df.columns)
        sheet_info[str(name)] = {"rows":len(df),"columns":[str(x) for x in cols]}
        id_col = select_column(cols, ("image",)) or select_column(cols, ("file",)) or select_column(cols, ("photo",))
        warp_col = select_column(cols, ("warp",)) or select_column(cols, ("end",))
        weft_col = select_column(cols, ("weft",)) or select_column(cols, ("pick",))
        texture_col = select_column(cols, ("texture",)) or select_column(cols, ("weave",))
        # FabricNET usually provides 130 ordered rows, and may use numeric filenames.
        if warp_col is None or weft_col is None:
            continue
        for i, (_, record) in enumerate(df.iterrows(), 1):
            if id_col is not None:
                value = str(record.get(id_col, ""))
                match = ID_PATTERN.search(value.replace(".jpg",""))
                index = int(match.group(1)) if match else None
            elif len(df)==130:
                index = i
            else:
                index = None
            if index is None or not (1<=index<=130):
                continue
            key = f"W{index:03d}.jpg"
            def numeric(col):
                try:
                    value = float(record.get(col))
                    return value if np.isfinite(value) and value > 0 else None
                except (ValueError, TypeError):
                    return None
            data[key] = {
                "warp": numeric(warp_col),
                "weft": numeric(weft_col),
                "texture": str(record.get(texture_col, "")) if texture_col else None,
            }
    return data, sheet_info

def overlay(frame: np.ndarray, result: dict, selected_runs: dict):
    output = frame.copy()
    orientation = result.get("orientation") or {}
    norm = result.get("normalization") or {}
    total = {}
    lines_public = result.get("centerline_evidence") or {}
    for key, color in (("warp",(0,10,255)),("weft",(255,230,0))):
        points = lines_public.get(key) or []
        if not points and norm:
            angle = orientation.get(f"{key}_direction_deg")
            selected = selected_runs.get(round(float(angle)%180.,4)) if angle is not None else None
            if selected:
                try:
                    points = map_centerlines_to_reflection(selected["_width_seed"], norm,
                        np.array([[1,0,0],[0,1,0]],np.float32))
                except Exception:
                    pass
        valid = 0
        for p in points:
            p = np.asarray(p)
            if p.ndim==2 and p.shape[0]>=2 and p.shape[1]==2:
                cv2.polylines(output,[np.rint(p).astype(np.int32)],False,color,1,cv2.LINE_AA)
                valid += 1
        total[key] = valid
    # Explicitly annotate pseudo-RT, never imply a genuine dual capture.
    cv2.rectangle(output,(0,0),(frame.shape[1]-1,30),(35,35,35),-1)
    cv2.putText(output,"Warp=RED Weft=CYAN / SINGLE IMAGE / NOT TRUE R-T",
                (5,20),cv2.FONT_HERSHEY_SIMPLEX,.43,(250,250,250),1,cv2.LINE_AA)
    return output,total

def predict_one(image_path: Path, output: Path):
    start = time.monotonic()
    image_bytes = image_path.read_bytes()
    frame = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8),cv2.IMREAD_COLOR)
    selected_runs = {}
    original_run = pipeline._run_direction
    def intercept(normalized, angle, mmx, mmy):
        run = original_run(normalized,angle,mmx,mmy)
        selected_runs[round(float(angle)%180.,4)] = run
        return run
    pipeline._run_direction = intercept
    try:
        result = pipeline.run_measurement(
            image_bytes,image_bytes,
            mm_per_px_x=5.0/640.0,
            mm_per_px_y=4.0/480.0,
            warp_axis_hint="vertical",
        )
    finally:
        pipeline._run_direction = original_run
    overlay_image,counts = overlay(frame,result,selected_runs)
    (output/"overlays").mkdir(exist_ok=True,parents=True)
    cv2.imwrite(str(output/"overlays"/image_path.name),overlay_image,
                [cv2.IMWRITE_JPEG_QUALITY,95])
    status=result.get("status")
    ori=result.get("orientation") or {}
    return {
        "image":image_path.name,
        "source_sha256":hashlib.sha256(image_bytes).hexdigest(),
        "status":status,
        "failure_reasons":"|".join(result.get("failure_reasons") or []),
        "warp_density_per_cm":result.get("warp_density_per_cm"),
        "weft_density_per_cm":result.get("weft_density_per_cm"),
        "warp_direction_deg":ori.get("warp_direction_deg"),
        "weft_direction_deg":ori.get("weft_direction_deg"),
        "warp_lines":counts["warp"],"weft_lines":counts["weft"],
        "gate3":(result.get("gate3") or {}).get("status"),
        "width_status":(result.get("apparent_width") or {}).get("status"),
        "runtime_s":round(time.monotonic()-start,3),
        "input_mode":"DUPLICATED_SINGLE_MICROSCOPE_PHOTO_NOT_GENUINE_RT",
    }

def fnum(x):
    try:
        n=float(x)
        return n if np.isfinite(n) else None
    except (ValueError,TypeError):
        return None

def attach_truth(row, truth):
    ref=truth.get(row["image"],{})
    row.update(truth_warp=ref.get("warp"),truth_weft=ref.get("weft"),
               truth_texture=ref.get("texture"))
    for key in ("warp","weft"):
        pred=fnum(row.get(key+"_density_per_cm"))
        gt=fnum(row.get("truth_"+key))
        row[key+"_abs_error"]=round(abs(pred-gt),4) if pred is not None and gt is not None else None
        row[key+"_rel_error_pct"]=round(abs(pred-gt)/gt*100,4) if pred is not None and gt and gt>0 else None
    a,b=row.get("warp_rel_error_pct"),row.get("weft_rel_error_pct")
    row["both_within_10pct"]=int(a<=10 and b<=10) if a is not None and b is not None else None
    return row

def sheet(paths, destination, title, per_row=5):
    if not paths:
        return
    tile_w,tile_h=350,300
    rows=(len(paths)+per_row-1)//per_row
    board=np.full((rows*tile_h,per_row*tile_w,3),235,dtype=np.uint8)
    for index,path in enumerate(paths):
        image=cv2.imread(str(path))
        if image is None: continue
        im=cv2.resize(image,(tile_w,tile_h-30),interpolation=cv2.INTER_AREA)
        y=(index//per_row)*tile_h; x=(index%per_row)*tile_w
        board[y:y+tile_h-30,x:x+tile_w]=im
        cv2.putText(board,path.stem,(x+7,y+tile_h-9),cv2.FONT_HERSHEY_SIMPLEX,.60,(30,30,30),2,cv2.LINE_AA)
    cv2.imwrite(str(destination),board,[cv2.IMWRITE_JPEG_QUALITY,90])

def summarize(rows,output,sheet_info,rev):
    measured=[r for r in rows if fnum(r["warp_density_per_cm"]) is not None and fnum(r["weft_density_per_cm"]) is not None]
    paired=[r for r in measured if r.get("warp_abs_error") is not None and r.get("weft_abs_error") is not None]
    stat={
       "dataset":"acseckin/FabricNET",
       "engine_ref":rev,"n_images":len(rows),
       "n_measured":len(measured),"n_scored":len(paired),
       "n_both_within_10pct":sum(x["both_within_10pct"] or 0 for x in paired),
       "warp_mae_per_cm":float(np.mean([r["warp_abs_error"] for r in paired])) if paired else None,
       "weft_mae_per_cm":float(np.mean([r["weft_abs_error"] for r in paired])) if paired else None,
       "status_histogram":{s:sum(r["status"]==s for r in rows) for s in sorted(set(r["status"] for r in rows))},
       "truth_workbook":sheet_info,
       "input_mode":"Single microscope photograph duplicated as two API inputs, NOT real R/T",
       "scoring_note":"Absolute density errors only; NO ground truth physical yarn ID, no centerline F1",
       "calibration_note":"Assume full 640x480 microscope image corresponds to 5mm x 4mm as paper. No independent per-photo geometry certified.",
       "warp_hint":"vertical, fixed before labels are loaded",
    }
    (output/"summary.json").write_text(json.dumps(stat,ensure_ascii=False,indent=2),encoding="utf8")
    all_sorted=sorted(rows,key=lambda r: (-(max(r.get("warp_rel_error_pct") or 0,r.get("weft_rel_error_pct") or 0)),r["image"]))
    best_sorted=sorted(paired,key=lambda r: max(r["warp_rel_error_pct"],r["weft_rel_error_pct"]))
    sheet([output/"overlays"/r["image"] for r in all_sorted[:20]],output/"worst20.jpg","Worst20")
    sheet([output/"overlays"/r["image"] for r in best_sorted[:20]],output/"best20.jpg","Best20")
    sheet([output/"overlays"/r["image"] for r in rows[:25]],output/"first25.jpg","First25")
    lines=[
        "# FabricNET 130 -- Shibie blind replay",
        "",
        f"- Engine commit: \`{rev}\`",
        f"- Images: {len(rows)}; returned densities: {len(measured)}; scored pairs: {len(paired)}",
        f"- Warp MAE: {stat['warp_mae_per_cm']} yarns/cm; weft MAE: {stat['weft_mae_per_cm']} yarns/cm",
        f"- Both axes relative error <=10%: {stat['n_both_within_10pct']}/{len(rows)} (full dataset); {stat['n_both_within_10pct']}/{len(paired)} (scorable)",
        f"- Status: {stat['status_histogram']}",
        "",
        "**Input is one physical microscope photo supplied TWICE to the historical API. It is not genuine reflected/transmitted paired capture.**",
        "GT was read *after* each inference. Photo scale uses dataset paper's 5mm x 4mm across original image, not 5cm calibration frame.",
        "The overlay is directly drawn from engine selected centerlines (red warp, cyan weft).",
        "FabricNET does not contain individual physical yarn ID / pixel GT; visual centerline correctness cannot be numerically measured as centerline F1.",
        "Do not present these overlays as visually certified without opening the actual artifacts and reviewing them.",
        "",
        "## Deliverables",
        "- metrics.csv (130 rows, include refused predictions)",
        "- summary.json (dataset level metrics and Excel schema)",
        "- overlays/W###.jpg (actual algorithm traces, not redrawn ideal regular grids)",
        "- worst20.jpg, best20.jpg, first25.jpg (contact sheets for independent visual review)",
    ]
    (output/"REPORT.md").write_text("\n".join(lines)+"\n",encoding="utf8")
    print("SUMMARY "+json.dumps({k:v for k,v in stat.items() if k!="truth_workbook"},ensure_ascii=False),flush=True)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--dataset",type=Path,default=Path("/tmp/fabricnet_public_dataset"))
    ap.add_argument("--rev",default=os.environ.get("GITHUB_SHA","UNVERIFIED"))
    args=ap.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    image_files=fetch_dataset(args.dataset)
    truth,schema=parse_ground_truth(args.dataset/"FabricNet_parameters.xlsx")
    print("FABRICNET_EXCEL_SCHEMA "+json.dumps(schema),flush=True)
    print("TRUTH_ENTRIES "+str(len(truth)),flush=True)
    rows=[]
    for idx,image in enumerate(image_files,1):
        try:
            row=predict_one(image,args.output)
        except Exception as exc:
            print("EXCEPTION "+str(image)+" "+repr(exc),flush=True)
            traceback.print_exc()
            row={k:None for k in FIELDS}
            row.update(image=image.name,source_sha256=hashlib.sha256(image.read_bytes()).hexdigest(),
                       status="EXCEPTION",failure_reasons=str(exc),
                       input_mode="DUPLICATED_SINGLE_MICROSCOPE_PHOTO_NOT_GENUINE_RT")
        row=attach_truth(row,truth)
        rows.append(row)
        print(f"[{idx}/130] {row['image']} {row['status']} WARP={row['warp_density_per_cm']} WEFT={row['weft_density_per_cm']}",flush=True)
    with (args.output/"metrics.csv").open("w",newline="",encoding="utf-8-sig") as fp:
        writer=csv.DictWriter(fp,fieldnames=FIELDS,extrasaction="ignore")
        writer.writeheader();writer.writerows(rows)
    summarize(rows,args.output,schema,args.rev)

if __name__=="__main__":
    main()
