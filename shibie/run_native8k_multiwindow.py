from __future__ import annotations
"""8k experimental multiwindow/physical-centre audit.

All GT reads occur only AFTER independent pixel-only inference is complete.
The synthetic label of yarn darkness, weave or camera H is not a prior.
"""
import json
import resource
import time
from pathlib import Path
import cv2
import numpy as np
from scipy.optimize import linear_sum_assignment
from engine.multiwindow_pitch import (PitchSettings,detect_calibration_frame,
                                       collect_pitch_windows,frame_windows)
from engine.physical_center_validation import validate_physical_centers

OUT=Path("experiments/shibie-8k-capture-multiwindow/smoke")

def _truth_at_mid(gt,family,M,size):
    values=[]
    axis=1 if family=="warp" else 0
    normal=0 if family=="warp" else 1
    for entity in gt["physical_yarn_centerlines"][family]:
        pts=np.asarray(entity["points"],dtype=np.float32)
        pts=cv2.perspectiveTransform(pts[None],M)[0]
        k=int(np.argmin(np.abs(pts[:,axis]-size/2)))
        if abs(pts[k,axis]-size/2)>35:continue
        center=float(pts[k,normal])
        if center>=0 and center<size:values.append(center)
    return np.asarray(sorted(values))

def _f1(pred,truth,pitch):
    a=np.asarray(pred,float);b=np.asarray(truth,float)
    if not len(a) or not len(b):
        return {"f1_proxy":0.,"matched":0,"truth":len(b),"predicted":len(a)}
    cost=np.abs(a[:,None]-b[None,:])
    i,j=linear_sum_assignment(cost)
    match=int(np.sum(cost[i,j]<.32*pitch))
    nearest=np.min(cost,axis=1)
    return {"f1_proxy":round(2*match/(len(a)+len(b)),4),"matched":match,
      "truth":len(b),"predicted":len(a),
      "median_nearest_fraction_pitch":round(float(np.median(nearest)/pitch),4),
      "half_pitch_fraction":round(float(np.mean((nearest/pitch>.36)&(nearest/pitch<.64))),4),
      "note":"window mid-cross-section proxy, not occlusion-aware identity F1"}

def _draw(patch,family,centers,color):
    img=patch.copy();size=img.shape[0]
    for c in centers:
        d=int(round(float(c)))
        if family=="warp":pt1,pt2=(d,0),(d,size-1)
        else:pt1,pt2=(0,d),(size-1,d)
        cv2.line(img,pt1,pt2,color,2,cv2.LINE_AA)
    return img

def _composite(R,T,window_mats,pitch,gt,rows,out):
    # Independent high-resolution crop saved without upscaling or rendering tricks.
    size=640
    imgs=[]
    for i,j,M in window_mats:
        if (i,j)!=(1,1):continue
        RR=cv2.warpPerspective(R,M,(size,size))
        TT=cv2.warpPerspective(T,M,(size,size))
        imgs=[RR,TT]
        for family in ("warp","weft"):
            if pitch["families"].get(family,{}).get("pitch_px") is None:continue
            row=next(x for x in rows if x["grid"]==[i,j] and x["family"]==family)
            true=_truth_at_mid(gt,family,M,size)
            c=row.get("center_positions_px",[]) if row["status"]=="PASS" else []
            imgs.append(_draw(TT,family,true,(255,30,205)))
            imgs.append(_draw(TT,family,c,(30,55,245)))
    if imgs:
        labels=["Reflection","Transmission","GT-Warp","New-Warp","GT-Weft","New-Weft"][:len(imgs)]
        vis=np.full((2*size,3*size,3),236,dtype=np.uint8)
        for k,im in enumerate(imgs):
            i,j=divmod(k,3)
            vis[i*size:(i+1)*size,j*size:(j+1)*size]=im
            cv2.rectangle(vis,(j*size,i*size),(j*size+200,i*size+30),(255,255,255),-1)
            cv2.putText(vis,labels[k],(j*size+8,i*size+23),
                cv2.FONT_HERSHEY_SIMPLEX,.7,(10,10,10),2,cv2.LINE_AA)
        cv2.imwrite(str(out/"multiwindow_center_evidence.jpg"),vis)

