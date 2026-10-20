from __future__ import annotations
"""Local physical-centre phase tests without any assumed T light polarity.

Contrasting extrema are candidate yarns, not confirmed entities. Paired
boundary widths, R/T phase agreement, and continuity provide independent
observations. Indeterminate means no yarn overlay should be published.
"""
import math
import cv2
import numpy as np
from scipy.ndimage import gaussian_filter1d

def _folded_profile(signal,pitch):
    a=np.asarray(signal,np.float64)
    period=int(round(pitch))
    phase=np.arange(period)
    bins=[]
    for i in phase:
        samples=np.arange(i+period, len(a)-period,period)
        if len(samples)<4:
            bins.append(np.nan)
        else:
            bins.append(float(np.median(a[samples])))
    p=np.asarray(bins,float)
    if not np.isfinite(p).all():return None
    p=gaussian_filter1d(p,max(.65,pitch*.055),mode="wrap")
    return p

def _core_width(p,phase,polarity):
    n=len(p)
    # Folded unit cell: center is exactly phase. An adjacent half-cell is gap.
    center=float(p[phase])
    opposite=float(p[(phase+n//2)%n])
    diff=(center-opposite)*polarity
    if diff<=0:return 0.,0.
    thr=.5*(center+opposite)
    # Search each direction for the first half-height edge.
    edges=[]
    for sign in (-1,1):
        dist=0
        for j in range(1,n//2+1):
            test=(float(p[(phase+sign*j)%n])-thr)*polarity
            if test<=0:break
            dist=j
        edges.append(dist)
    return float(sum(edges))/n, float(diff)

def _rank_phases(r,t,pitch):
    fr=_folded_profile(r,pitch); ft=_folded_profile(t,pitch)
    if fr is None or ft is None:return []
    n=len(fr)
    norms=[max(float(np.percentile(x,95)-np.percentile(x,5)),2.0) for x in (fr,ft)]
    items=[]
    for phase in range(n):
        results=[]
        for p,norm in ((fr,norms[0]),(ft,norms[1])):
            options=[]
            for polarity in (-1,1):
                width,amp=_core_width(p,phase,polarity)
                if amp>0:options.append((width,amp/norm,polarity))
            results.append(max(options,key=lambda x:x[0]*x[1]) if options else (0,0,0))
        widths=[z[0] for z in results]
        strengths=[z[1] for z in results]
        # Exclude phases whose two-sided paired edge geometry is absent.
        coherence=min(strengths)/max(max(strengths),1e-6)
        occupancy=float(np.mean(widths))
        profile_support=float(np.mean(np.minimum(strengths,1.5)))
        width_support=max(0., min(1., (occupancy-.36)/.28))
        score=profile_support*(.34+.66*width_support)*(.60+.40*coherence)
        items.append({"phase_px":phase,"score":float(score),"width_fraction":round(occupancy,4),
              "modality_widths":[round(v,4) for v in widths],
              "R_polarity":results[0][2],"T_polarity":results[1][2],
              "RT_support":round(coherence,4)})
    return sorted(items,key=lambda x:x["score"],reverse=True)

def _positions_from_phase(profile_size,phase,pitch):
    pts=np.arange(float(phase),float(profile_size),float(pitch))
    return pts[(pts>=pitch*.7)&(pts<profile_size-pitch*.7)]

def validate_physical_centers(Rpatch,Tpatch,normal_family,pitch_px):
    """Validate candidates within one high-res rectified window.

    No ground-truth ID, weave, camera metadata or synthetic polarity is used.
    If there is no identifiable physical center, abstain instead of shifting by
    half a pitch based on an unverifiable bright/dark assumption.
    """
    if Rpatch.shape[:2]!=Tpatch.shape[:2]:
        raise ValueError("RT_SHAPE_MISMATCH")
    if normal_family not in ("warp","weft"):raise ValueError("UNKNOWN_FAMILY")
    if pitch_px is None or not (7<=pitch_px<=60):
        return {"status":"UNDETERMINED","reason":"PITCH_UNUSABLE"}
    axis=0 if normal_family=="warp" else 1
    r=cv2.cvtColor(Rpatch,cv2.COLOR_BGR2GRAY)
    t=cv2.cvtColor(Tpatch,cv2.COLOR_BGR2GRAY)
    rp=np.median(r,axis=axis)
    tp=np.median(t,axis=axis)
    candidates=_rank_phases(rp,tp,pitch_px)
    if not candidates:return {"status":"UNDETERMINED","reason":"NO_BILATERAL_EDGE_EVIDENCE"}
    top=candidates[0]
    pitch_round=int(round(pitch_px))
    alternate=[q for q in candidates if abs((q["phase_px"]-top["phase_px"])%pitch_round-pitch_round/2.)<pitch_round*.16]
    competitor=max(alternate,key=lambda q:q["score"]) if alternate else None
    margin=top["score"]-competitor["score"] if competitor else top["score"]
    width=top["width_fraction"]
    positions=_positions_from_phase(len(rp),top["phase_px"],pitch_round)
    status="PASS" if (width>=.50 and margin>=.06 and top["RT_support"]>=.24 and
                       len(positions)>=5) else "LOW_CONFIDENCE"
    reason= "BILATERAL_EDGE_AND_RT_CONSISTENCY" if status=="PASS" else "PHASE_OR_WIDTH_AMBIGUOUS"
    # Independent longitudinal check: 3 sections of SAME window. Do not
    # require center rigidly straight at subpixel scale.
    chunks=np.array_split(np.arange(r.shape[axis]),3)
    observed=[]
    for ix in chunks:
        rr=np.median(np.take(r,ix,axis=axis),axis=axis)
        tt=np.median(np.take(t,ix,axis=axis),axis=axis)
        variants=_rank_phases(rr,tt,pitch_round)
        if variants:
            ph=variants[0]["phase_px"]
            dx=abs((ph-top["phase_px"]+pitch_round/2)%pitch_round-pitch_round/2)
            observed.append(round(dx/pitch_round,4))
    max_phase_drift=max(observed) if observed else 1.
    if max_phase_drift>.26:
        status="LOW_CONFIDENCE";reason="LONGITUDINAL_PHASE_INCONSISTENT"
    return {"status":status,"reason":reason,"pitch_px":pitch_round,
       "phase_px":int(top["phase_px"]),"center_positions_px":np.round(positions,2).tolist(),
       "width_fraction":width,"relative_phase_margin":round(float(margin),4),
       "continuity_phase_drift_fraction":round(float(max_phase_drift),4),
       "R_center_polarity":top["R_polarity"],"T_center_polarity":top["T_polarity"],
       "alternative_phase_px":competitor["phase_px"] if competitor else None,
       "phase_candidates":candidates[:4]}
