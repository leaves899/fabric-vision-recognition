from __future__ import annotations

import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.signal import find_peaks

from .config import EngineConfig, DEFAULT_CONFIG


def estimate_normal_periodicity(
    aligned_gray: np.ndarray,
    min_spacing_px: float,
    max_spacing_px: float,
    config: EngineConfig = DEFAULT_CONFIG,
) -> dict:
    """Estimate the normal yarn pitch from an independent grey-profile autocorrelation.

    ``aligned_gray`` is only a rotated copy of the normalized input image.  This
    routine does not add, move, merge, or remove centreline tracks, so it is an
    independent consistency check rather than a second density route.
    """
    if aligned_gray.ndim != 2 or min(aligned_gray.shape[:2]) < 24:
        return {"status": "NOT_AVAILABLE", "reason": "PERIODICITY_IMAGE_UNAVAILABLE"}

    profile = np.mean(aligned_gray.astype(np.float64), axis=0)
    # Suppress illumination drift while retaining yarn-scale repeated contrast.
    trend_sigma = max(6.0, min(float(min_spacing_px) * 1.5, float(profile.size) / 8.0))
    signal = profile - gaussian_filter1d(profile, sigma=trend_sigma, mode="nearest")
    signal -= float(np.mean(signal))
    energy = float(np.dot(signal, signal))
    if energy <= 1e-8:
        return {"status": "NOT_AVAILABLE", "reason": "PERIODICITY_PROFILE_FLAT"}

    autocorr = np.correlate(signal, signal, mode="full")[len(signal) - 1:]
    autocorr /= energy
    lo = max(2, int(np.ceil(float(min_spacing_px))))
    hi = min(len(autocorr) - 1, int(np.floor(float(max_spacing_px))))
    if hi <= lo:
        return {"status": "NOT_AVAILABLE", "reason": "PERIODICITY_RANGE_INVALID"}

    window = autocorr[lo:hi + 1]
    peaks, props = find_peaks(
        window,
        distance=max(2, int(np.floor(float(min_spacing_px) * 0.45))),
        prominence=max(0.025, float(np.std(window)) * 0.45),
    )
    if len(peaks) == 0:
        return {"status": "NOT_AVAILABLE", "reason": "PERIODICITY_PEAK_NOT_FOUND"}

    peak_values = window[peaks]
    strongest = float(np.max(peak_values))
    if strongest <= 0.0:
        return {"status": "NOT_AVAILABLE", "reason": "PERIODICITY_POSITIVE_PEAK_NOT_FOUND"}
    # Prefer the earliest peak that is nearly as well supported as the strongest
    # one, avoiding a 2x/3x harmonic when the fundamental is visible.
    candidates = peaks[peak_values >= strongest * 0.85]
    selected = int(candidates[0])
    lag = lo + selected
    return {
        "status": "PASS",
        "spacing_px": float(lag),
        "autocorrelation_peak": float(window[selected]),
        "candidate_peak_count": int(len(peaks)),
        "search_range_px": [int(lo), int(hi)],
    }


def compare_periodicity_to_centerlines(periodicity: dict, center_spacing_px: float) -> dict:
    """Return a diagnostic comparison without modifying either measurement."""
    if periodicity.get("status") != "PASS" or float(center_spacing_px) <= 0:
        return {
            **periodicity,
            "centerline_spacing_px": float(center_spacing_px),
            "spacing_difference_pct": None,
            "agreement": "NOT_AVAILABLE",
        }
    periodic_spacing = float(periodicity["spacing_px"])
    difference = abs(periodic_spacing - float(center_spacing_px)) / max(
        (periodic_spacing + float(center_spacing_px)) * 0.5, 1e-9
    ) * 100.0
    return {
        **periodicity,
        "centerline_spacing_px": float(center_spacing_px),
        "spacing_difference_pct": float(difference),
        "agreement": "AVAILABLE",
    }
