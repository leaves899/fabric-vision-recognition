"""G1.3 operator-assisted V5 geometry audit with physically distinct A1/A2.

This is an OPTIONAL two-anchor path, not improved fully-automatic V5.
A3 is strictly held out from inference and is an approximate physical-yarn
path, not verified pixel centerline or real-yarn count.
"""
from __future__ import annotations
import numpy as np
from benchmark.yarn_phase_anchor import normal_to_segment,median_distance
from benchmark.yarn_pitch_calibration import two_anchor_correct
from benchmark.yarn_duplicate_guard import suppress_double_tracks

def _idx(positions,value):
    return int(np.argmin(abs(np.asarray(positions)-value)))

def candidate_gap_count(tracks,first,second):
    n=normal_to_segment(first)
    mid=[]
    for track in tracks:
        a=np.asarray(track,float)
        if a.ndim==2 and a.shape[1]==2 and len(a)>=2 and np.isfinite(a).all():
            mid.append(float(np.median(a@n)))
    if len(mid)<4:return None
    mid.sort()
    a=float(np.mean(np.asarray(first)@n))
    b=float(np.mean(np.asarray(second)@n))
    return abs(_idx(mid,a)-_idx(mid,b))

def assisted_first_family(tracks,a1,a2,*,physical_intervals,confirmed):
    info={"status":"ABSTAINED","reason":None,"source":"A1_A2_OPERATOR_ASSISTED",
          "operator_anchors":["A1","A2"],"A3_used_in_inference":False,
          "physical_yarn_identity_verified":False,
          "input_count":len(tracks),"output_count":len(tracks),
          "physical_intervals_verified":bool(confirmed)}
    if type(physical_intervals)!=int or not 1<=physical_intervals<=200 or confirmed is not True:
        info["reason"]="UNCONFIRMED_OPERATOR_INTERVALS"
        return tracks,info
    observed=candidate_gap_count(tracks,a1,a2)
    info["v5_candidate_index_intervals"]=observed
    info["operator_physical_yarn_intervals"]=physical_intervals
    info["before_A1_distance_px"]=median_distance(a1,tracks)
    info["before_A2_distance_px"]=median_distance(a2,tracks)
    if observed is None:
        info["reason"]="INSUFFICIENT_CANDIDATES"
        return tracks,info
    if observed==physical_intervals:
        result,diag=two_anchor_correct(tracks,a1,a2)
        info["procedure"]="INDEX_MATCH_THEN_TWO_ANCHOR_AFFINE"
    elif observed>physical_intervals:
        result,diag=suppress_double_tracks(tracks,a1,a2,physical_intervals,confirmed=True,holdout=None)
        info["procedure"]="CONSERVATIVE_INTEGER_PERIOD_ALIAS_TEST"
    else:
        info["reason"]="MISSING_REAL_YARN_INTERVAL_CANDIDATES_NO_INTERPOLATION"
        return tracks,info
    info["component_report"]=diag
    if diag["status"] not in ("TWO_ANCHOR_CANDIDATE_GRID","DOUBLE_CANDIDATES_SUPPRESSED_UNVERIFIED_FIELD"):
        info["reason"]=diag.get("reason","PROPOSAL_REJECTED")
        return tracks,info
    info["status"]="ASSISTED_CANDIDATE_ONLY"
    info["output_count"]=len(result)
    info["after_A1_distance_px"]=median_distance(a1,result)
    info["after_A2_distance_px"]=median_distance(a2,result)
    info["warning"]="A1/A2 fit error is calibration, not independent evaluation"
    return result,info
