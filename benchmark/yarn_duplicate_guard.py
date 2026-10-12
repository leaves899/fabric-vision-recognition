"""Conservative yarn-count alias guard for operator-verified physical spacing.

V6 previously aligned two positions while retaining every V4 candidate; a
single real yarn could therefore receive two candidate traces. Here an
operator must first confirm how many REAL yarn-to-yarn intervals separate two
marked distinct yarns. Only then may an over-dense candidate grid be reduced.
This is still a CANDIDATE lattice, not verified full-field yarn recognition.
"""
from __future__ import annotations
import math
import numpy as np
from benchmark.yarn_phase_anchor import normal_to_segment, median_distance


def _lines_by_normal(tracks, normal):
    rows=[]
    for index, track in enumerate(tracks):
        arr=np.asarray(track,dtype=float)
        if arr.ndim==2 and arr.shape[1]==2 and len(arr)>=2 and np.isfinite(arr).all():
            rows.append((float(np.median(arr@normal)), index, arr))
    rows.sort(key=lambda entry:entry[0])
    return rows


def suppress_double_tracks(tracks, reference, second, physical_intervals=None, *,
                           confirmed=False, holdout=None):
    """One candidate per real-yarn period; no frequency guess from dark stripes.

    The two anchors and VERIFIED number of real intervals are CALIBRATION.
    The optional third yarn is strictly withheld for reporting.
    Refuse when aliasing is unclear, or after-anchor alignment is unsupported.
    """
    report={
        "status":"ABSTAINED","reason":None,
        "physical_interval_count_verified":False,
        "physical_intervals":None,"physical_pitch_px":None,
        "original_candidate_pitch_px":None,"alias_ratio":None,
        "original_candidates":len(tracks),"retained_candidates":None,
        "suppressed_candidates":None,
        "reference_before_px":median_distance(reference,tracks),
        "second_before_px":median_distance(second,tracks),
        "reference_after_px":None,"second_after_px":None,
        "independent_holdout_before_px":median_distance(holdout,tracks) if holdout else None,
        "independent_holdout_after_px":None,
        "warning":"Physical intervals need manual confirmation; sparse-grid output remains a candidate, not per-yarn truth.",
    }
    if not confirmed or isinstance(physical_intervals,bool) or not isinstance(physical_intervals,int) or not 1<=physical_intervals<=200:
        report["reason"]="PHYSICAL_INTERVAL_COUNT_UNCONFIRMED"
        return tracks,report
    report["physical_interval_count_verified"]=True
    report["physical_intervals"]=physical_intervals
    n=normal_to_segment(reference)
    n2=normal_to_segment(second)
    if abs(float(np.dot(n,n2)))<.97:
        report["reason"]="NONPARALLEL_REAL_YARN_ANCHORS"
        return tracks,report
    r0=np.asarray(reference,dtype=float).mean(axis=0)
    r1=np.asarray(second,dtype=float).mean(axis=0)
    separation=float(np.dot(r1-r0,n))
    if separation<0:
        n=-n
        separation=-separation
    pitch=separation/physical_intervals
    report["physical_pitch_px"]=round(pitch,3)
    if pitch<5:
        report["reason"]="PHYSICAL_YARNS_UNRESOLVABLE_AT_IMAGE_SCALE"
        return tracks,report
    rows=_lines_by_normal(tracks,n)
    if len(rows)<4:
        report["reason"]="TOO_FEW_CANDIDATE_TRACKS"
        return tracks,report
    coords=np.array([r[0] for r in rows])
    spacings=np.diff(coords)
    spacings=spacings[spacings>2]
    if len(spacings)<3:
        report["reason"]="CANDIDATE_SPACING_UNRELIABLE"
        return tracks,report
    old_pitch=float(np.median(spacings))
    ratio=pitch/old_pitch
    report["original_candidate_pitch_px"]=round(old_pitch,3)
    report["alias_ratio"]=round(ratio,3)
    if not (1.45<=ratio<=3.20):
        report["reason"]="NO_CLEAR_INTEGER_MULTIPLE_ALIAS"
        return tracks,report
    # Close-to-integral alias hypotheses are less likely to be caused by
    # perspective or a wrong candidate family. Do not tune by fabric ID.
    nearest_alias=int(round(ratio))
    if nearest_alias not in (2,3) or abs(ratio-nearest_alias)>.32:
        report["reason"]="NONINTEGRAL_PERIOD_ALIAS_UNRELIABLE"
        return tracks,report
    report["candidate_lines_per_real_yarn_period"]=nearest_alias
    signed0=float(np.dot(r0,n))
    lower=coords[0]-old_pitch*.25
    upper=coords[-1]+old_pitch*.25
    kmin=math.ceil((lower-signed0)/pitch)
    kmax=math.floor((upper-signed0)/pitch)
    if kmax<kmin:
        report["reason"]="NO_PHYSICAL_LATTICE_IN_IMAGE"
        return tracks,report
    if not (kmin<=0<=kmax and kmin<=physical_intervals<=kmax):
        report["reason"]="CALIBRATION_OUTSIDE_CANDIDATE_SUPPORT"
        return tracks,report
    selected=[]
    used=set()
    for k in range(kmin,kmax+1):
        target=signed0+k*pitch
        choices=[(abs(q-target), idx, q, pts) for q,idx,pts in rows if idx not in used]
        if not choices:
            break
        distance,idx,q,pts=min(choices,key=lambda item:item[0])
        if distance>.48*pitch:
            report["reason"]="INSUFFICIENT_LOCAL_TRACK_SUPPORT"
            return tracks,report
        used.add(idx)
        selected.append((k,idx,(pts+(target-q)*n).tolist()))
    if not selected or len(selected)>=len(rows):
        report["reason"]="NO_DUPLICATES_TO_SUPPRESS"
        return tracks,report
    output=[track for _,_,track in selected]
    first=median_distance(reference,output)
    second_dist=median_distance(second,output)
    report["reference_after_px"]=first
    report["second_after_px"]=second_dist
    report["retained_candidates"]=len(output)
    report["suppressed_candidates"]=len(rows)-len(output)
    report["independent_holdout_after_px"]=median_distance(holdout,output) if holdout else None
    # If the original V4 candidate polyline does not cross the original
    # human-confirmed anchor, do not mark mere mathematical phase as usable.
    bound=max(4.0,.22*pitch)
    if first is None or second_dist is None or max(first,second_dist)>bound:
        report["reason"]="REAL_YARN_ANCHOR_TRACK_GEOMETRY_NOT_SUPPORTED"
        return tracks,report
    report["status"]="DOUBLE_CANDIDATES_SUPPRESSED_UNVERIFIED_FIELD"
    report["reason"]=None
    report["selected_original_indices"]=[i for _,i,_ in selected]
    return output,report
