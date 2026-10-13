"""Research-only: infer near-orthogonal point-link direction from an operator A segment.

Inputs used by predictor: photo pixels and ONLY annotation.segments.reference.
check_same/holdout_same/check_cross/check_cross_second are held out for scoring.
No photo-length calibration, no physical yarn counts, no yarn-identity assertion.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import cv2
import numpy as np
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[1]
BATCH = "U20261013_"
MAX_ROI = 720


def axis_deg(segment):
    a, b = np.asarray(segment, dtype=float)
    return float(np.degrees(np.arctan2(*(b-a)[::-1])) % 180)


def diff180(a, b):
    return float(abs((a - b + 90) % 180 - 90))


def get_roi(img, ref_segment, side=MAX_ROI):
    """Deterministic source-pixel square. No held-out cross coordinates used."""
    h, w = img.shape[:2]
    s = min(side, h, w)
    cx, cy = np.asarray(ref_segment, float).mean(axis=0)
    x0 = int(np.clip(round(cx-s/2), 0, w-s))
    y0 = int(np.clip(round(cy-s/2), 0, h-s))
    return img[y0:y0+s, x0:x0+s].copy(), (x0, y0)


def points_from_pixels(bgr):
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)[:, :, 0].astype(np.float32)
    micro = cv2.GaussianBlur(gray, (0,0), 1.0) - cv2.GaussianBlur(gray, (0,0), 10.0)
    positive = (micro > np.percentile(micro, 76)).astype(np.uint8)
    positive = cv2.morphologyEx(positive, cv2.MORPH_OPEN, np.ones((2,2),np.uint8))
    n, lab, stats, centers = cv2.connectedComponentsWithStats(positive, 8)
    spots = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if (6 <= area <= 250 and 2 <= w <= 55 and 2 <= h <= 55
                and 0.16 <= w/max(h,1) <= 6 and x > 4 and y > 4
                and x+w < bgr.shape[1]-4 and y+h < bgr.shape[0]-4):
            spots.append(centers[i])
    return np.asarray(spots, dtype=np.float32).reshape(-1, 2)


def tensor(bgr):
    lum = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)[:, :, 0].astype(np.float32)
    lum = cv2.GaussianBlur(lum, (0,0), 1.1)
    gx = cv2.Sobel(lum, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(lum, cv2.CV_32F, 0, 1, ksize=3)
    a = cv2.GaussianBlur(gx*gx, (0,0), 2.5)
    b = cv2.GaussianBlur(gy*gy, (0,0), 2.5)
    c = cv2.GaussianBlur(gx*gy, (0,0), 2.5)
    magnitude = a+b
    return a,b,c,float(np.median(magnitude[20:-20,20:-20]))


def aligned_at(a,b,c, baseline, x, y, direction):
    rad = np.radians(direction)
    u, v = np.cos(rad), np.sin(rad)
    normal_energy = a[y,x]*v*v+b[y,x]*u*u-2*c[y,x]*u*v
    tangent_energy = a[y,x]*u*u+b[y,x]*v*v+2*c[y,x]*u*v
    coherence = (normal_energy-tangent_energy)/(normal_energy+tangent_energy+1e-6)
    return (coherence > .20) & ((a[y,x]+b[y,x]) > .25*baseline)


def detect(bgr, first_deg):
    """A-family reference direction is a prior; neither B label enters here."""
    pts = points_from_pixels(bgr)
    ideal = (first_deg+90.) % 180
    output = dict(first_axis_deg=round(first_deg,3), ideal_cross_deg=round(ideal,3),
                  point_count=len(pts), pair_count=0, candidate_cross_deg=None,
                  linked_gap_count=0, supported_gap_count=0,
                  gap_support_fraction=0., long_chain_count=0,
                  status="ABSTAIN_IMAGE_EVIDENCE")
    if len(pts) < 30:
        return output,pts,np.empty((0,2),np.int32)
    pairs = np.asarray(sorted(cKDTree(pts).query_pairs(r=70)), np.int32).reshape(-1,2)
    if not len(pairs):
        return output,pts,pairs
    vec = pts[pairs[:,1]]-pts[pairs[:,0]]
    length = np.linalg.norm(vec,axis=1)
    angle = np.degrees(np.arctan2(vec[:,1],vec[:,0])) % 180
    off = (angle-ideal+90)%180-90
    near = (length>=13)&(length<=65)&(np.abs(off)<=24)
    pairs, length, off = pairs[near],length[near],off[near]
    output["pair_count"] = int(len(pairs))
    if len(pairs)<30:
        return output,pts,np.empty((0,2),np.int32)
    a,b,c,base=tensor(bgr)
    centers = np.rint((pts[pairs[:,0]]+pts[pairs[:,1]])/2).astype(int)
    x = np.clip(centers[:,0], 3,bgr.shape[1]-4)
    y = np.clip(centers[:,1], 3,bgr.shape[0]-4)
    # Direction is evaluated on BETWEEN-point image pixels, not spot positions.
    choices=[]
    for shift in range(-22,23,2):
        belongs=np.abs(off-shift)<=3.0
        if np.sum(belongs)<12:
            continue
        supported=aligned_at(a,b,c,base,x[belongs],y[belongs],(ideal+shift)%180)
        evidence=int(np.count_nonzero(supported))
        # Scores prefer independent physical structure, not merely many collinear dots.
        score=evidence / max(np.sqrt(len(pts)),1)
        choices.append((score, evidence, int(np.sum(belongs)), shift, belongs, supported))
    if not choices:
        return output,pts,np.empty((0,2),np.int32)
    best=max(choices,key=lambda z:(z[0],z[1],-abs(z[3])))
    score,evidence,count,shift,belongs,supported=best
    good_edges=pairs[belongs][supported]
    fraction=evidence/max(count,1)
    output.update(candidate_cross_deg=round(float((ideal+shift)%180),3),
                  linked_gap_count=count,supported_gap_count=evidence,
                  gap_support_fraction=round(float(fraction),4))
    # Simple spatially independent chain indication; does NOT confer yarn identity.
    uu=np.asarray([np.cos(np.radians(ideal+shift)),np.sin(np.radians(ideal+shift))])
    if len(good_edges):
        adjacency={}
        for i,j in good_edges:
            adjacency.setdefault(int(i),set()).add(int(j))
            adjacency.setdefault(int(j),set()).add(int(i))
        unseen=set(adjacency); spans=[]
        while unseen:
            root=unseen.pop(); component={root}; frontier=[root]
            while frontier:
                for k in adjacency.get(frontier.pop(),()):
                    if k not in component:
                        component.add(k); unseen.discard(k);frontier.append(k)
            spans.append(np.ptp(pts[list(component)]@uu))
        output["long_chain_count"]=int(sum(s>=90 for s in spans))
    if (evidence>=35 and fraction>=.55 and output["long_chain_count"]>=3
            and abs(shift)<20):
        output["status"]="IMAGE_SUPPORTED_DIRECTION_ONLY_NOT_YARN_PROOF"
    return output,pts,good_edges


def pitch_from_manual(a,b,angle,intervals):
    """Operator interval counts are calibration evidence, not independent GT."""
    if intervals is None or int(intervals)<=0:return None
    u=np.radians(angle)
    n=np.asarray([-np.sin(u),np.cos(u)])
    distance=abs(float((np.asarray(b,float).mean(axis=0)-
                        np.asarray(a,float).mean(axis=0))@n))
    return round(distance/int(intervals),3)


def draw_panel(img, pts, edges, annotation, offset, out):
    left=img.copy()
    for i,j in edges:
        aa=tuple(np.rint(pts[i]).astype(int));bb=tuple(np.rint(pts[j]).astype(int))
        cv2.line(left,aa,bb,(50,220,70),1,cv2.LINE_AA)
    for p in pts:
        cv2.circle(left,tuple(np.rint(p).astype(int)),2,(0,180,255),-1)
    right=img.copy()
    colors={"reference":(0,230,255),"check_same":(255,230,0),
            "holdout_same":(255,0,255),
            "check_cross":(80,80,255),"check_cross_second":(80,255,255)}
    for role,color in colors.items():
        seg=annotation["segments"].get(role)
        if seg:
            a=np.rint(np.asarray(seg)-offset).astype(int)
            cv2.line(right,tuple(a[0]),tuple(a[1]),color,3,cv2.LINE_AA)
    both=np.hstack([left,right])
    caption=np.full((32,both.shape[1],3),22,dtype=np.uint8)
    cv2.putText(caption,"LEFT: image candidates (NOT physical yarn IDs)    RIGHT: held-out operator checks",
                (8,21),cv2.FONT_HERSHEY_SIMPLEX,.52,(255,255,255),1,cv2.LINE_AA)
    out.parent.mkdir(parents=True,exist_ok=True)
    cv2.imwrite(str(out),np.vstack([caption,both]))


def run_sample(root, ann_file, out):
    from benchmark.manual_annotation import validate_annotation
    ann=validate_annotation(root,json.loads(ann_file.read_text(encoding="utf-8")))
    if ann.get("review_state")!="OPERATOR_REVIEWED" or not ann.get("reference_confirmed"):
        return None
    raw=(root/ann["image_path"]).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=ann["image_sha256"]:
        raise ValueError("Image hash mismatch for "+ann["sample_id"])
    img=cv2.imdecode(np.frombuffer(raw,np.uint8),cv2.IMREAD_COLOR)
    if img is None or list(img.shape[1::-1])!=[ann["image_width"],ann["image_height"]]:
        raise ValueError("Native zoom image dimensions mismatch")
    reference=ann["segments"]["reference"]
    roi,origin=get_roi(img,reference)
    pred,spots,edges=detect(roi,axis_deg(reference))
    # Run same detector after exact 90-degree rotation; no change to calibration.
    rotated=cv2.rotate(roi,cv2.ROTATE_90_CLOCKWISE)
    rp,_,_=detect(rotated,(axis_deg(reference)+90)%180)
    angular_drift=(diff180(pred["candidate_cross_deg"],
                        (rp["candidate_cross_deg"]-90)%180)
                   if pred["candidate_cross_deg"] is not None
                   and rp["candidate_cross_deg"] is not None else None)
    cross=[ann["segments"].get("check_cross"),ann["segments"].get("check_cross_second")]
    manual_axes=[round(axis_deg(x),3) if x else None for x in cross]
    manual_pitch_a=pitch_from_manual(reference,ann["segments"]["check_same"],
                  axis_deg(reference),ann.get("same_family_intervals"))
    manual_pitch_b=(pitch_from_manual(cross[0],cross[1],manual_axes[0],
                    ann.get("cross_family_intervals")) if all(cross) else None)
    errors=[round(diff180(pred["candidate_cross_deg"],v),3)
            if pred["candidate_cross_deg"] is not None and v is not None else None
            for v in manual_axes]
    if pred["status"].startswith("IMAGE_SUPPORTED") and angular_drift is not None and angular_drift>3:
        pred["status"]="ABSTAIN_ROTATION_INCONSISTENCY"
    result={"sample_id":ann["sample_id"],"source_sha256":ann["image_sha256"],
            "coordinate_space":ann["coordinate_space"],
            "input_roles":["reference"],
            "heldout_roles":["check_same","holdout_same","check_cross","check_cross_second"],
            "first_reference_deg":round(axis_deg(reference),3),
            "heldout_same_error_deg":round(diff180(axis_deg(reference),
                                           axis_deg(ann["segments"]["holdout_same"])),3),
            "manual_cross_axes_deg":manual_axes,
            "manual_cross_internal_disagreement_deg":round(diff180(*manual_axes),3)
                if all(v is not None for v in manual_axes) else None,
            "manual_a_pitch_px_per_interval":manual_pitch_a,
            "manual_b_pitch_px_per_interval":manual_pitch_b,
            "candidate_vs_cross_heldout_error_deg":errors,
            "rotation_90_reprojected_drift_deg":round(angular_drift,3) if angular_drift is not None else None,
            "photo_physical_scale_available":False,
            "physical_yarn_identity_verified":False,
            "root_per_cm_evaluable":False,
            "detector":pred}
    draw_panel(roi,spots,edges,ann,origin,out/(ann["sample_id"]+".jpg"))
    return result


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("--root",type=Path,default=ROOT)
    parser.add_argument("--out",type=Path,default=Path("experiments/orthogonal-new-reviewed"))
    args=parser.parse_args(argv)
    root=args.root.resolve(); out=args.out if args.out.is_absolute() else root/args.out
    out.mkdir(parents=True,exist_ok=True)
    anns=sorted((root/"datasets/annotations/drafts").glob(BATCH+"*.json"))
    results=[]
    for path in anns:
        row=run_sample(root,path,out)
        if row:
            results.append(row)
            d=row["detector"]
            print(f'{row["sample_id"]}: {d["status"]} candidate={d["candidate_cross_deg"]} '
                  f'heldout_error={row["candidate_vs_cross_heldout_error_deg"]} '
                  f'rotation_drift={row["rotation_90_reprojected_drift_deg"]}',flush=True)
    # Negative control: textured dots without yarns must never be physical success.
    rng=np.random.default_rng(20261013)
    dots=np.full((500,500,3),95,dtype=np.uint8)
    for x,y in rng.integers(10,490,size=(180,2)):
        cv2.circle(dots,(int(x),int(y)),3,(190,190,190),-1)
    neg,_,_=detect(dots,0.)
    negative_ok=not neg["status"].startswith("IMAGE_SUPPORTED")
    report={"main_source_sha":"e1b219384224e1d77c79aa108bef3fb51a39ea56",
            "samples_evaluated":len(results),"results":results,
            "synthetic_no_yarn_negative":{"rejected":negative_ok,"detector":neg},
            "conclusion":"Directional candidate audit only; no yarn identity or physical density validated."}
    (out/"summary.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    if not negative_ok:raise SystemExit("FAIL: synthetic no-yarn negative accepted")
    if len(results)<5:raise SystemExit("FAIL: missing newly reviewed annotations")
    print("SUMMARY evaluated",len(results)," negative rejected",negative_ok,flush=True)
    return 0


if __name__=="__main__":
    raise SystemExit(main())
