"""Direction-guided, IMAGE-ONLY first-family yarn location HYPOTHESES.

A user annotation is an INFERRED CONNECTION DIRECTION, not visible strand pixels.
Consequently its coordinate POSITION MUST NOT be used to pick a ridge appearance,
grid phase, centerline, or spacing. The angle alone constrains orientation.
All output center lines are UNVERIFIED CANDIDATES; no pixel-level GT exists yet.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import cv2
import numpy as np
from scipy.signal import find_peaks

from benchmark.first_yarn_evidence import axis_deg, rectify_axis, oriented_ridge

ROOT=Path(__file__).resolve().parents[1]
SCALES=(3,5,8,12,17)
MIN_WINDOWS=3


def central_native_crop(img, side=1100, center_xy=None):
    h,w=img.shape[:2]
    n=min(h,w,side)
    if center_xy is None:
        center_xy=(w/2,h/2)
    x=int(np.clip(round(center_xy[0]-n/2),0,w-n))
    y=int(np.clip(round(center_xy[1]-n/2),0,h-n))
    return img[y:y+n,x:x+n].copy(),(x,y)


def synthetic_direction_line(shape, direction_deg):
    """Use angle only; line passes through fixed IMAGE center, not user's point."""
    h,w=shape[:2]
    a=np.deg2rad(direction_deg)
    u=np.array([np.cos(a),np.sin(a)],dtype=float)
    center=np.array([w/2,h/2],dtype=float)
    step=min(w,h)*.32
    return np.asarray([center-step*u,center+step*u],dtype=float)


def score_profile(img, orientation_deg, *, approximate_roi_center=None):
    # Approximate user path may select the FIELD OF VIEW; it does not set
    # appearance, line center, peak phase, or image texture scale.
    crop,xy0=central_native_crop(img,center_xy=approximate_roi_center)
    virtual=synthetic_direction_line(crop.shape,orientation_deg)
    rotated,m,_=rectify_axis(crop,virtual.tolist())
    lab=cv2.cvtColor(rotated,cv2.COLOR_BGR2LAB).astype(np.float32)
    h,w=rotated.shape[:2]
    xs=[(int(w*(.18+i*.12)),int(w*(.32+i*.12))) for i in range(5)]
    outputs=[]
    for channel_id,channel in (("L",lab[:,:,0]),("blue_yellow",lab[:,:,2])):
        for scale in SCALES:
            raw=oriented_ridge(channel,scale)
            disp=float(np.percentile(np.abs(raw-np.median(raw)),75))
            if disp<.3:continue
            for sign in (-1,1):
                response=raw*sign/max(disp,.3)
                windows=np.stack([np.median(response[:,a:b],axis=1)
                                  for a,b in xs])
                mean_profile=np.median(windows,axis=0)
                distance=max(6,round(scale*1.45))
                prominence=max(.30, .42*float(np.std(mean_profile)))
                peaks,_=find_peaks(mean_profile,distance=distance,prominence=prominence)
                if not len(peaks):continue
                accepted=[]
                for y in peaks:
                    count=0
                    for window in windows:
                        local,_=find_peaks(window,distance=distance,
                                           prominence=max(.25, .35*float(np.std(window))))
                        if len(local) and np.min(abs(local-y))<=max(3,round(scale*.75)):
                            count+=1
                    if count>=MIN_WINDOWS and mean_profile[y]>=.12:
                        accepted.append((int(y),int(count),round(float(mean_profile[y]),3)))
                if not accepted:continue
                strength=sum(n*(max(.1,amp)) for _,n,amp in accepted)
                # No human target position or interval used to select configuration.
                candidate_quality=float(strength)/(max(8,len(peaks))*5)
                outputs.append((candidate_quality,len(accepted),channel_id,scale,sign,accepted))
    result={"status":"ABSTAIN_NO_CONSISTENT_IMAGE_RIDGES",
            "direction_deg_from_operator":round(orientation_deg,3),
            "image_crop_source_xy":list(xy0),
            "physical_yarn_centers_verified":False,
            "actual_yarn_count_verified":False,
            "pixel_pitch_verified":False,
            "visual_only_hypotheses":True}
    if not outputs:
        return result,None
    best=max(outputs,key=lambda x:(x[0],x[1]))
    quality,count,channel,scale,sign,peaks=best
    ycoords=[p[0] for p in peaks]
    # A regular set of texture ridges may also pass; we do NOT call it a yarn grid.
    result.update(status="IMAGE_TEXTURE_RIDGE_CANDIDATES_REQUIRE_YARN_CONFIRMATION",
                  image_support_score=round(quality,4), selected_channel=channel,
                  selected_polarity="light" if sign>0 else "dark",
                  selected_cross_scale_px=scale,
                  candidate_positions_rotated_y=ycoords,
                  image_only_candidate_ridge_count=len(ycoords),
                  repeated_window_support_count=[p[1] for p in peaks],
                  warning="These candidates may be twill texture or gaps; NOT verified physical yarns.")
    return result,(rotated,ycoords,m,np.asarray(xy0,float))


