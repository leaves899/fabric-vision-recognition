"""Safe semantics layer for an unverified optical-morphology V3 proposal.

The provided V3 detects no individual yarn identity, no across-occlusion
correspondences, and no independently measured physical yarn pitch.
"""
from __future__ import annotations
import math
from .symmetric_valley_user_v3 import detect_and_verify_physical_yarns_v3


def angdiff(a,b):
    return abs((float(a)-float(b)+90.)%180.-90.)


def investigate(image):
    raw=detect_and_verify_physical_yarns_v3(image)
    a=raw.get("warp_or_dom_deg")
    p=raw.get("pattern_deg")
    return {
        "status":"UNVERIFIED_OPTICAL_MORPHOLOGY" if raw["accepted"] else "ABSTAINED",
        "image_axis_deg":round(float(a),4) if a is not None else None,
        "macro_pattern_deg":round(float(p),4) if p is not None else None,
        "risk_macro_overlap":a is not None and p is not None and angdiff(a,p)<=8.,
        "source_heuristic_flag":bool(raw.get("twill_hijack_risk")),
        "source_heuristic_outcome":raw.get("reject_reason"),
        "raw_shoulder_distance_proxy_px":raw.get("estimated_yarn_pitch_px"),
        "is_yarn_pitch_measured":False,
        "is_physical_yarn_verified":False,
        "has_cross_occlusion_same_yarn_match":False,
        "is_warp_weft_identified":False,
        "density_per_cm":None
    }
