from __future__ import annotations
"""Strict physical-ID trajectory scorer: post-inference only.

A track may score as a physical entity ONLY if almost every valid longitudinal
sample matches the SAME unique GT yarn ID and NONE matches another GT yarn.
The prior relaxed 60% correspondence metric is retained separately for audit;
its high F1 is not evidence of reliable identity across all sampled slices.
"""
import numpy as np
from scipy.optimize import linear_sum_assignment


def _nearest_truth_id(point, yarns, family, pitch, gate=.32):
    axis=1 if family=="warp" else 0
    normal=1-axis
    dist=[]
    for item in yarns:
        pts=np.asarray(item["sampled_points_in_tile"],float)
        coord=pts[:,axis]
        order=np.argsort(coord)
        u=coord[order];v=pts[order,normal]
        if not (u[0]<=point[axis]<=u[-1]):continue
        z=float(np.interp(point[axis],u,v))
        dist.append((abs(z-point[normal]),item["id"]))
    if not dist:return None
    d,ref=min(dist)
    return ref if d<gate*pitch else None


def strict_trajectory_id_match(tracks, real_entities, family, pitch_px,
                               max_missed_fraction=.15):
    if family not in ("warp","weft") or pitch_px<=0:
        raise ValueError("BAD_STRICT_TRAJECTORY_INPUT")
    n=len(tracks);m=len(real_entities)
    edges=np.zeros((n,m),np.bool_)
    distances=np.ones((n,m),np.float64)*3.
    switches=0;rejected=0
    for i,track in enumerate(tracks):
        pts=np.asarray(track["points"],dtype=np.float64)
        if pts.ndim!=2 or pts.shape[1]!=2 or not np.isfinite(pts).all():
            raise ValueError("MALFORMED_TRACK")
        along_axis=1 if family=="warp" else 0
        observed=[_nearest_truth_id(x,real_entities,family,pitch_px) for x in pts]
        certain=[r for r in observed if r is not None]
        switches+=sum(a!=b for a,b in zip(certain,certain[1:]))
        if len(pts)<5 or np.ptp(pts[:,along_axis])<.52*520:
            rejected+=1;continue
        # Any observed different physical entity is a veto regardless of
        # whether 60% of samples happened to align to the expected yarn.
        distinct=set(certain)
        if len(distinct)!=1:
            rejected+=1;continue
        winning=next(iter(distinct))
        fraction=observed.count(winning)/len(pts)
        if fraction<1.-max_missed_fraction:
            rejected+=1;continue
        j=next(k for k,x in enumerate(real_entities) if x["id"]==winning)
        edges[i,j]=True
        distances[i,j]=1.-fraction
    cost=np.zeros((n+m,n+m),float)
    if n and m:cost[:n,:m]=np.where(edges,.01*distances,3.)
    if n:cost[:n,m:]=1.
    if m:cost[n:,:m]=1.
    ii,jj=linear_sum_assignment(cost)
    pairs=[(int(i),int(j)) for i,j in zip(ii,jj) if i<n and j<m and edges[i,j]]
    hits=len(pairs)
    return {"f1":round(2*hits/(n+m),4) if n+m else 0.,
            "matched_physical_ids":hits,"proposed_tracks":n,"true_eligible_yarns":m,
            "single_id_violations_or_incomplete_tracks":rejected,
            "nearest_id_switch_events":switches,
            "matched_ids":[real_entities[j]["id"] for _,j in pairs],
            "definition":"ONE_GT_ID_85_PERCENT_AND_ZERO_OBSERVED_SWITCHES",
            "limit":"LOCAL_SAMPLED_ID_NOT_GROUND_TRUTH_VISIBILITY_UNDER_OCCLUSION"}
