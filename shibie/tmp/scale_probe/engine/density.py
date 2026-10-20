from __future__ import annotations

import numpy as np

from .config import EngineConfig, DEFAULT_CONFIG


def relative_diff_pct(a: float, b: float) -> float:
    return abs(a - b) / max((abs(a) + abs(b)) * 0.5, 1e-9) * 100.0


def dual_path_density(
    centerline_result: dict,
    aligned_width_px: int,
    mm_per_px_normal: float,
    config: EngineConfig = DEFAULT_CONFIG,
) -> dict:
    positions = np.asarray(centerline_result["center_positions_px"], dtype=np.float64)
    if len(positions) < config.min_valid_centerlines:
        raise ValueError("INSUFFICIENT_VALID_CENTERLINES")

    spacing_px = float(centerline_result["median_center_spacing_px"])
    if spacing_px <= 0:
        raise ValueError("CENTER_SPACING_INVALID")
    spacing_density = 10.0 / (spacing_px * mm_per_px_normal)

    left = aligned_width_px * 0.08
    right = aligned_width_px * 0.92
    inside = positions[(positions >= left) & (positions < right)]
    physical_length_mm = (right - left) * mm_per_px_normal
    if len(inside) < 3 or physical_length_mm <= 0:
        raise ValueError("COUNT_PATH_EFFECTIVE_LENGTH_INVALID")
    count_density = len(inside) / (physical_length_mm / 10.0)
    diff_pct = relative_diff_pct(count_density, spacing_density)
    spacing_cv = float(centerline_result.get("spacing_cv", 0.0))
    conservative = bool(
        spacing_cv > float(config.spacing_cv_pass)
        or diff_pct > float(config.density_agree_pass_pct)
    )
    # When the spacing evidence is not stable, do not publish a density that is
    # driven only by a potentially over-dense false-centreline pattern.  The
    # count path remains an independent lower-bound check; confidence.py records
    # the warning through the same spacing/agreement metrics.
    final_density = min(spacing_density, count_density) if conservative else spacing_density
    return {
        "density_per_cm": float(final_density),
        "density_count_path": float(count_density),
        "density_spacing_path": float(spacing_density),
        "path_diff_pct": float(diff_pct),
        "count_path_centerlines": int(len(inside)),
        "count_path_physical_length_mm": float(physical_length_mm),
        "conservative_adjustment": conservative,
        "final_rule": "MIN_OF_PATHS_WHEN_UNSTABLE__MEDIAN_SPACING_PRIMARY_OTHERWISE",
    }
