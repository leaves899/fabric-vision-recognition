"""Read saved V5 JSON without modifying frozen V4 or running inference.

This adapter exposes *candidate* results only. It never upgrades V5
NEEDS_CONFIRMATION to a physically validated measurement.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

FROZEN_V4_SHA = "dde5d84193a3f3d02bb55ad72a8c2b9f2a640034563ed936736ad46808b8dad1"


def _number(value):
    if value is None or isinstance(value, bool): return None
    try: number = float(value)
    except (ValueError, TypeError): return None
    return number if math.isfinite(number) else None


def parse_v5(raw: dict) -> dict:
    """Return numeric candidates and explicit restrictions on their interpretation."""
    result = raw.get("result", raw) if isinstance(raw, dict) else None
    if not isinstance(result, dict): raise ValueError("V5 result is not an object")
    if not str(result.get("demo_version", "")).endswith("-v5"):
        raise ValueError("not a V5 demo result")
    if result.get("v4", {}).get("frozen_sha256") != FROZEN_V4_SHA:
        raise ValueError("unexpected frozen V4 hash")
    manual = result.get("manual_yarn_reference") or {}
    assignment = result.get("family_assignment") or {}
    calibration = result.get("calibration") or {}
    params = {p.get("id"): p for p in result.get("parameters", []) if isinstance(p, dict)}
    reasons = []
    identity_ok = assignment.get("confirmed_by_human") is True and assignment.get("warp_family") in ("A", "B")
    reference_ok = manual.get("confirmed_by_operator") is True and manual.get("source") == "USER_TWO_POINT_SAME_REAL_YARN"
    calibrated = calibration.get("confirmed") is True and _number(calibration.get("cm_per_px")) not in (None, 0)
    if not reference_ok: reasons.append("REFERENCE_NOT_CONFIRMED")
    if not identity_ok: reasons.append("WARP_WEFT_NOT_CONFIRMED")
    if not calibrated: reasons.append("FRAME_5CM_NOT_CONFIRMED")

    output = {"source": "V5_FROZEN_V4_CANDIDATES", "review_status": "CANDIDATE",
              "warp_axis_deg": None, "weft_axis_deg": None,
              "warp_density_per_cm": None, "weft_density_per_cm": None,
              "reasons": reasons, "image_sha256": result.get("image_sha256")}
    if identity_ok and reference_ok:
        for key, idx in (("warp_axis_deg", 1), ("weft_axis_deg", 2)):
            p = params.get(idx, {})
            if p.get("status") not in ("UNAVAILABLE", None):
                value = _number(p.get("value"))
                if value is not None and 0 <= value < 180: output[key] = value
    if identity_ok and reference_ok and calibrated:
        for key, idx in (("warp_density_per_cm", 8), ("weft_density_per_cm", 9)):
            p = params.get(idx, {})
            value = p.get("value") if p.get("status") != "UNAVAILABLE" else None
            number = _number(value.get("candidate_per_cm")) if isinstance(value, dict) else None
            if number is not None and number >= 0: output[key] = number
    return output


def load_v5(path: Path) -> dict:
    with path.open(encoding="utf-8") as source:
        raw = json.load(source)
    return parse_v5(raw)
