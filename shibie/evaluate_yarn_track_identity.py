from __future__ import annotations
"""Independent physical yarn-ID trajectory evaluator, post-inference ONLY.

This is stronger than one cross-section centre F1: a predicted local track must
stay near ONE SAME ground-truth yarn ID over multiple spaced cross-sections.
Labels are never input to tracking. We report missing/extra tracks, matched
cross-section coverage, and potential identity switches separately.

This is not pixel-level visibility/occlusion coverage, and a tile ID does not
prove global identity across the full 50mm sample.
"""
import cv2
import numpy as np
from scipy.optimize import linear_sum_assignment


def projected_truth_curves(raw_truth, family, raw_to_tile, side=520,
                           slice_alongs=None, min_eligible_slices=5):
    along_axis=1 if family=="warp" else 0
    normal_axis=1-along_axis
    if slice_alongs is None:
        slice_alongs=np.linspace(40,side-40,7)
    out=[]
    for yarn in raw_truth["physical_yarn_centerlines"][family]:
        pts=np.asarray(yarn["points"],np.float32)
        projected=cv2.perspectiveTransform(pts[None],np.asarray(raw_to_tile,np.float64))[0]
        order=np.argsort(projected[:,along_axis])
        u=projected[order,along_axis]
        v=projected[order,normal_axis]
        unique=np.r_[True,np.diff(u)>1.e-6]
        u=u[unique];v=v[unique]
        if len(u)<2:continue
        supports={}
        for j,along in enumerate(slice_alongs):
            if along<u[0] or along>u[-1]:continue
            normal=float(np.interp(along,u,v))
            if 0<=normal<side:
                supports[j]=normal
        if len(supports)>=min_eligible_slices:
            out.append({"id":str(yarn["id"]),"positions_by_slice":supports,
                        "sampled_points_in_tile":np.round(projected,2).tolist()})
    return out


def straight_candidate_tracks(candidate, family, slice_alongs):
    """Fair frozen prior baseline: its actual returned centres, not a GT fit."""
    if candidate.get("status")!="PASS":
        return []
    tracks=[]
    for i,c in enumerate(candidate.get("center_positions_px",[])):
        points=[]
        for u in slice_alongs:
            pt=[float(c),float(u)] if family=="warp" else [float(u),float(c)]
            points.append(pt)
        tracks.append({"track_id":f"baseline_{i}","points":points,
                       "observed_slices":len(points),"status":"CANDIDATE_ONLY"})
    return tracks


def _sample_truth(yarn, along, family):
    # Returns real yarn position at the requested along-yarn coordinate.
    normal_axis=0 if family=="warp" else 1
    along_axis=1-normal_axis
    pts=np.asarray(yarn["sampled_points_in_tile"],dtype=np.float64)
    order=np.argsort(pts[:,along_axis])
    u=pts[order,along_axis]
    v=pts[order,normal_axis]
    if along<u[0] or along>u[-1]:
        return None
    return float(np.interp(along,u,v))


def evaluate_local_tracks(tracks, real_entities, family, physical_pitch,
                          side=520, match_fraction=.32, minimum_span=.52):
    if family not in ("warp","weft"):
        raise ValueError("UNKNOWN_FAMILY")
    if not (.05<match_fraction<.5 and physical_pitch>0):
        raise ValueError("BAD_PHYSICAL_MATCH_THRESHOLD")
    n=len(tracks);m=len(real_entities)
    candidates=np.full((n,m),False)
    benefit=np.zeros((n,m),np.float64)
    diagnostics={}
    switches=0
    for i,track in enumerate(tracks):
        pts=np.asarray(track["points"],dtype=np.float64)
        if pts.ndim!=2 or pts.shape[1]!=2 or not np.isfinite(pts).all():
            raise ValueError("TRACK_POINTS_MUST_BE_FINITE_XY")
        along_axis=1 if family=="warp" else 0
        normal_axis=1-along_axis
        # Nearest truth ID across sampled points helps flag identity switching,
        # without treating the nearest match as proof of a physical entity.
        closest=[]
        for point in pts:
            near=[]
            for yarn in real_entities:
                normal=_sample_truth(yarn,point[along_axis],family)
                if normal is not None:
                    near.append((abs(normal-point[normal_axis]),yarn["id"]))
            if near:
                distance,id_=min(near)
                if distance<match_fraction*physical_pitch:
                    closest.append(id_)
        switches+=sum(a!=b for a,b in zip(closest,closest[1:]))
        for j,yarn in enumerate(real_entities):
            d=[]
            for point in pts:
                normal=_sample_truth(yarn,point[along_axis],family)
                if normal is not None and 0<=normal<side:
                    d.append(abs(normal-point[normal_axis]))
            if len(d)<3:continue
            good=np.asarray(d)<match_fraction*physical_pitch
            coverage=float(np.mean(good))
            span=float(np.ptp(pts[:,along_axis]))/side if len(pts)>1 else 0.
            if coverage>=.60 and int(np.sum(good))>=3 and span>=minimum_span:
                candidates[i,j]=True
                benefit[i,j]=coverage-.01*np.mean(np.asarray(d)/physical_pitch)
                diagnostics[(i,j)]={"covered_fraction_of_predicted_samples":round(coverage,4),
                  "longitudinal_span_fraction":round(span,4),
                  "mean_distance_fraction_pitch":round(float(np.mean(d)/physical_pitch),4),
                  "ground_truth_id":yarn["id"]}
    # Max cardinality on gated ID-compatible trajectory pairs. No global L1
    # assignment followed by thresholding (that bug was found last round).
    cost=np.zeros((n+m,n+m),dtype=np.float64)
    if n and m:cost[:n,:m]=np.where(candidates,.01*(1-benefit),3.)
    if n:cost[:n,m:]=1.
    if m:cost[n:,:m]=1.
    ii,jj=linear_sum_assignment(cost)
    matched=[(int(i),int(j)) for i,j in zip(ii,jj)
             if i<n and j<m and candidates[i,j]]
    recall=len(matched)/m if m else 0.
    precision=len(matched)/n if n else 0.
    return {"status":"EVALUATION_ONLY","f1":round(2*len(matched)/(n+m),4) if n+m else 0.,
            "precision":round(float(precision),4),"recall":round(float(recall),4),
            "matched_tracks":len(matched),"predicted_tracks":n,"real_physical_yarns":m,
            "nearest_gt_id_switches_unmatched_inclusive":int(switches),
            "matches":[{"candidate_id":tracks[i]["track_id"],**diagnostics[(i,j)]}
                       for i,j in matched],
            "missed_real_ids":[x["id"] for j,x in enumerate(real_entities)
                               if j not in {b for a,b in matched}],
            "unmatched_candidate_ids":[t["track_id"] for i,t in enumerate(tracks)
                                        if i not in {a for a,b in matched}],
            "notes":["TILE_IDENTITY_NOT_GLOBAL_FABRIC_IDENTITY",
                     "SAMPLED_GEOMETRIC_CONTINUITY_NOT_VISIBLE_OCCLUSION_COVERAGE"]}
