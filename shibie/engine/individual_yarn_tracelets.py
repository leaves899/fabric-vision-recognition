from __future__ import annotations
"""Independent *per-yarn* short-range image evidence tracking in native R/T tiles.

The old 7-strip model applies one phase offset to every yarn; this alternative
allows separate, locally supported movement per yarn, while enforcing a strict
same-family non-overlap/order exclusion. Neither synthetic GT nor known weave
or synthetic curvature is input. Track IDs are provisional within one tile.
"""
from dataclasses import dataclass
import cv2
import numpy as np
from scipy.ndimage import gaussian_filter1d
from .subpixel_physical_phase import validate_centers_fractional


@dataclass(frozen=True)
class EntityTraceConfig:
    slices: int = 7
    longitudinal_min_slices: int = 5
    maximum_step_pitch_fraction: float = .34
    maximum_anchor_pitch_fraction: float = .47
    minimum_neighbor_fraction: float = .55
    optical_min_joint_contrast: float = .14


def _interpolate(values, xs):
    return np.interp(xs,np.arange(len(values),dtype=np.float64),values)


def _local_core_evidence(rprofile,tprofile,x,pitch,polarity):
    """Two-sided physical core-vs-pore signal, not texture energy alone."""
    px=np.asarray(x,float)
    flank=max(3.,.45*pitch)
    outputs=[]
    for profile,sign in ((rprofile,polarity[0]),(tprofile,polarity[1])):
        c=_interpolate(profile,px)
        left=_interpolate(profile,px-flank)
        right=_interpolate(profile,px+flank)
        robust=max(float(np.percentile(profile,90)-np.percentile(profile,10)),8.)
        signed=sign*(c-(left+right)*.5)/robust
        imbalance=np.abs((c-left)-(c-right))/robust
        outputs.append((signed,imbalance))
    r,t=outputs
    # Weak modality can be occluded at one crossing. However the two
    # independently observed optical signs must not be strongly contradictory.
    combined=.45*r[0]+.55*t[0]-.045*(r[1]+t[1])
    return combined,r[0],t[0]


def _best_individual_center(rprofile,tprofile,predicted,anchor,pitch,polarity,config):
    half_width=.5*pitch
    dx=np.arange(-config.maximum_step_pitch_fraction*pitch,
                 config.maximum_step_pitch_fraction*pitch+.001,.5)
    xs=float(predicted)+dx
    permissible=(xs>half_width)&(xs<len(rprofile)-half_width)&(
        np.abs(xs-anchor)<=config.maximum_anchor_pitch_fraction*pitch)
    xs=xs[permissible]
    if not len(xs):
        return None
    combined,r,t=_local_core_evidence(rprofile,tprofile,xs,pitch,polarity)
    # Weak smoothness prior independent of GT; avoid jumping across a gap.
    score=combined-.07*((xs-predicted)/pitch)**2
    if len(score)==0:return None
    idx=int(np.argmax(score))
    if (combined[idx]<config.optical_min_joint_contrast or
        (r[idx]<-.2 and t[idx]<-.2)):
        return None
    return {"normal_px":float(xs[idx]),"score":float(score[idx]),
            "R_support":float(r[idx]),"T_support":float(t[idx])}