def main():
    start=time.perf_counter()
    R=cv2.imread(str(OUT/"reflection_8000x6000.jpg"),cv2.IMREAD_COLOR)
    T=cv2.imread(str(OUT/"transmission_8000x6000.jpg"),cv2.IMREAD_COLOR)
    if R is None or T is None or R.shape[:2]!=(6000,8000) or T.shape[:2]!=(6000,8000):
        raise RuntimeError("FULL_RESOLUTION_PAIR_REQUIRED")
    frame=detect_calibration_frame(R)
    result={"frame":frame,"status":"UNDETERMINED"}
    if frame.get("status")!="PASS":
        (OUT/"multiwindow_metrics.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
        print("FRAME_DETECTION_FAILED "+json.dumps(result),flush=True)
        return
    settings=PitchSettings()
    summary=collect_pitch_windows(R,T,frame,settings)
    # GT is explicitly unread until the last inference step completes.
    rows=[]
    generated=list(frame_windows(frame,settings.grid,settings.window_size_px))
    for item in summary["windows"]:
        i,j=item["grid"]
        M=next(m for a,b,m in generated if a==i and b==j)
        rp=cv2.warpPerspective(R,M,(settings.window_size_px,settings.window_size_px))
        tp=cv2.warpPerspective(T,M,(settings.window_size_px,settings.window_size_px))
        for family in ("warp","weft"):
            global_choice=summary["families"].get(family,{})
            if "pitch_px" in global_choice:
                guess=validate_physical_centers(rp,tp,family,global_choice["pitch_px"])
            else:
                guess={"status":"UNDETERMINED","reason":"NO_CONSENSUS_PITCH"}
            rows.append({"grid":[i,j],"family":family,**guess})
    # After all image-only inference completed, load the metadata exclusively for scoring.
    gt=json.loads((OUT/"truth.json").read_text(encoding="utf-8"))
    for row in rows:
        i,j=row["grid"];fam=row["family"]
        M=next(m for a,b,m in generated if a==i and b==j)
        truth=_truth_at_mid(gt,fam,M,settings.window_size_px)
        pitch=gt["true_pitch_px_canonical"][fam]
        predicted=row.get("center_positions_px",[]) if row["status"]=="PASS" else []
        row["ground_truth_assessment_only"]=_f1(predicted,truth,pitch)
    for family in ("warp","weft"):
        arr=[r["ground_truth_assessment_only"]["f1_proxy"] for r in rows if r["family"]==family]
        result[family+"_local_f1_proxy"]=round(float(np.mean(arr)),4)
        result[family+"_passed_windows"]=sum(r["status"]=="PASS" for r in rows if r["family"]==family)
        result[family+"_pitch_candidate"]=summary["families"][family]
    result.update({"status":"CANDIDATE_ONLY",
       "runtime_seconds":round(time.perf_counter()-start,2),
       "peak_rss_mib":round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,2),
       "warnings":["SIMULATED_DATA_NOT_REAL_CAMERA","NO_COMPLETE_YARN_IDENTITY_TRAJECTORY_SCORE",
                   "FRAME_CORNERS_DETECTED_FROM_IMAGE_NOT_FROM_SYNTHETIC_TRUTH"],
       "window_evidence":rows})
    (OUT/"multiwindow_metrics.json").write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding="utf-8")
    _composite(R,T,generated,summary,gt,rows,OUT)
    print("MULTIWINDOW_RESULTS "+json.dumps({k:v for k,v in result.items() if k!="window_evidence"},
          ensure_ascii=False),flush=True)

if __name__=="__main__":main()
