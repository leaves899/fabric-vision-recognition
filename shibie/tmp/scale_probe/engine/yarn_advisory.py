from __future__ import annotations


def _axis_advisory(density_per_cm: float, width: dict | None, axis: str) -> dict:
    """Return a deliberately coarse yarn-count advisory, never a measurement."""
    if not width or width.get("status") == "FAIL":
        return {
            "status": "NOT_AVAILABLE", "range_ne": None, "range_tex": None,
            "confidence": "LOW", "reasons": ["YARN_WIDTH_INPUT_UNAVAILABLE"],
        }
    width_mm = width.get("p50_mm")
    if width_mm is None or float(width_mm) <= 0 or density_per_cm <= 0:
        return {
            "status": "NOT_AVAILABLE", "range_ne": None, "range_tex": None,
            "confidence": "LOW", "reasons": ["YARN_STRUCTURAL_INPUT_INVALID"],
        }

    # PoC lookup bands. These are intentionally broad and must be calibrated with
    # real yarn-count labels before being used outside a feasibility report.
    if width_mm >= 0.18:
        low_ne, high_ne = 6.0, 10.0
    elif width_mm >= 0.12:
        low_ne, high_ne = 10.0, 16.0
    elif width_mm >= 0.08:
        low_ne, high_ne = 16.0, 24.0
    else:
        low_ne, high_ne = 24.0, 40.0
    density_factor = max(0.85, min(1.15, 32.0 / max(float(density_per_cm), 1.0)))
    low_ne *= density_factor
    high_ne *= density_factor
    # Cotton count conversion: tex ~= 590.5 / Ne.
    tex_low = 590.5 / high_ne
    tex_high = 590.5 / low_ne
    return {
        "status": "AVAILABLE", "range_ne": [round(low_ne, 1), round(high_ne, 1)],
        "range_tex": [round(tex_low, 1), round(tex_high, 1)],
        "confidence": "LOW", "reasons": ["HEURISTIC_RULE_NO_GROUND_TRUTH"],
        "input_axis": axis, "input_density_per_cm": round(float(density_per_cm), 3),
        "input_width_p50_mm": round(float(width_mm), 5),
    }


def advise_yarn_counts(
    warp_density_per_cm: float,
    weft_density_per_cm: float,
    apparent_width: dict | None,
) -> dict:
    warp_width = apparent_width.get("warp") if apparent_width else None
    weft_width = apparent_width.get("weft") if apparent_width else None
    return {
        "status": "AVAILABLE" if warp_width and weft_width else "NOT_AVAILABLE",
        "reference_only": True,
        "method": "COARSE_WIDTH_DENSITY_RULE__NO_TRAINED_ESTIMATOR",
        "warp": _axis_advisory(warp_density_per_cm, warp_width, "warp"),
        "weft": _axis_advisory(weft_density_per_cm, weft_width, "weft"),
        "reasons": ["REFERENCE_ONLY_NO_REAL_YARN_COUNT_GROUND_TRUTH"],
    }
