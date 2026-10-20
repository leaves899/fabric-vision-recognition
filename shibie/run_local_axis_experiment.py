from __future__ import annotations
"""Rotated-cloth falsification benchmark at native 8k, no truth in inference."""
import argparse
import json
import math
import time
from pathlib import Path
import cv2
import numpy as np
from scipy.optimize import linear_sum_assignment
from engine.multiwindow_pitch import (PitchSettings, detect_calibration_frame,
    frame_windows, analyze_pitch_window)
from engine.local_axis_rectification import (AxisScanConfig,
    estimate_fabric_axis_from_frame,adjusted_window_homography)
from engine.physical_center_validation import validate_physical_centers

def score_centers(found,real,pitch):
    a=np.asarray(found,float);b=np.asarray(real,float)
    if not len(a) or not len(b):return {"matched":0,"f1_proxy":0., "counted":len(a),"truth":len(b)}
    dist=np.abs(a[:,None]-b[None,:])
    row,col=linear_sum_assignment(dist)
    good=np.sum(dist[row,col]<.32*pitch)
    return {"matched":int(good),"f1_proxy":round(float(2*good/(len(a)+len(b))),4),
            "counted":len(a),"truth":len(b)}

def raw_gt_projected(gt,family,matrix,n):
    axis=1 if family=="warp" else 0
    normal=1-axis
    positions=[]
    for yarn in gt["physical_yarn_centerlines"][family]:
        p=np.asarray(yarn["points"],np.float32)
        img=cv2.perspectiveTransform(p[None],matrix)[0]
        nearest=int(np.argmin(np.abs(img[:,axis]-n/2)))
        if abs(img[nearest,axis]-n/2)<35:
            z=float(img[nearest,normal])
            if 0<z<n:positions.append(z)
    return positions

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--case",required=True)
    a=p.parse_args()
    out=Path("experiments/shibie-8k-capture-multiwindow/stress")/a.case
    r=cv2.imread(str(out/"reflection_8000x6000.jpg"))
    t=cv2.imread(str(out/"transmission_8000x6000.jpg"))
    if r is None or t is None or r.shape[:2]!=(6000,8000):
        raise RuntimeError("NATIVE_PAIR_MISSING")
    frame=detect_calibration_frame(r)
    start=time.perf_counter()
    settings=PitchSettings()
    rotation=estimate_fabric_axis_from_frame(r,t,frame,settings)
    fields=[]
    if rotation["status"]!="UNDETERMINED":
        degree=rotation["image_rotation_deg"]
        for i,j,M in frame_windows(frame,3,settings.window_size_px):
            full=adjusted_window_homography(M,degree,640,520)
            rr=cv2.warpPerspective(r,full,(520,520))
            tt=cv2.warpPerspective(t,full,(520,520))
            pitch=analyze_pitch_window(rr,tt,settings)
            for family in ("warp","weft"):
                choices=pitch[family]["candidates"]
                likely=choices[0]["pitch_px"] if choices else None
                centers=validate_physical_centers(rr,tt,family,likely)
                fields.append({"grid":[i,j],"family":family,"chosen_pitch_px":likely,
                  "candidate_pitches":choices[:3],"centers":centers,
                  "transformation":full.tolist()})
    # Physical truth is opened ONLY after every frame rotation and center choice.
    gt=json.loads((out/"truth.json").read_text(encoding="utf-8"))
    scores={}
    for family in ("warp","weft"):
        assessed=[]
        for field in fields:
            if field["family"]!=family:continue
            M=np.asarray(field["transformation"],np.float64)
            real=raw_gt_projected(gt,family,M,520)
            pred=field["centers"].get("center_positions_px",[]) if field["centers"]["status"]=="PASS" else []
            assessed.append(score_centers(pred,real,gt["true_pitch_px_canonical"][family]))
        scores[family]={
          "local_f1_proxy":round(float(np.mean([x["f1_proxy"] for x in assessed])),4) if assessed else 0.,
          "pass_windows":sum(f["centers"]["status"]=="PASS" for f in fields if f["family"]==family),
          "window_score":assessed}
    truth_rotation=gt["source_scene"].get("fabric_rotation_deg")
    # Truth angle is strictly for audit. OpenCV rotation sign will be tested,
    # not selected by reading this field.
    report={"case":a.case,"pixel_only_axis_estimation":rotation,
       "truth_rotation_deg_EVALUATION_ONLY":truth_rotation,"scores":scores,
       "runtime_seconds":round(time.perf_counter()-start,3),
       "caveats":["POSE_TRUTH_UNAVAILABLE_TO_INFERENCE",
                  "LOCAL_CROSSSECTION_F1_ONLY","UNVALIDATED_ON_REAL_CAMERA"]}
    (out/"local_angle_experiment.json").write_text(
      json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("ROTATION_EXPERIMENT "+json.dumps({
       "case":a.case,"truth_rotation":truth_rotation,"result":rotation,
       "scores":{k:{x:y for x,y in v.items() if x!="window_score"} for k,v in scores.items()}
    },ensure_ascii=False),flush=True)
if __name__=="__main__":main()
