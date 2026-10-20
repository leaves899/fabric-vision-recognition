from __future__ import annotations
"""Seven-cross-section, *tile-local* yarn track candidates from native R/T pixels.

Neither GT IDs nor known weave, density, synthetic seed, or synthetic camera
parameters enter this module. It is a falsifiable alternative to publishing
one straight line across a complex woven patch from one central cross-section.

A track ID is LOCAL and tentative. It does not assert global physical identity
or prove that the material remains visible beneath an interlacing occlusion.
"""
from dataclasses import dataclass
import cv2
import numpy as np
from .subpixel_physical_phase import (
    validate_centers_fractional, _phase_ranking, _phase_distance)


@dataclass(frozen=True)
class TrackSettings:
    slices: int = 7
    min_support_slices: int = 5
    max_phase_step_fraction: float = .25
    max_anchor_drift_fraction: float = .34
    min_core_width_px: float = 12.


def _coords_at_slice(family, along, position):
    return [float(position),float(along)] if family == "warp" else [float(along),float(position)]


def trace_local_yarns(Rpatch,Tpatch,family,initial_pitch,settings=TrackSettings()):
    if family not in ("warp","weft"):
        raise ValueError("BAD_YARN_FAMILY")
    if Rpatch.shape != Tpatch.shape or len(Rpatch.shape)!=3:
        raise ValueError("RT_TILE_MISMATCH")
    if settings.slices<5 or settings.slices%2==0 or settings.min_support_slices>settings.slices:
        raise ValueError("INVALID_SLICE_SPEC")
    base=validate_centers_fractional(Rpatch,Tpatch,family,initial_pitch)
    if base.get("status")!="PASS":
        return {"status":"LOW_CONFIDENCE","reason":"BASE_ENTITY_UNVERIFIED",
                "base_status":base.get("status"),"base_reason":base.get("reason"),
                "tracks":[],"slices":[]}
    pitch=float(base["pitch_px"])
    along_axis=0 if family=="warp" else 1
    n=Rpatch.shape[along_axis]
    normal_n=Rpatch.shape[1-along_axis]
    if n<settings.slices*24:
        return {"status":"UNDETERMINED","reason":"LONGITUDINAL_TILE_TOO_SHORT","tracks":[]}
    gray_r=cv2.cvtColor(Rpatch,cv2.COLOR_BGR2GRAY)
    gray_t=cv2.cvtColor(Tpatch,cv2.COLOR_BGR2GRAY)
    bands=np.array_split(np.arange(n),settings.slices)
    anchor=float(base["phase_px"])
    current=anchor
    observations=[]
    for index,band in enumerate(bands):
        rr=np.median(np.take(gray_r,band,axis=along_axis),axis=along_axis)
        tt=np.median(np.take(gray_t,band,axis=along_axis),axis=along_axis)
        ranked=_phase_ranking(rr,tt,pitch)
        compatible=[v for v in ranked
                    if v["R_polarity"]==base["R_center_polarity"]
                    and v["T_polarity"]==base["T_center_polarity"]
                    and v["RT_support"]>=.24
                    and v["width_fraction"]*pitch>=settings.min_core_width_px
                    and _phase_distance(v["phase_px"],anchor,pitch) <=
                        settings.max_anchor_drift_fraction*pitch]
        # Look for a phase supported by photons AND consistent with the
        # previously observed slice, not a center invented by interpolation.
        near=[v for v in compatible if
              _phase_distance(v["phase_px"],current,pitch) <= settings.max_phase_step_fraction*pitch]
        decision=max(near,key=lambda q:q["score"]) if near else None
        # Refuse an unambiguous *different* optical entity even if it lies
        # nearby; a meaningful rival here warrants abstention, not a forced link.
        winner=ranked[0] if ranked else None
        if decision and winner and winner["score"]-decision["score"]>.09:
            decision=None
        along=float(np.mean(band))
        if decision:
            phase=float(decision["phase_px"])
            # unwrap to a continuous non-modular coordinate for the local
            # residual, so the same k labels the same tentative yarn.
            delta=(phase-anchor+pitch/2)%pitch-pitch/2
            unwrapped=anchor+delta
            current=phase
            observations.append({"slice":index,"along_px":round(along,3),
                "status":"PASS","phase_px":round(phase,4),
                "unwrapped_phase_px":round(unwrapped,4),
                "optical_phase_support":round(float(decision["score"]),4),
                "width_fraction":decision["width_fraction"]})
        else:
            observations.append({"slice":index,"along_px":round(along,3),
                "status":"LOW_CONFIDENCE","reason":"LOCAL_PHASE_OR_POLARITY_CONFLICT"})
    valid=[r for r in observations if r["status"]=="PASS"]
    global_status="PASS" if len(valid)>=settings.min_support_slices else "LOW_CONFIDENCE"
    if len(valid)<2:
        global_status="LOW_CONFIDENCE"
    max_jump=0.
    for left,right in zip(valid,valid[1:]):
        jump=abs(right["unwrapped_phase_px"]-left["unwrapped_phase_px"])
        max_jump=max(max_jump,jump)
        if jump>settings.max_phase_step_fraction*pitch * (right["slice"]-left["slice"]):
            global_status="LOW_CONFIDENCE"
    # Tracks occupy ordered non-overlapping local pitch lanes, never linked
    # across independent 8k windows based on texture resemblance.
    tracks=[]
    kmin=int(np.floor(-anchor/pitch))-1
    kmax=int(np.ceil((normal_n-anchor)/pitch))+1
    for k in range(kmin,kmax+1):
        points=[]
        for r in valid:
            normal=r["unwrapped_phase_px"]+k*pitch
            if .50*pitch<=normal<normal_n-.50*pitch:
                points.append(_coords_at_slice(family,r["along_px"],normal))
        if len(points)<settings.min_support_slices:
            continue
        tracks.append({"track_id":f"{family}_local_{k:+d}",
           "points":np.round(points,3).tolist(),"observed_slices":len(points),
           "status":"CANDIDATE_ONLY"})
    if not tracks:
        global_status="LOW_CONFIDENCE"
    reason=("LONGITUDINAL_ENTITY_EVIDENCE_CANDIDATE_ONLY" if global_status=="PASS"
            else "STRIP_ENTITY_PHASE_INCONSISTENT")
    return {"status":global_status,"reason":reason,
      "pitch_px":pitch,"anchor_phase_px":anchor,"max_step_px":round(float(max_jump),3),
      "passing_slices":len(valid),"total_slices":settings.slices,
      "R_center_polarity":base["R_center_polarity"],
      "T_center_polarity":base["T_center_polarity"],
      "slices":observations,"tracks":tracks if global_status=="PASS" else [],
      "limitations":["TILE_LOCAL_ID_ONLY","NO_GLOBAL_CROSS_WINDOW_LINK",
                     "VISIBLE_PHYSICAL_FIBRE_CONTINUITY_NOT_PROVEN"]}
