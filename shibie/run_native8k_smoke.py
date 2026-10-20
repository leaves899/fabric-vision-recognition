from __future__ import annotations
"""Native 8k R/T smoke: freeze original V0.6.3 output and audit phase independently.

Simulator truth is opened only after the measurement function returns; it is
never used as an input, crop selector, angle hint or model parameter.
"""
import argparse
import hashlib
import json
import math
import time
import resource
from pathlib import Path
import cv2
import numpy as np
from scipy.optimize import linear_sum_assignment
from synthetic_capture_8k import CaptureScene, generate
from engine import pipeline
from engine.width import map_centerlines_to_reflection

def _rss_mib():
    rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(float(rss)/1024,2)  # Linux CI, KiB

def _angle_diff(a,b):
    return abs((float(a)-float(b)+90)%180-90)

def _angle_of_line(pts):
    p=np.asarray(pts,np.float64)
    vec=p[-1]-p[0]
    return math.degrees(math.atan2(vec[1],vec[0]))%180

def _score_lines(actual_lines, pred_lines, pitch, expected_angle):
    n=np.array([-math.sin(math.radians(expected_angle)),math.cos(math.radians(expected_angle))])
    o=np.array([4000.,3000.])
    def center_at_mid(lines):
        vals=[]
        for line in lines:
            p=np.asarray(line,np.float64)
            if len(p)<2:continue
            q=p[(p[:,0]>=3000)&(p[:,0]<=5000)&(p[:,1]>=2000)&(p[:,1]<=4000)]
            if len(q)<2:q=p
            v=float(np.median((q-o)@n))
            if abs(v)<2100:vals.append(v)
        return vals
    a=center_at_mid(actual_lines);b=center_at_mid(pred_lines)
    if not a or not b:return {"f1_proxy":0.,"matched":0,"truth":len(a),"predicted":len(b)}
    D=np.abs(np.array(a)[:,None]-np.array(b)[None,:])
    i,j=linear_sum_assignment(D)
    good=D[i,j]<.32*pitch
    m=int(good.sum())
    f1=2*m/max(len(a)+len(b),1)
    nearest=np.min(D,axis=0)
    return {"f1_proxy":round(float(f1),4),"matched":m,"truth":len(a),"predicted":len(b),
       "median_nearest_gt_fraction_pitch":round(float(np.median(nearest)/pitch),4),
       "half_pitch_candidate_fraction":round(float(np.mean((nearest/pitch>.36)&(nearest/pitch<.64))),4),
       "note":"mid-ROI projection proxy; not occlusion-aware curve identity F1"}

def _overlay(path, detected, truth):
    img=cv2.imread(str(path))
    for family,col in (("warp",(30,55,245)),("weft",(255,200,30))):
        for l in (truth if truth is not None else detected)[family]:
            pts=np.asarray(l["points"] if isinstance(l,dict) else l)
            if len(pts)>1:cv2.polylines(img,[np.rint(pts).astype(np.int32)],False,col,2,cv2.LINE_AA)
    return img

def run(output:Path):
    gtfile=output/"truth.json"
    if (not gtfile.exists() or not (output/"reflection_8000x6000.jpg").is_file()
            or not (output/"transmission_8000x6000.jpg").is_file()):
        generate(CaptureScene(),output)
    print("START_RAW_ORIGINAL_8K",flush=True)
    r=(output/"reflection_8000x6000.jpg").read_bytes()
    t=(output/"transmission_8000x6000.jpg").read_bytes()
    assert cv2.imdecode(np.frombuffer(r,np.uint8),cv2.IMREAD_REDUCED_COLOR_8).shape[:2]==(750,1000)
    captured={}
    original=pipeline._run_direction
    def wrapper(image,deg,mx,my):
        ans=original(image,deg,mx,my)
        captured[round(float(deg)%180,4)]=ans
        return ans
    pipeline._run_direction=wrapper
    started=time.perf_counter()
    try:
        result=pipeline.run_measurement(r,t,mm_per_px_x=.0125,mm_per_px_y=.0125,sample_id="native_8k_smoke")
    finally:
        pipeline._run_direction=original
    elapsed=time.perf_counter()-started
    # Privacy of ground-truth labels: load them AFTER inference.
    gt=json.loads(gtfile.read_text(encoding="utf-8"))
    orientation=result.get("orientation",{})
    norm=result.get("normalization",{})
    predicted={"warp":[],"weft":[]}
    metrics={"engine_status":result.get("status"),"engine_reasons":result.get("failure_reasons"),
       "runtime_seconds":round(elapsed,2),"peak_rss_mib":_rss_mib(),
       "normalization":norm,"density":{k:result.get(k+"_density_per_cm") for k in ("warp","weft")},
       "recorded_input":gt["sha256"],"baseline_version":"V0.6.3_UNMODIFIED"}
    H=np.asarray(gt["camera_geometry"]["canonical_to_raw_homography"],np.float64)
    pp=np.asarray([[4000.,3000.],[4000.,3500.],[4500.,3000.]],np.float32)
    mapped=cv2.perspectiveTransform(pp[None],H)[0]
    truth_angles={"warp":_angle_of_line(mapped[:2]),"weft":_angle_of_line(mapped[[0,2]])}
    for family in ("warp","weft"):
        angle=orientation.get(family+"_direction_deg")
        cand=captured.get(round(float(angle)%180,4)) if angle is not None else None
        if cand and norm:
            predicted[family]=map_centerlines_to_reflection(
                cand["_width_seed"],norm,np.eye(2,3,dtype=np.float32))
        actual=[x["points"] for x in gt["physical_yarn_centerlines"][family]]
        # Predicted pitch scaled to raw image approximately; homography varies.
        pitch=gt["true_pitch_px_canonical"][family]
        score=_score_lines(actual,predicted[family],pitch,truth_angles[family])
        score.update({"expected_angle_deg":round(truth_angles[family],3),
               "predicted_angle_deg":angle,
               "angle_error_deg":round(_angle_diff(angle,truth_angles[family]),3) if angle is not None else None})
        metrics[family]=score
    (output/"baseline_metrics.json").write_text(json.dumps(metrics,indent=2,ensure_ascii=False),encoding="utf-8")
    raw=output/"transmission_8000x6000.jpg"
    ref_overlay=_overlay(raw,predicted,truth=None)
    gt_overlay=_overlay(raw,predicted,truth=gt["physical_yarn_centerlines"])
    for key,im in (("baseline_overlay",ref_overlay),("physical_truth_overlay",gt_overlay)):
        cv2.imwrite(str(output/(key+".jpg")),cv2.resize(im,(1200,900),interpolation=cv2.INTER_AREA))
        cv2.imwrite(str(output/(key+"_crop.jpg")),im[2700:3300,3700:4300])
    del ref_overlay,gt_overlay
    print("BASELINE_RESULTS "+json.dumps(metrics,ensure_ascii=False),flush=True)
    return metrics

if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("--out",default="experiments/shibie-8k-capture-multiwindow/smoke")
    opts=a.parse_args()
    run(Path(opts.out))