def render(img,original_reference,proposal,visual,out):
    original=cv2.resize(img,(600,600),interpolation=cv2.INTER_AREA)
    candidate=np.zeros_like(original)
    if visual is not None:
        rotated,ys,_,_=visual
        overlay=rotated.copy()
        for y in ys:
            cv2.line(overlay,(0,int(y)),(overlay.shape[1]-1,int(y)),(0,215,65),2,cv2.LINE_AA)
        candidate=cv2.resize(overlay,(600,600),interpolation=cv2.INTER_AREA)
    top=np.full((48,1200,3),24,dtype=np.uint8)
    cv2.putText(top,"LEFT: original zoom crop (overview)    RIGHT: unverified image-only ridges",
                (12,30),cv2.FONT_HERSHEY_SIMPLEX,.65,(240,240,240),1,cv2.LINE_AA)
    out.parent.mkdir(parents=True,exist_ok=True)
    cv2.imwrite(str(out),np.vstack([top,np.hstack([original,candidate])]))


def run(root,out):
    from benchmark.manual_annotation import validate_annotation
    out.mkdir(parents=True,exist_ok=True)
    data=[]
    for path in sorted((root/"datasets/annotations/drafts").glob("U20261013_*.json")):
        ann=validate_annotation(root,json.loads(path.read_text(encoding="utf-8")))
        if ann["review_state"]!="OPERATOR_REVIEWED":continue
        source=(root/ann["image_path"]).read_bytes()
        if hashlib.sha256(source).hexdigest()!=ann["image_sha256"]:
            raise RuntimeError("stale annotated image hash")
        img=cv2.imdecode(np.frombuffer(source,np.uint8),cv2.IMREAD_COLOR)
        if img is None or img.shape[1]!=ann["image_width"] or img.shape[0]!=ann["image_height"]:
            raise RuntimeError("annotation coordinate image does not match")
        angle=axis_deg(ann["segments"]["reference"])
        proposal,visual=score_profile(img,angle)
        proposal.update(sample_id=ann["sample_id"],
                        annotation_semantics="INFERRED_YARN_CONNECTION_DIRECTION_ONLY",
                        annotation_coordinates_used_to_fit_center=False,
                        input_fields=["image","reference orientation angle"],
                        no_independent_physical_center_gt=True)
        data.append(proposal)
        render(img,ann["segments"]["reference"],proposal,visual,
               out/(ann["sample_id"]+".jpg"))
        print(f'{ann["sample_id"]} {proposal["status"]} '
              f'ridges={proposal.get("image_only_candidate_ridge_count",0)}',flush=True)
    (out/"summary.json").write_text(json.dumps({"source_main_sha":"e1b219384224e1d77c79aa108bef3fb51a39ea56",
        "dataset_semantics":"OPERATOR_DRAWN_DIRECTION_GUIDES_NOT_VISIBLE_YARN_SEGMENTS",
        "reviewed":len(data),"results":data,
        "accuracy_evaluable":False,"physical_yarn_count_evaluable":False,
        "caution":"Do not score photo candidate center accuracy against direction guides."},
        ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    if len(data)<5:raise SystemExit("Insufficient reviewed samples")
    return 0


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=ROOT)
    p.add_argument("--out",type=Path,default=Path("experiments/first-yarn-direction-only"))
    args=p.parse_args()
    root=args.root.resolve()
    out=args.out if args.out.is_absolute() else root/args.out
    return run(root,out)


if __name__=="__main__":
    raise SystemExit(main())
