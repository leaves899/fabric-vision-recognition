"""Legacy visible-yarn-anchor experiment (INVALIDATED for U20261013 labels).

On 2026-10-13 the operator clarified that all first batch clicked lines
are INFERRED YARN CONNECTION DIRECTIONS, not visible physical yarn segments.
Never use their pixel positions to fit a ridge or to validate centerlines.
For current samples diagnostic_one ABSTAINS. New direction-only candidate
engine: benchmark.direction_only_first_yarn.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import cv2
import numpy as np
from scipy.signal import find_peaks

ROOT = Path(__file__).resolve().parents[1]
BATCH = "U20261013_"
SCALES = (3, 5, 8, 12, 17)


def axis_deg(segment):
    p = np.asarray(segment, dtype=np.float64)
    v = p[1]-p[0]
    if np.linalg.norm(v) < 20:
        raise ValueError("manual reference too short")
    return float(np.degrees(np.arctan2(v[1], v[0])) % 180)


def axis_diff(a, b):
    return abs((a-b+90.) % 180.-90.)


def manual_interval_pitch(first, other, intervals):
    if not isinstance(intervals, int) or isinstance(intervals, bool) or intervals <= 0:
        return None
    u = np.radians(axis_deg(first))
    normal = np.array([-np.sin(u), np.cos(u)])
    d = abs(float((np.mean(other,axis=0)-np.mean(first,axis=0))@normal))
    return d/intervals


def crop_from_reference(img, reference, margin=350):
    """ROI is located using input-only reference; no check/holdout enters crop."""
    coords=np.asarray(reference, dtype=np.float64)
    h,w=img.shape[:2]
    x0=max(0, int(np.floor(coords[:,0].min()))-margin)
    y0=max(0, int(np.floor(coords[:,1].min()))-margin)
    x1=min(w, int(np.ceil(coords[:,0].max()))+margin)
    y1=min(h, int(np.ceil(coords[:,1].max()))+margin)
    return img[y0:y1,x0:x1].copy(), np.array([x0,y0],float)


def rectify_axis(img, reference):
    """Rotate the known input axis to horizontal without changing pixel scale."""
    ang=axis_deg(reference)
    h,w=img.shape[:2]
    ctr=np.array([w/2,h/2],float)
    affine=cv2.getRotationMatrix2D(tuple(ctr),ang,1.0)
    cs, sn=abs(affine[0,0]),abs(affine[0,1])
    new_w=int(np.ceil(h*sn+w*cs))+2
    new_h=int(np.ceil(h*cs+w*sn))+2
    affine[0,2]+=(new_w/2-ctr[0])
    affine[1,2]+=(new_h/2-ctr[1])
    rotated=cv2.warpAffine(img,affine,(new_w,new_h),
                          flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT_101)
    points=cv2.transform(np.asarray(reference,float).reshape(1,2,2),affine)[0]
    return rotated,affine,points


def transform_points(segment, offset, matrix):
    pts=np.asarray(segment,float)-offset
    return cv2.transform(pts.reshape(1,2,2),matrix)[0]


def oriented_ridge(channel, scale):
    """Signed axis-parallel DoG: narrow center minus wider surroundings."""
    sigma_x=float(max(11, scale*2.5))
    small=cv2.GaussianBlur(channel,(0,0),sigmaX=sigma_x,sigmaY=max(1.,scale*.38))
    large=cv2.GaussianBlur(channel,(0,0),sigmaX=sigma_x,sigmaY=max(3.,scale*1.9))
    return (small-large).astype(np.float32)


def sample_on_line(field, line, n=51, displacement=0.):
    a,b=np.asarray(line,float)
    tt=np.linspace(.10,.90,n,dtype=np.float32)
    xy=(a[None,:]+tt[:,None]*(b-a)[None,:]).astype(np.float32)
    xy[:,1]+=displacement
    mask=((xy[:,0]>=2)&(xy[:,0]<field.shape[1]-2)&
          (xy[:,1]>=2)&(xy[:,1]<field.shape[0]-2))
    if np.count_nonzero(mask) < n*.6:
        return None
    sampled=cv2.remap(field, xy[:,0].reshape(-1,1),xy[:,1].reshape(-1,1),
                      interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT_101)[:,0]
    return float(np.median(sampled[mask]))


def fit_from_reference(img, reference):
    """Template sign/channel/scale fitted on one marked yarn ONLY.

    This is a supervised-anchor localization diagnostic, not auto-yarn direction.
    """
    rotated,m,anchor=rectify_axis(img,reference)
    lab=cv2.cvtColor(rotated,cv2.COLOR_BGR2LAB).astype(np.float32)
    channels={"luminance":lab[:,:,0],"blue_yellow":lab[:,:,2]}
    candidates=[]
    for channel,layer in channels.items():
        for scale in SCALES:
            field=oriented_ridge(layer,scale)
            median=float(np.median(field))
            dispersion=float(np.percentile(np.abs(field-median),70))
            if dispersion < .7:continue
            for sign in (-1,1):
                signal=sign*field/(dispersion+1e-5)
                center=sample_on_line(signal,anchor)
                left=sample_on_line(signal,anchor,displacement=-scale*1.6)
                right=sample_on_line(signal,anchor,displacement=scale*1.6)
                if None in (center,left,right):continue
                # No holdout coordinates used. Avoid templates where reference
                # is less supportive than BOTH symmetric side controls.
                margin=center-.5*(left+right)
                if center>0 and margin>.10:
                    candidates.append((margin,center,channel,scale,sign))
    if not candidates:
        return {"status":"ABSTAIN_REFERENCE_NOT_RIDGE_LIKE"},None
    best=max(candidates, key=lambda x:(x[0],x[1]))
    margin,center,channel,scale,sign=best
    field=oriented_ridge(channels[channel],scale)
    normalization=float(np.percentile(np.abs(field-np.median(field)),70))
    score=sign*field/max(normalization,.7)
    return {"status":"REFERENCE_RIDGE_TEMPLATE",
            "channel":channel,"polarity":"bright" if sign>0 else "dark",
            "scale_px":scale,"reference_margin":round(float(margin),3),
            "reference_response":round(float(center),3),
            "direction_source":"OPERATOR_REFERENCE_ONLY",
            "model_is_not_independent_physical_yarn_detector":True},(rotated,m,anchor,score)


def profile_peaks(score, anchor, scale):
    x0,x1=sorted(anchor[:,0])
    lo=int(np.clip(x0+0.13*(x1-x0),2,score.shape[1]-3))
    hi=int(np.clip(x1-0.13*(x1-x0),lo+1,score.shape[1]-2))
    signal=np.median(score[:,lo:hi],axis=1)
    yref=float(np.mean(anchor[:,1]))
    # Detector does not see check_same, holdout_same or human interval labels.
    prom=max(.11,.22*np.std(signal))
    indices,_=find_peaks(signal,prominence=prom,
                         distance=max(5,int(round(scale*1.30))))
    # filter spurious response weak/negative at the candidate center
    indices=indices[signal[indices] > .05]
    if len(indices)==0:
        return signal,np.array([],int),None
    reference_index=int(indices[np.argmin(abs(indices-yref))])
    # Template sometimes has reference between peaks: do NOT force the closest
    # found peak to be a real yarn; report its actual distance.
    return signal,indices,reference_index


def diagnostic_one(ann, img):
    # 2026-10-13 user correction: these clicked lines are inferred yarn
    # CONNECTION DIRECTIONS, NOT directly visible fiber pixels/centers.
    # Do not fit brightness or grid phase to their arbitrary positions;
    # historical localization metrics are INVALIDATED for these samples.
    if str(ann.get("sample_id","")).startswith("U20261013_"):
        return {
            "sample_id":ann["sample_id"],
            "status":"INVALIDATED_DIRECTION_ONLY_ANNOTATION",
            "manual_reference_axis_deg":round(axis_deg(ann["segments"]["reference"]),3),
            "annotation_semantics":"INFERRED_YARN_CONNECTION_DIRECTION_NOT_VISIBLE_YARN_SEGMENT",
            "physical_yarn_center_gt_available":False,
            "invalidated_metrics":["reference ridge response","photo center offset",
                                  "holdout center distance","interval count errors"],
            "next_step":"Use direction_only_first_yarn for image-only proposals; obtain separate physical visible-yarn pixel validation."
        },None
    ref=ann["segments"]["reference"]
    crop,offset=crop_from_reference(img,ref)
    ref_local=(np.asarray(ref,float)-offset).tolist()
    fit,data=fit_from_reference(crop,ref_local)
    result={"sample_id":ann["sample_id"],
            "image_sha256":ann["image_sha256"],
            "annotation_origin":ann["annotation_origin"],
            "operator_reference_deg":round(axis_deg(ref),3),
            "calibration_inputs":["reference"],
            "heldout":["check_same","holdout_same"],
            "fitted":fit,
            "status":"ABSTAINED"}
    if data is None:
        return result,None
    rotated,m,anchor,score=data
    scale=fit["scale_px"]
    signal,peaks,anchor_idx=profile_peaks(score,anchor,scale)
    result["photo_candidate_count"]=len(peaks)
    if anchor_idx is None:
        result["reason"]="NO_CANDIDATE_PEAKS"
        return result,None
    yref=float(np.mean(anchor[:,1]))
    result["anchor_peak_offset_px"]=round(abs(anchor_idx-yref),3)
    result["photo_center_positions_rotated_y_px"]=peaks.astype(int).tolist()
    if len(peaks)>1:
        result["median_photo_peak_spacing_px"]=round(float(np.median(np.diff(peaks))),3)
    human_pitch=manual_interval_pitch(ref,ann["segments"]["check_same"],
                                      ann["same_family_intervals"])
    result["human_interval_pitch_for_EVALUATION_ONLY_px"]=round(human_pitch,3) if human_pitch else None
    checks={}
    for role in ("check_same","holdout_same"):
        segment=ann["segments"].get(role)
        if not segment:continue
        transformed=transform_points(segment,offset,m)
        yy=float(np.mean(transformed[:,1]))
        nearest=min(peaks,key=lambda p:abs(p-yy))
        response=sample_on_line(score,transformed)
        shifted=[]
        if human_pitch:
            shifted=[sample_on_line(score,transformed,displacement=s*human_pitch*.5)
                     for s in (-1,1)]
        valid=[v for v in shifted if v is not None]
        checks[role]={"axis_error_from_reference_deg":round(axis_diff(
                         axis_deg(ref),axis_deg(segment)),3),
                       "center_dist_to_nearest_photo_peak_px":round(abs(nearest-yy),3),
                       "offset_as_fraction_of_human_pitch":round(abs(nearest-yy)/human_pitch,3)
                            if human_pitch else None,
                       "photo_response_on_operator_yarn":round(response,3) if response is not None else None,
                       "photo_response_minus_half_pitch_controls":round(response-np.mean(valid),3)
                            if response is not None and len(valid)==2 else None,
                       "in_reference_generated_crop": bool(0<=yy<score.shape[0])}
    result["checks"]=checks
    ycheck=float(np.mean(transform_points(ann["segments"]["check_same"],offset,m)[:,1]))
    # Number of photo peaks between true reference and independent check.
    result["image_only_peak_intervals_to_check_same"]=int(sum(
        min(yref,ycheck) < y < max(yref,ycheck) for y in peaks))
    result["human_intervals_EVALUATION_ONLY"]=ann["same_family_intervals"]
    result["count_abs_error_vs_operator_intervals"]=abs(
        result["image_only_peak_intervals_to_check_same"]-ann["same_family_intervals"])
    result["status"]="CANDIDATE_LINES_NOT_PHYSICAL_PROOF"
    return result,(rotated,score,peaks,anchor,m,offset)


def overlay(ann,payload,out):
    rotated,score,peaks,anchor,m,offset=payload
    view=rotated.copy()
    for y in peaks:
        cv2.line(view,(0,int(y)),(view.shape[1]-1,int(y)),(70,220,60),1,cv2.LINE_AA)
    for role,color in (("reference",(0,255,255)),
                       ("check_same",(255,220,0)),
                       ("holdout_same",(255,0,255))):
        seg=ann["segments"].get(role)
        if seg:
            pts=transform_points(seg,offset,m).round().astype(np.int32)
            cv2.line(view,tuple(pts[0]),tuple(pts[1]),color,3,cv2.LINE_AA)
    # Scale preview for review without claiming zoom is new physical detail.
    maxside=1080
    factor=min(1,maxside/max(view.shape[:2]))
    if factor<1:
        view=cv2.resize(view,None,fx=factor,fy=factor,interpolation=cv2.INTER_AREA)
    out.parent.mkdir(parents=True,exist_ok=True)
    cv2.imwrite(str(out),view)


def main(argv=None):
    from benchmark.manual_annotation import validate_annotation
    parser=argparse.ArgumentParser()
    parser.add_argument("--out",default="experiments/first-yarn-evidence")
    parser.add_argument("--root",type=Path,default=ROOT)
    args=parser.parse_args(argv)
    root=args.root.resolve()
    output=Path(args.out)
    if not output.is_absolute():output=root/output
    output.mkdir(parents=True,exist_ok=True)
    reports=[]
    for path in sorted((root/"datasets/annotations/drafts").glob(BATCH+"*.json")):
        ann=validate_annotation(root,json.loads(path.read_text(encoding="utf-8")))
        if ann["review_state"]!="OPERATOR_REVIEWED":continue
        source=(root/ann["image_path"]).read_bytes()
        if hashlib.sha256(source).hexdigest()!=ann["image_sha256"]:
            raise RuntimeError("stale source image")
        img=cv2.imdecode(np.frombuffer(source,np.uint8),cv2.IMREAD_COLOR)
        if img is None or img.shape[1]!=ann["image_width"] or img.shape[0]!=ann["image_height"]:
            raise RuntimeError("native zoom image coordinate mismatch")
        result,payload=diagnostic_one(ann,img)
        reports.append(result)
        if payload is not None:
            overlay(ann,payload,output/(ann["sample_id"]+".jpg"))
        print(json.dumps({"id":result["sample_id"],"status":result["status"],
                          "pitch":result.get("median_photo_peak_spacing_px"),
                          "manual_pitch":result.get("human_interval_pitch_for_EVALUATION_ONLY_px"),
                          "interval_count_error":result.get("count_abs_error_vs_operator_intervals"),
                          "check":result.get("checks",{})},ensure_ascii=False),flush=True)
    meta={"main_baseline":"e1b219384224e1d77c79aa108bef3fb51a39ea56",
          "reviewed_count":len(reports),
          "results":reports,
          "honesty":"Operator reference calibrates appearance/direction. Heldout checks are never used to fit. Candidate peaks are not certified real yarns. No density/cm."}
    (output/"summary.json").write_text(json.dumps(meta,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    if len(reports)<5:raise SystemExit("Missing reviewed annotations")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
