"""V6 opt-in candidate overlays, preserving V4 raw-vs-corrected evidence."""
from __future__ import annotations
from pathlib import Path
import cv2
import numpy as np

def draw_ab(image, family_a, family_b, annotation, origin_xy=(0,0),
            *, a_calibrated=False, b_calibrated=False, max_side=1200):
    h,w=image.shape[:2]
    k=min(1.0,max_side/max(w,h))
    preview=cv2.resize(image,(round(w*k),round(h*k)),interpolation=cv2.INTER_AREA) if k<1 else image.copy()
    for name,tracks,color in (
        ("A",family_a,(35,55,250)), # red
        ("B",family_b,(25,210,55) if b_calibrated else (140,145,130)), # green only if human-calibrated
    ):
        for track in tracks:
            pts=np.asarray(track,dtype=np.float32)
            if pts.ndim!=2 or pts.shape[1]!=2 or len(pts)<2:continue
            cv2.polylines(preview,[np.rint(pts*k).astype(np.int32)],False,color,1,cv2.LINE_AA)
    for field,color in (
        ("reference",(0,225,255)),
        ("check_same",(255,245,0)),
        ("holdout_same",(255,0,255)),
        ("check_cross",(255,160,90)),
        ("check_cross_second",(240,80,205)),
    ):
        pair=annotation["segments"].get(field)
        if pair is None:continue
        pts=np.asarray(pair,dtype=np.float64)-np.asarray(origin_xy,dtype=np.float64)
        pts=np.rint(pts*k).astype(np.int32)
        cv2.line(preview,tuple(pts[0]),tuple(pts[1]),color,3,cv2.LINE_AA)
    header=np.zeros((38,preview.shape[1],3),dtype=np.uint8)
    msg=("A RED=CALIBRATED" if a_calibrated else "A RED=V4 RAW") + (" / B GREEN=CALIBRATED" if b_calibrated else " / B GRAY=UNVERIFIED")
    cv2.putText(header,msg,(7,25),cv2.FONT_HERSHEY_SIMPLEX,.48,(255,255,255),1,cv2.LINE_AA)
    return np.vstack([header,preview])

def save_compare(image, original_a, original_b, revised_a, revised_b, annotation, origin,
                 out_dir: Path, *, b_calibrated=False):
    out_dir=Path(out_dir)
    raw=draw_ab(image,original_a,original_b,annotation,origin,b_calibrated=False)
    repaired=draw_ab(image,revised_a,revised_b,annotation,origin,a_calibrated=True,b_calibrated=b_calibrated)
    # Clearly mark the raw side independently of the patched candidate side.
    cv2.putText(raw,"FROZEN V5 ORIGINAL",(8,raw.shape[0]-10),cv2.FONT_HERSHEY_SIMPLEX,.6,(255,255,255),2,cv2.LINE_AA)
    cv2.putText(repaired,"V6 HUMAN TWO-ANCHOR CANDIDATE",(8,repaired.shape[0]-10),cv2.FONT_HERSHEY_SIMPLEX,.6,(255,255,255),2,cv2.LINE_AA)
    side=cv2.hconcat([raw,repaired])
    if not cv2.imwrite(str(out_dir/"v5_v6_side_by_side.jpg"),side):
        raise RuntimeError("cannot write side-by-side evidence")
    if not cv2.imwrite(str(out_dir/"v6_candidate_ab.jpg"),repaired):
        raise RuntimeError("cannot write candidate A/B evidence")
