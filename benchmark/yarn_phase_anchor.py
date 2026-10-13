# NOTE (2026-10-13): U20261013 marked lines are PHYSICAL_YARN_REFERENCE of distinct REAL yarns through possible occlusion; geometric residuals are NOT visible-segment pixel GT. A1/A2 calibration must not be called independent accuracy; A3 holdout only. No cm density from 2x zoom.
"""Candidate phase alignment to an operator-confirmed yarn. V4 remains frozen."""
from __future__ import annotations
import numpy as np
from benchmark.phase_offset_diagnostic import nearby_candidate_pitch, closest_track_distances

def normal_to_segment(points):
    a = np.asarray(points, dtype=float)
    if a.shape != (2, 2) or not np.isfinite(a).all():
        raise ValueError("two finite yarn points required")
    vec = a[1] - a[0]
    length = float(np.linalg.norm(vec))
    if length < 20:
        raise ValueError("yarn reference must be at least 20 native pixels")
    return np.array([-vec[1], vec[0]]) / length

def nearest_signed_distances(points, tracks, normal):
    pieces = []
    for track in tracks:
        poly = np.asarray(track, dtype=float)
        if poly.ndim != 2 or poly.shape[1] != 2 or len(poly) < 2:
            continue
        for a, b in zip(poly[:-1], poly[1:]):
            if np.sum((b - a)**2) > 1e-8:
                pieces.append((a, b))
    if not pieces:
        return []
    a = np.array([p[0] for p in pieces])
    v = np.array([p[1]-p[0] for p in pieces])
    d = np.sum(v*v, axis=1)
    values = []
    for p in points:
        t = np.clip(np.sum((p-a)*v, axis=1)/d, 0, 1)
        foot = a + t[:, None]*v
        idx = int(np.argmin(np.sum((foot-p)**2, axis=1)))
        values.append(float(np.dot(p-foot[idx], normal)))
    return values

def median_distance(points, tracks):
    p = np.linspace(np.asarray(points[0],float), np.asarray(points[1],float), 17)
    values = [v for v in closest_track_distances(p, tracks) if v is not None]
    return round(float(np.median(values)), 3) if values else None

def adjust_first_family(tracks, reference, check=None):
    """Phase from INPUT segment alone; check segment is withheld for evaluation."""
    normal = normal_to_segment(reference)
    p = np.linspace(np.asarray(reference[0],float),np.asarray(reference[1],float),17)
    pitch, count = nearby_candidate_pitch(tracks, reference, p[8])
    report = dict(status="ABSTAINED", reason=None, candidate_pitch_px=pitch,
                  reference_before_px=median_distance(reference,tracks),
                  reference_after_px=None, check_before_px=median_distance(check,tracks) if check else None,
                  check_after_px=None, signed_shift_px=None, family_b="UNCHANGED_NOT_ANCHORED")
    if pitch is None or count < 3 or pitch <= 3:
        report["reason"] = "NO_RELIABLE_PITCH"
        return tracks, report
    offsets = nearest_signed_distances(p,tracks,normal)
    if len(offsets)<12:
        report["reason"] = "NO_TRACK_SUPPORT"
        return tracks, report
    center = float(np.median(offsets))
    mad = float(np.median(np.abs(np.asarray(offsets)-center)))
    report["offset_mad_px"] = round(mad,3)
    if mad > max(3, .2*pitch):
        report["reason"] = "PHASE_NOT_STABLE"
        return tracks, report
    shift = (center + pitch/2) % pitch - pitch/2
    report["signed_shift_px"] = round(float(shift),3)
    move = normal * shift
    corrected = [(np.asarray(path,float)+move).tolist() for path in tracks]
    before = report["reference_before_px"]
    after = median_distance(reference,corrected)
    report["reference_after_px"] = after
    report["check_after_px"] = median_distance(check,corrected) if check else None
    if before is None or after is None or after > max(4,.25*pitch) or (before > 4 and after >= before*.65):
        report["reason"] = "ANCHOR_NOT_ALIGNED_AFTER_TRANSLATION"
        return tracks, report
    report["status"] = "ANCHORED_CANDIDATE_A" if abs(shift)>.25 else "ALREADY_ALIGNED_A"
    return corrected, report
