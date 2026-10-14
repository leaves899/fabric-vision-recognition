"""Conservative wrapper around the user-provided symmetric-shoulder V2 baseline.

An optical dark valley is an image structure, not proof of physical yarn.
Do NOT directly connect this function to the production V5 engine.
"""
from __future__ import annotations
import math
from .symmetric_valley_user_v2 import detect_true_yarn_directions_v2


def angle_distance_180(a: float, b: float) -> float:
    return abs((float(a) - float(b) + 90.) % 180. - 90.)


def inspect_candidate(bgr, *, include_map=False) -> dict:
    raw = detect_true_yarn_directions_v2(bgr)
    angle = raw['warp_or_dom_deg'] if raw['accepted'] else None
    macro = raw['pattern_deg']
    risk = angle_distance_180(angle, macro) if angle is not None else None
    result = {
        'status': 'OPTICAL_DARK_VALLEY_UNVERIFIED' if angle is not None else 'ABSTAINED',
        'axis_angle_deg': angle,
        'perpendicular_geometry_only_deg': (angle + 90.) % 180. if angle is not None else None,
        'macroscopic_texture_angle_deg': macro,
        'axis_macro_distance_deg': round(risk, 4) if risk is not None else None,
        'macro_overlap_risk': bool(risk <= 8.) if risk is not None else None,
        'active_response_fraction': raw['valid_pixel_ratio'],
        'uncalibrated_peak_to_median': raw['confidence'] if math.isfinite(raw['confidence']) else None,
        'is_real_yarn_verified': False,
        'warp_weft_identity_verified': False,
        'yarn_density_cm': None,
        'reason': 'LOCAL_SYMMETRIC_OPTICAL_VALLEY_NOT_UNIQUE_TO_YARN',
    }
    if include_map:
        result['sym_seam_map'] = raw['sym_seam_map']
    return result
