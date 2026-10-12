"""Two confirmed, distinct real-yarn segments constrain candidate A phase AND pitch.

Both operator segments are calibration inputs, not independent accuracy GT.
No frozen V4/V5 algorithm change, no assumed dark-vs-light yarn polarity.
This result is a testable candidate lattice, NOT individually validated yarns.
"""
from __future__ import annotations
import numpy as np
from benchmark.yarn_phase_anchor import normal_to_segment, median_distance

def _candidate_rows(tracks, normal):
    rows=[]
    for path in tracks:
        pts=np.asarray(path,dtype=float)
        if pts.ndim==2 and pts.shape[1]==2 and len(pts)>=2:
            rows.append((float(np.median(pts@normal)),pts))
    return sorted(rows,key=lambda x:x[0])

def two_anchor_correct(tracks, reference, second, *, pitch_scale_bounds=(.65,1.40)):
    """Affine remap normal coordinates to 2 physical yarns; no hidden GT claim."""
    normal=normal_to_segment(reference)
    other=normal_to_segment(second)
    report=dict(status="ABSTAINED", reason=None, source="TWO_OPERATOR_YARN_ANCHORS",
                reference_before_px=median_distance(reference,tracks),
                second_before_px=median_distance(second,tracks),
                reference_after_px=None,second_after_px=None,
                scale_pitch=None,observed_candidate_intervals=None,
                physical_interval_count_verified=False,
                warning="Both human segments are calibration anchors; after-error is NOT independent benchmark. Verify yarn-by-yarn positions before publishing.",
                B_family="UNMODIFIED_NO_CONFIRMED_CROSS_REFERENCE")
    if abs(float(np.dot(normal,other)))<.96:
        report["reason"]="ANCHOR_DIRECTIONS_NOT_PARALLEL"
        return tracks,report
    refs=np.asarray(reference,float).mean(axis=0)
    checks=np.asarray(second,float).mean(axis=0)
    p0=float(np.dot(refs,normal));p1=float(np.dot(checks,normal))
    positions=_candidate_rows(tracks,normal)
    if len(positions)<4:
        report["reason"]="NOT_ENOUGH_TRACKS"
        return tracks,report
    pitch=float(np.median(np.diff([r[0] for r in positions])))
    report["original_candidate_pitch_px"]=round(pitch,3)
    if pitch<=3 or abs(p1-p0)<pitch*.8:
        report["reason"]="NOT_DISTINCT_ANCHOR_YARNS"
        return tracks,report
    idx0=int(np.argmin([abs(q-p0) for q,_ in positions]))
    idx1=int(np.argmin([abs(q-p1) for q,_ in positions]))
    if idx0==idx1:
        report["reason"]="SAME_GRID_INDEX"
        return tracks,report
    q0,q1=positions[idx0][0],positions[idx1][0]
    scale=float((p1-p0)/(q1-q0))
    report["scale_pitch"]=round(scale,5)
    report["observed_candidate_intervals"]=abs(idx1-idx0)
    report["anchors_q_px"]=[round(q0,3),round(q1,3)]
    if not (pitch_scale_bounds[0]<=scale<=pitch_scale_bounds[1]):
        report["reason"]="IMPLAUSIBLE_PITCH_SCALE_OR_INDEX_ALIAS"
        return tracks,report
    # Remap each tracked path at native pixel scale. This preserves the order,
    # number of tracks, original along-axis coordinates, and V4 provenance.
    corrected=[]
    for track in tracks:
        pts=np.asarray(track,dtype=float)
        if pts.ndim!=2 or len(pts)<2:
            corrected.append(track)
            continue
        signed=pts@normal
        displacement=(p0+scale*(signed-q0)-signed)[:,None]*normal
        corrected.append((pts+displacement).tolist())
    report["reference_after_px"]=median_distance(reference,corrected)
    report["second_after_px"]=median_distance(second,corrected)
    report["revised_candidate_pitch_px"]=round(pitch*scale,3)
    before0=report["reference_before_px"];before1=report["second_before_px"]
    after0=report["reference_after_px"];after1=report["second_after_px"]
    if any(v is None for v in (before0,before1,after0,after1)):
        report["reason"]="UNSUPPORTED_SEGMENT"
        return tracks,report
    # Do not mark a fix if merely matching theoretical infinite lines would
    # leave either marked real yarn far away from any actual candidate track.
    if max(after0,after1)>max(4.,.22*pitch*scale):
        report["reason"]="ANCHORS_STILL_FAR_FROM_CANDIDATE_SUPPORT"
        return tracks,report
    if after0>before0+1. or after1>before1+1.:
        report["reason"]="CORRECTION_MADE_AN_ANCHOR_WORSE"
        return tracks,report
    report["status"]="TWO_ANCHOR_CANDIDATE_GRID"
    return corrected,report
