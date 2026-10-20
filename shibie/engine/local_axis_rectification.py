from __future__ import annotations
"""Image-only local axis estimation relative to the 50mm fixture.

The camera/fiducial homography does NOT define a woven cloth's intrinsic
warp/weft directions. Search candidate cloth angles using *both* periodic
normal profiles and cross-modal support, with an explicit ambiguity veto.
No generator truth, known weave, or nominal warp/weft densities are inputs.
"""
from dataclasses import dataclass
import cv2
import numpy as np
from .multiwindow_pitch import PitchSettings, _lags, frame_windows

@dataclass(frozen=True)
class AxisScanConfig:
    min_angle_deg: int = -30
    max_angle_deg: int = 30
    step_deg: int = 2
    inner_px: int = 520
    min_score: float = .13
    min_gain_over_zero: float = .02

def _rotate_crop(img, angle, inner):
    n=img.shape[0]
    H=cv2.getRotationMatrix2D((n/2.,n/2.),float(angle),1.)
    aligned=cv2.warpAffine(img,H,(n,n),flags=cv2.INTER_LINEAR,
                         borderMode=cv2.BORDER_REFLECT101)
    margin=(n-inner)//2
    return aligned[margin:margin+inner,margin:margin+inner]

def _candidate_strength(R,T,angle,pitch_settings,scan):
    a=_rotate_crop(R,angle,scan.inner_px)
    b=_rotate_crop(T,angle,scan.inner_px)
    rg=cv2.cvtColor(a,cv2.COLOR_BGR2GRAY)
    tg=cv2.cvtColor(b,cv2.COLOR_BGR2GRAY)
    result=[]
    for axis in (0,1):
        rr=_lags(np.median(rg,axis=axis).astype(np.float32),pitch_settings)
        tt=_lags(np.median(tg,axis=axis).astype(np.float32),pitch_settings)
        xr=rr[0]["acf"] if rr else 0.
        xt=tt[0]["acf"] if tt else 0.
        result.append(float(.25*max(xr,0)+.75*max(xt,0)))
    return float(np.sqrt(max(result[0],0)*max(result[1],0))),result

def estimate_fabric_axis_from_frame(R,T,frame,
                                    pitch_settings=PitchSettings(),
                                    config=AxisScanConfig()):
    if frame.get("status")!="PASS":
        return {"status":"UNDETERMINED","reason":"FRAME_NOT_RECTIFIED"}
    if R.shape!=T.shape:
        raise ValueError("RT_IMAGE_SHAPE_MISMATCH")
    # The center patch alone proposes an angle. Independent patches MUST audit
    # it below; do not average arbitrary mutually incompatible directions.
    transforms=list(frame_windows(frame,3,pitch_settings.window_size_px))
    center=next(H for i,j,H in transforms if (i,j)==(1,1))
    n=pitch_settings.window_size_px
    r=cv2.warpPerspective(R,center,(n,n))
    t=cv2.warpPerspective(T,center,(n,n))
    trials=[]
    for angle in range(config.min_angle_deg,config.max_angle_deg+1,config.step_deg):
        score,families=_candidate_strength(r,t,angle,pitch_settings,config)
        trials.append({"image_rotation_deg":angle,"joint_score":round(score,5),
                       "family_period_support":[round(x,5) for x in families]})
    ranked=sorted(trials,key=lambda item:item["joint_score"],reverse=True)
    best=ranked[0];neutral=next((x for x in trials if x["image_rotation_deg"]==0),None)
    # A 90degree exchange remains possible; report axis group without claiming
    # automatically assigned warp/weft identity.
    status="CANDIDATE_ONLY" if best["joint_score"]>=config.min_score else "UNDETERMINED"
    if (neutral is not None and best["image_rotation_deg"]!=0
        and best["joint_score"]-neutral["joint_score"]<config.min_gain_over_zero):
        status="LOW_CONFIDENCE"
    # Audit independent windows at selected angle for periodic support (without labels).
    checks=[]
    for i,j,H in transforms:
        if (i,j)==(1,1):continue
        rr=cv2.warpPerspective(R,H,(n,n))
        tt=cv2.warpPerspective(T,H,(n,n))
        score,_=_candidate_strength(rr,tt,best["image_rotation_deg"],pitch_settings,config)
        checks.append({"grid":[i,j],"support":round(score,5)})
    if sum(x["support"]>=config.min_score for x in checks)<4:
        status="LOW_CONFIDENCE"
    return {"status":status,"image_rotation_deg":best["image_rotation_deg"],
            "image_rotation_definition":"OpenCV rotate captured rectangle to align yarn axes",
            "candidate_score":best["joint_score"],
            "unrotated_score":neutral["joint_score"] if neutral else None,
            "independent_support_windows":sum(x["support"]>=config.min_score for x in checks),
            "independent_windows":checks,"top_competitors":ranked[:6],
            "reason":"ROTATION_PERIODICITY_IS_CANDIDATE_NOT_YARN_IDENTITY_PROOF"}

def adjusted_window_homography(frame_transform, angle_deg,
                               tile_size=640, inner_size=520):
    # RAW -> original 640px frame tile -> image rotated about tile center ->
    # central 520px crop. This map must ALSO transform independent GT curves.
    center=tile_size/2.
    rotation=cv2.getRotationMatrix2D((center,center),float(angle_deg),1.)
    H=np.eye(3,dtype=np.float64);H[:2,:]=rotation
    margin=(tile_size-inner_size)//2
    T=np.eye(3,dtype=np.float64);T[:2,2]=-margin
    return T@H@np.asarray(frame_transform,dtype=np.float64)
