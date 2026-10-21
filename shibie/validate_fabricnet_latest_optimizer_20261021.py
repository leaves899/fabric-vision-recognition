#!/usr/bin/env python3
"""FabricNET compatibility diagnostic for *experimental* physical-yarn arms.

NOT a deployment test: FabricNET has NO physical 50mm frame and NO genuine
reflection/transmission pair. The exact same microscope image is fed twice.
All inference is blind to reference warp/weft and weave type.
"""
from __future__ import annotations
import argparse
import csv
import json
import time
from pathlib import Path

import cv2
import numpy as np

from engine.multiwindow_pitch import PitchSettings, analyze_pitch_window, detect_calibration_frame
from engine.subpixel_physical_phase import validate_centers_fractional
from engine.local_yarn_tracks import trace_local_yarns
from engine.individual_yarn_tracelets import trace_individual_entities
from validate_fabricnet_latest_20261021 import fetch_dataset,parse_ground_truth,sheet

ARMS=("FLOAT_LOCAL","SHARED_SEVEN","INDIVIDUAL_SEVEN")
FAMILIES=("warp","weft")

def annotate(patch, results):
    out=patch.copy()
    for family,color in (("warp",(0,0,255)),("weft",(255,255,0))):
        obj=results[family]
        if obj.get("status")!="PASS":
            continue
        if "center_positions_px" in obj:
            for x in obj.get("center_positions_px", []):
                z=int(round(float(x)))
                if family=="warp":
                    cv2.line(out,(z,0),(z,out.shape[0]-1),color,1,cv2.LINE_AA)
                else:
                    cv2.line(out,(0,z),(out.shape[1]-1,z),color,1,cv2.LINE_AA)
        for item in obj.get("tracks",[]):
            pts=np.asarray(item["points"],dtype=np.float32)
            if len(pts)>1:
                cv2.polylines(out,[np.rint(pts).astype(np.int32)],False,color,1,cv2.LINE_AA)
    return out

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--out",required=True,type=Path)
    parser.add_argument("--dataset",type=Path,default=Path("/tmp/fabricnet_public_dataset"))
    parser.add_argument("--sha",required=True)
    a=parser.parse_args()
    a.out.mkdir(parents=True,exist_ok=True)
    images=fetch_dataset(a.dataset)
    truth,truth_schema=parse_ground_truth(a.dataset/"FabricNet_parameters.xlsx")
    records=[]
    for i,path in enumerate(images,1):
        start=time.monotonic()
        raw=cv2.imread(str(path))
        if raw is None: raise RuntimeError("IMAGE_DECODING_FAILED:"+str(path))
        h,w=raw.shape[:2]
        box_status=detect_calibration_frame(raw).get("status")
        # The original experimental native-8K entry point REQUIRES a 50mm
        # calibration frame. Do not fake a passing frame. Run local candidate
        # modules separately and report them as incompatible diagnostics.
        side=min(h,w)
        x0=(w-side)//2;y0=(h-side)//2
        patch=raw[y0:y0+side,x0:x0+side]
        pitch=analyze_pitch_window(patch,patch,PitchSettings())
        results={arm:{} for arm in ARMS}
        for family in FAMILIES:
            choices=pitch.get(family,{}).get("candidates",[])
            candidate=choices[0]["pitch_px"] if choices else None
            if candidate is None:
                for arm in ARMS:
                    results[arm][family]={"status":"UNDETERMINED","reason":"NO_PIXEL_PITCH"}
                continue
            try:
                results["FLOAT_LOCAL"][family]=validate_centers_fractional(patch,patch,family,candidate)
            except Exception as ex:
                results["FLOAT_LOCAL"][family]={"status":"EXCEPTION","reason":str(ex)}
            try:
                results["SHARED_SEVEN"][family]=trace_local_yarns(patch,patch,family,candidate)
            except Exception as ex:
                results["SHARED_SEVEN"][family]={"status":"EXCEPTION","reason":str(ex)}
            try:
                results["INDIVIDUAL_SEVEN"][family]=trace_individual_entities(patch,patch,family,candidate)
            except Exception as ex:
                results["INDIVIDUAL_SEVEN"][family]={"status":"EXCEPTION","reason":str(ex)}
        for arm in ARMS:
            group=results[arm]
            for family in FAMILIES:
                r=group[family]
                status=r.get("status","UNDETERMINED")
                gt=truth.get(path.name,{})
                normal_mm_px=(5.0/640 if family=="warp" else 4.0/480)
                p=r.get("pitch_px")
                density=10.0/(p*normal_mm_px) if (status=="PASS" and p and p>0) else None
                gt_val=gt.get(family)
                records.append({
                    "image":path.name,"arm":arm,"family":family,
                    "official_native8k_frame_status":box_status,
                    "pseudo_rt":"SINGLE_IMAGE_DUPLICATED",
                    "status":status,"reason":r.get("reason"),
                    "detector_pitch_px":p,
                    "pred_density_cm":round(density,3) if density is not None else None,
                    "truth_density_cm":gt_val,
                    "abs_error_cm":round(abs(density-gt_val),3) if density is not None and gt_val is not None else None,
                    "track_count":len(r.get("tracks",r.get("center_positions_px",[]))),
                    "elapsed_image_s":round(time.monotonic()-start,3),
                })
            name=path.name
            (a.out/"overlays"/arm).mkdir(parents=True,exist_ok=True)
            output=annotate(patch,group)
            cv2.rectangle(output,(0,0),(output.shape[1]-1,25),(35,35,35),-1)
            cv2.putText(output,f"{arm} | pseudo RT | red warp / cyan weft",
                        (4,17),cv2.FONT_HERSHEY_SIMPLEX,.39,(240,240,240),1,cv2.LINE_AA)
            cv2.imwrite(str(a.out/"overlays"/arm/name),output,[cv2.IMWRITE_JPEG_QUALITY,90])
        print(f"[{i}/130] {path.name}: frame={box_status}, float W={results['FLOAT_LOCAL']['warp'].get('status')} F={results['FLOAT_LOCAL']['weft'].get('status')}",flush=True)
    if len(records)!=130*len(ARMS)*len(FAMILIES):
        raise RuntimeError("RECORD_COUNT_MISMATCH")
    with (a.out/"metrics.csv").open("w",newline="",encoding="utf-8-sig") as fp:
        writer=csv.DictWriter(fp,fieldnames=list(records[0]))
        writer.writeheader();writer.writerows(records)
    summary={
      "source_engine_sha":a.sha,"total_photos":len(images),
      "input":"SINGLE_MICROSCOPE_PHOTO_DUPLICATED_NOT_GENUINE_RT",
      "official_native8k_frame_pass":sum(r["official_native8k_frame_status"]=="PASS" for r in records if r["arm"]==ARMS[0] and r["family"]=="warp"),
      "arms":{},
      "major_limitations":[
        "These are isolated current native8k detector modules, not the official 8K registered full pipeline.",
        "No 50mm calibration fixture or genuinely paired R/T photographs",
        "No pixel-level physical yarn identities in FabricNET, so no yarn F1",
        "Single central 480px crop; not 9 independent 8K calibration windows",
        "12px optical core and 7..60px pitch rejection limits retained unmodified"],
      "truth_schema":truth_schema,
    }
    for arm in ARMS:
        curr=[r for r in records if r["arm"]==arm]
        valid=[r for r in curr if r["pred_density_cm"] is not None and r["truth_density_cm"] is not None]
        summary["arms"][arm]={
          "status_counts":{s:sum(r["status"]==s for r in curr) for s in sorted(set(x["status"] for x in curr))},
          "scorable_directional_predictions":len(valid),
          "mean_absolute_density_error_scored_only":round(float(np.mean([r["abs_error_cm"] for r in valid])),3) if valid else None,
        }
        sheet([a.out/"overlays"/arm/f"W{i:03d}.jpg" for i in range(1,26)],
              a.out/(arm+"_first25.jpg"),arm)
    (a.out/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    (a.out/"REPORT.md").write_text(
       "# FabricNET latest experimental detector arms (compatibility diagnostic ONLY)\n\n"
       +f"Source engine {a.sha}\n\n"
       +"FabricNET contains no 50mm fixture and no genuine matched reflection/transmission views. "
       +"Official native8K pipeline cannot be certified on it; do not present this result as deployment accuracy.\n"
       +"Individual lines are original arm candidates drawn on the original central image crop, not invented GT.\n\n"
       +json.dumps(summary["arms"],ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("FINAL_SUMMARY "+json.dumps({k:v for k,v in summary.items() if k!="truth_schema"},ensure_ascii=False),flush=True)

if __name__=="__main__":
    main()