def trace_individual_entities(Rpatch,Tpatch,family,initial_pitch,
                              config=EntityTraceConfig()):
    if family not in ("warp","weft"):raise ValueError("UNKNOWN_YARN_FAMILY")
    if Rpatch.shape!=Tpatch.shape or Rpatch.ndim!=3:
        raise ValueError("RT_PATCH_MISMATCH")
    if config.slices<5 or config.slices%2==0:
        raise ValueError("SLICE_COUNT_MUST_BE_ODD_AT_LEAST_FIVE")
    base=validate_centers_fractional(Rpatch,Tpatch,family,initial_pitch)
    if base.get("status")!="PASS":
        return {"status":"LOW_CONFIDENCE","reason":"BASE_PHASE_UNVERIFIED",
                "tracks":[],"base_reason":base.get("reason")}
    pitch=float(base["pitch_px"])
    polarity=(int(base["R_center_polarity"]),int(base["T_center_polarity"]))
    along_axis=0 if family=="warp" else 1
    nr=Rpatch.shape[1-along_axis]
    n=Rpatch.shape[along_axis]
    if n<config.slices*24:
        return {"status":"UNDETERMINED","reason":"TOO_SHORT_FOR_INDEPENDENT_SLICES","tracks":[]}
    r=cv2.cvtColor(Rpatch,cv2.COLOR_BGR2GRAY)
    t=cv2.cvtColor(Tpatch,cv2.COLOR_BGR2GRAY)
    sections=[]
    for band in np.array_split(np.arange(n),config.slices):
        rr=gaussian_filter1d(np.median(np.take(r,band,axis=along_axis),axis=along_axis),
                            1.0).astype(float)
        tt=gaussian_filter1d(np.median(np.take(t,band,axis=along_axis),axis=along_axis),
                            1.0).astype(float)
        sections.append({"along":float(np.mean(band)),"R":rr,"T":tt})
    seeds=[float(c) for c in base["center_positions_px"]]
    # Each yarn has its own variable x(y), unlike global common-phase tracking.
    middle=config.slices//2
    points={k:{} for k in range(len(seeds))}
    rejected={"optical":0,"order":0}
    for k,seed in enumerate(seeds):
        # Both directions propagate outward from a single central observation.
        sec=sections[middle]
        start=_best_individual_center(sec["R"],sec["T"],seed,seed,pitch,polarity,config)
        if start is None:
            rejected["optical"]+=1
            continue
        points[k][middle]=start["normal_px"]
        for direction in (-1,1):
            previous=start["normal_px"]
            for j in range(middle+direction,config.slices if direction>0 else -1,direction):
                sec=sections[j]
                obs=_best_individual_center(sec["R"],sec["T"],previous,seed,pitch,polarity,config)
                if obs is None:
                    rejected["optical"]+=1
                    break
                points[k][j]=obs["normal_px"]
                previous=obs["normal_px"]
    # Exhaustive per-slice local neighbour exclusion. If two physical threads
    # compete for the same core, reject BOTH competing tracks rather than
    # pick a winner from an arbitrary process order.
    conflict=set()
    for j in range(config.slices):
        observed=sorted((coords[j],k) for k,coords in points.items() if j in coords)
        for (xa,ka),(xb,kb) in zip(observed,observed[1:]):
            if xb-xa < config.minimum_neighbor_fraction*pitch or ka>=kb:
                conflict.add(ka);conflict.add(kb)
    rejected["order"]=len(conflict)
    tracks=[]
    for k,loc in points.items():
        if k in conflict or len(loc)<config.longitudinal_min_slices:
            continue
        pointlist=[]
        for j,normal in sorted(loc.items()):
            along=sections[j]["along"]
            xy=[float(normal),float(along)] if family=="warp" else [float(along),float(normal)]
            pointlist.append([round(a,3) for a in xy])
        tracks.append({"track_id":f"{family}_individual_{k}",
             "points":pointlist,"observed_slices":len(loc),
             "status":"CANDIDATE_ONLY"})
    status="PASS" if tracks else "LOW_CONFIDENCE"
    return {"status":status,"reason":"INDEPENDENT_OPTICAL_CORE_TRACKLETS_NOT_GLOBAL_ID" if tracks
            else "NO_UNAMBIGUOUS_INDEPENDENT_ENTITY_TRACKLETS",
            "pitch_px":pitch,
            "R_polarity":polarity[0],"T_polarity":polarity[1],
            "total_seeds":len(seeds),"published_tracks":len(tracks),
            "rejections":rejected,"slices":config.slices,
            "tracks":tracks,"limitations":["TILE_LOCAL_TENTATIVE_ID",
                 "PER_CORE_OPTICAL_EVIDENCE_MAY_FAIL_UNDER_OCCLUSION",
                 "NO_REAL_IMAGE_VALIDATION_YET"]}
