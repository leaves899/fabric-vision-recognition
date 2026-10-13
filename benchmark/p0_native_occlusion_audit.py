"""E6.3b native-camera occlusion observation audit (NOT a yarn identity solver).

Uses only camera pixels, fragment endpoints, and calibrated pitch. No manual
SAME/NOT_SAME labels, sample ID, image enlargement, or fitted classification
thresholds. An observed intensity transition is not proof of a physical
over/under crossing.
"""
from __future__ import annotations

import numpy as np
import cv2


def observe_gap(image, source, target, pitch, samples=9):
    """Report fixed dimensionless cross-sections along a proposed gap.

    Missing evidence stays None. Endpoints and pitch must be in ORIGINAL
    camera pixel coordinates. Result is descriptive, never a matching score.
    """
    if image is None or image.ndim != 3 or image.shape[2] != 3:
        raise ValueError("original BGR camera image required")
    if not np.isfinite(pitch) or pitch <= 0 or samples < 3:
        raise ValueError("invalid calibration")
    a = np.asarray(source["end"], dtype=float)
    b = np.asarray(target["start"], dtype=float)
    v = b - a
    length = float(np.linalg.norm(v))
    if not np.isfinite(length) or length <= 0:
        return {"status": "UNOBSERVABLE_DEGENERATE_GAP", "sections": [],
                "physical_identity": "UNKNOWN", "observed_over_under": None}
    t = v / length
    n = np.array([-t[1], t[0]])
    # Half-width of one calibrated A-yarn pitch, never a fixed pixel radius.
    offsets = np.linspace(-0.5, 0.5, 17) * pitch
    fractions = np.linspace(0.1, 0.9, samples)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float32)
    h, w = gray.shape
    sections = []
    for frac in fractions:
        center = a + frac*v
        xy = center[None, :] + offsets[:, None]*n[None, :]
        valid = bool(np.isfinite(xy).all() and
                     xy[:, 0].min() >= 1 and xy[:, 0].max() < w-2 and
                     xy[:, 1].min() >= 1 and xy[:, 1].max() < h-2)
        if not valid:
            sections.append({"fraction": round(float(frac), 5),
                             "valid_native_camera_support": False,
                             "cross_section_range": None,
                             "normalized_transverse_total_variation": None,
                             "peak_edge_location_in_pitch": None})
            continue
        x = xy[:, 0].astype(np.float32).reshape(1, -1)
        y = xy[:, 1].astype(np.float32).reshape(1, -1)
        profile = cv2.remap(gray, x, y, cv2.INTER_LINEAR)[0].astype(float)
        dif = np.abs(np.diff(profile))
        span = float(np.ptp(profile))
        total = float(dif.sum())
        edge_ix = int(np.argmax(dif))
        sections.append({
            "fraction": round(float(frac), 5),
            "valid_native_camera_support": True,
            "cross_section_range": round(span/255.0, 6),
            "normalized_transverse_total_variation": round(total/255.0, 6),
            "peak_edge_location_in_pitch": round(float(
                (offsets[edge_ix]+offsets[edge_ix+1])/(2*pitch)), 5),
        })
    usable = [s for s in sections if s["valid_native_camera_support"]]
    # Even full photographic support cannot certify which entity is on top.
    return {
        "status": "DESCRIPTIVE_ONLY" if len(usable)==samples else
                  "PARTIAL_NATIVE_SUPPORT" if usable else "UNOBSERVABLE_OUTSIDE_FRAME",
        "sections": sections,
        "valid_section_count": len(usable),
        "camera_gap_over_pitch": round(length/pitch, 5),
        "physical_identity": "UNKNOWN",
        "observed_over_under": None,
        "physical_boundary_termination_verified": False,
        "fiber_continuity_verified": False,
        "note": "Optical cross-sections may show texture, shading or another yarn; neither identity nor topology follows.",
    }


def audit_alternatives(image, fragments, candidate_pairs, pitch):
    """Observe competing edges in identical fashion; NO pair is selected."""
    lookup = {f["id"]: f for f in fragments}
    result = []
    for src, dst in sorted(set(map(tuple, candidate_pairs))):
        if src not in lookup or dst not in lookup:
            raise ValueError("unregistered fragment")
        result.append({"source": src, "target": dst,
                       "observation": observe_gap(image, lookup[src], lookup[dst], pitch)})
    return {"method": "NATIVE_CAMERA_CROSS_SECTION_EVIDENCE_AUDIT",
            "manual_identity_labels_used": False,
            "fixed_pixel_gate_or_fitted_classification": False,
            "automatically_confirmed_physical_connections": 0,
            "links": result}
