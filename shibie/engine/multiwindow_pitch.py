from __future__ import annotations
"""Independent native-resolution, multiwindow yarn-pitch hypotheses.

No weave class, physical yarn IDs, simulator seed or ground-truth pitch may enter
this module. Agreement across windows is NOT regarded as proof of a yarn entity.
"""
from dataclasses import dataclass
import math
import cv2
import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.signal import find_peaks, fftconvolve

@dataclass(frozen=True)
class PitchSettings:
    mm_per_px: float = 0.0125
    min_density_cm: float = 15.
    max_density_cm: float = 100.
    window_size_px: int = 640
    grid: int = 3
    competing_ratio: float = .85
    minimum_support_windows: int = 4

def _sort_corners(points):
    q=np.asarray(points,np.float32)
    s=q.sum(axis=1)
    d=np.diff(q,axis=1).ravel()
    return np.float32([q[np.argmin(s)],q[np.argmin(d)],
                       q[np.argmax(s)],q[np.argmax(d)]])

def detect_calibration_frame(reflection):
    """Detect a high-reflectance square *physical fixture* from pixels, not truth.
    Reject ambiguous/no-frame images rather than silently assuming a geometry.
    The 50x50mm size is the only provided calibration information.
    """
    small=cv2.resize(reflection,(1000,750),interpolation=cv2.INTER_AREA)
    gray=cv2.cvtColor(small,cv2.COLOR_BGR2GRAY)
    # Two independent diagnostics; the bright frame must be a closed contour.
    candidates=[]
    for threshold in (206,214,222):
        mask=(gray>=threshold).astype(np.uint8)*255
        mask=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,np.ones((3,3),np.uint8))
        contours,_=cv2.findContours(mask,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
        for cont in contours:
            area=cv2.contourArea(cont)
            if not (20000<area<400000):continue
            peri=cv2.arcLength(cont,True)
            q=cv2.approxPolyDP(cont,.018*peri,True)
            if len(q)!=4 or not cv2.isContourConvex(q):continue
            pts=q.reshape(4,2).astype(np.float32)
            lengths=np.linalg.norm(pts-np.roll(pts,-1,axis=0),axis=1)
            ratio=float(np.min(lengths)/np.max(lengths))
            if ratio<.72:continue
            rect_area=cv2.contourArea(cv2.convexHull(pts))
            fit=min(area/rect_area,rect_area/max(area,1))
            # Prefer the expected frame scale, not simply any bright yarn component.
            area_ratio=area/(1000*750)
            score=ratio*fit*max(0.,1-abs(area_ratio-.34))
            candidates.append((score,pts,threshold))
    if not candidates:
        return {"status":"UNDETERMINED","reason":"FRAME_NOT_FOUND"}
    candidates.sort(key=lambda x:x[0],reverse=True)
    score,pts,threshold=candidates[0]
    if score<.30:
        return {"status":"LOW_CONFIDENCE","reason":"FRAME_GEOMETRY_AMBIGUOUS","score":score}
    corners=_sort_corners(pts)*8
    # Inset ~17px bezel: raw outer contour is slightly outside 50mm interior.
    center=np.mean(corners,axis=0)
    corners=center+(corners-center)*(.99575)
    inner_dim=int(round(50/.0125))
    dest=np.float32([[0,0],[inner_dim,0],[inner_dim,inner_dim],[0,inner_dim]])
    rect=cv2.getPerspectiveTransform(corners,dest)
    return {"status":"PASS","frame_corners_raw_px":corners.tolist(),
            "raw_to_frame":rect.tolist(),"frame_size_px":inner_dim,
            "detection_score":round(float(score),4),"threshold":threshold}

def _lags(profile,settings):
    x=np.asarray(profile,dtype=np.float32)
    n=x.size
    # Robust high-pass avoids illumination drift; do not assume yarn contrast polarity.
    x=x-gaussian_filter1d(x,max(10.,n*.045))
    x-=x.mean()
    scale=float(np.linalg.norm(x))
    if scale<1e-4:return []
    lo=max(6,int(math.floor(10/(settings.max_density_cm*settings.mm_per_px))))
    hi=min(int(math.ceil(10/(settings.min_density_cm*settings.mm_per_px))),n//4)
    if hi<=lo:return []
    corr=fftconvolve(x,x[::-1],mode="full")[n-1:]
    corr=corr/max(float(corr[0]),1e-5)
    span=corr[lo:hi+1]
    peaks,_=find_peaks(span,prominence=max(.035,float(np.std(span))*.24),distance=3)
    ranked=[{"pitch_px":float(lo+k),"acf":round(float(span[k]),4)}
            for k in peaks if span[k]>.07]
    ranked.sort(key=lambda item:item["acf"],reverse=True)
    return ranked[:8]

def _harmonic_candidates(candidates):
    unique={}
    for cand in candidates:
        x=cand["pitch_px"]
        for target in (x,x/2.,x*2.):
            if target<7 or target>55:continue
            key=round(target,1)
            unique[key]=max(unique.get(key,0.),float(cand["acf"])*(1 if target==x else .42))
    return sorted(({"pitch_px":x,"evidence":round(y,4)} for x,y in unique.items()),
                  key=lambda q:q["evidence"],reverse=True)[:8]

def analyze_pitch_window(reflection_patch,transmission_patch,settings=PitchSettings()):
    if reflection_patch.shape!=transmission_patch.shape:
        raise ValueError("PATCH_MISMATCH")
    if min(reflection_patch.shape[:2])<120:
        return {"status":"UNDETERMINED","reason":"PATCH_TOO_SMALL"}
    r=cv2.cvtColor(reflection_patch,cv2.COLOR_BGR2GRAY)
    t=cv2.cvtColor(transmission_patch,cv2.COLOR_BGR2GRAY)
    result={}
    for family,axis in (("warp",0),("weft",1)):
        # For vertical yarns the normal profile varies in X; for horizontal Y.
        a=np.median(r,axis=axis).astype(np.float32)
        b=np.median(t,axis=axis).astype(np.float32)
        acf_t=_lags(b,settings);acf_r=_lags(a,settings)
        combined={}
        for modality,rows in (("T",acf_t),("R",acf_r)):
            for item in _harmonic_candidates(rows):
                q=round(item["pitch_px"])
                if q not in combined:combined[q]={"pitch_px":q,"sources":{}}
                combined[q]["sources"][modality]=max(
                    combined[q]["sources"].get(modality,0.),item["evidence"])
        arr=[]
        for v in combined.values():
            tt=v["sources"].get("T",0.)
            rr=v["sources"].get("R",0.)
            evidence=.70*tt+.30*rr+.12*min(tt,rr)
            arr.append({"pitch_px":v["pitch_px"],"strength":round(evidence,4),
                        "R_support":round(rr,4),"T_support":round(tt,4)})
        arr.sort(key=lambda z:z["strength"],reverse=True)
        result[family]={"candidates":arr[:6],"primary":arr[0] if arr else None,
                        "status":"PASS" if arr else "UNDETERMINED"}
    return result

def frame_windows(frame, count=3, window_size_px=640):
    n=frame["frame_size_px"]
    H=np.asarray(frame["raw_to_frame"],dtype=np.float64)
    grid=np.linspace(window_size_px/2+250,n-window_size_px/2-250,count)
    for i,y in enumerate(grid):
        for j,x in enumerate(grid):
            shift=np.array([[1,0,window_size_px/2-x],
                            [0,1,window_size_px/2-y],[0,0,1]],np.float64)
            yield i,j,shift@H

def collect_pitch_windows(R,T,frame,settings=PitchSettings()):
    if frame.get("status")!="PASS":
        return {"status":"UNDETERMINED","reason":"NO_VALID_FRAME"}
    windows=[]
    for i,j,transform in frame_windows(frame,settings.grid,settings.window_size_px):
        outsize=(settings.window_size_px,settings.window_size_px)
        r=cv2.warpPerspective(R,transform,outsize,flags=cv2.INTER_LINEAR)
        t=cv2.warpPerspective(T,transform,outsize,flags=cv2.INTER_LINEAR)
        scores=analyze_pitch_window(r,t,settings)
        windows.append({"grid":[i,j],"scores":scores,"homography":transform.tolist()})
    final={}
    for family in ("warp","weft"):
        choices=[]
        for w in windows:
            v=w["scores"][family]["primary"]
            if v is not None:choices.append(v["pitch_px"])
        if len(choices)<settings.minimum_support_windows:
            final[family]={"status":"UNDETERMINED","reason":"INSUFFICIENT_WINDOWS"}
            continue
        # Pick the strongest cluster without averaging wrong harmonics together.
        clusters=[]
        for root in sorted(set(choices)):
            members=[v for v in choices if abs(v/root-1)<.12]
            center=float(np.median(members))
            # One family of pitches may be supported by roots 26 and 27 px;
            # it is not two incompatible period hypotheses.
            if any(abs(center/other[1]-1.)<.12 for other in clusters):
                continue
            clusters.append((len(members),center,members))
        clusters.sort(reverse=True,key=lambda z:z[0])
        best=clusters[0]
        supports=len(best[2])
        second=clusters[1] if len(clusters)>1 else None
        if supports<settings.minimum_support_windows or (second and second[0]>=supports-1):
            final[family]={"status":"LOW_CONFIDENCE","reason":"PERIOD_FAMILIES_CONFLICT",
                           "leading_candidates_px":[round(c[1],2) for c in clusters[:3]],
                           "window_support":supports}
            continue
        final[family]={"status":"CANDIDATE_ONLY",
           "pitch_px":round(best[1],4),"density_per_cm":round(10/(best[1]*settings.mm_per_px),3),
           "window_support":supports,"window_count":len(windows),
           "window_cv":round(float(np.std(best[2])/np.mean(best[2])),4),
           "competition_px":[round(c[1],2) for c in clusters[1:4]],
           "reason":"MULTIWINDOW_PITCH_IS_NOT_PHYSICAL_YARN_PROOF"}
    return {"status":"CANDIDATE_ONLY","frame":frame,"families":final,"windows":windows}
