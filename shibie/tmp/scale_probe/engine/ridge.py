from __future__ import annotations

import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.optimize import linear_sum_assignment
from scipy.signal import find_peaks

from .config import EngineConfig, DEFAULT_CONFIG
from .preprocess import rotate_keep_size


def _effective_mm_per_px_normal(line_deg: float, mm_x: float, mm_y: float) -> float:
    theta = np.deg2rad(float(line_deg))
    nx, ny = -np.sin(theta), np.cos(theta)
    return float(np.sqrt((nx * mm_x) ** 2 + (ny * mm_y) ** 2))


def _profile_dynamic(signal: np.ndarray) -> float:
    q50, q95 = np.quantile(signal, [0.50, 0.95])
    return max(float(q95 - q50), 1e-8)


def _detect_peaks(profile: np.ndarray, min_spacing_px: float, prominence_ratio: float = 0.13, config: EngineConfig = DEFAULT_CONFIG):
    """Detect only measured local maxima; no predicted/synthetic peaks."""
    p = gaussian_filter1d(profile.astype(np.float64), sigma=float(config.ridge_strip_smoothing_sigma))
    prominence = max(_profile_dynamic(p) * prominence_ratio, 0.0035)
    # Keep peaks sufficiently separated to suppress the two edges of one yarn.
    distance = max(3, int(np.floor(max(min_spacing_px, 1.0) * config.ridge_peak_distance_ratio)))
    peaks, props = find_peaks(p, prominence=prominence, distance=distance)
    proms = np.asarray(props.get("prominences", np.zeros(len(peaks))), dtype=np.float64)
    return peaks.astype(np.float64), proms, float(prominence)


def _bounded_prediction(track: dict, y: float, seed_spacing: float, prediction_points: int) -> float:
    seed = float(track["seed_x"])
    pts = track["points"]
    if len(pts) < 2:
        return seed
    arr = np.asarray(pts[-max(2, int(prediction_points)):], dtype=np.float64)
    if np.ptp(arr[:, 1]) <= 1e-6:
        return seed
    slope, intercept = np.polyfit(arr[:, 1], arr[:, 0], 1)
    pred = float(slope * y + intercept)
    # After alignment a real yarn should remain close to its global seed column.
    # This bound prevents a diagonal twill ridge from dragging a track across neighbours.
    anchor_limit = max(2.0, min(6.0, seed_spacing * 0.18))
    return float(np.clip(pred, seed - anchor_limit, seed + anchor_limit))


def _validate_seed_tracks(
    roi: np.ndarray,
    validation_roi: np.ndarray,
    seeds: np.ndarray,
    min_spacing_px: float,
    seed_spacing_px: float,
    config: EngineConfig,
):
    """Validate global Ridge seeds with independent strip-level peak evidence.

    Global profile provides candidate yarn columns. Each strip must independently expose a
    real find_peaks response near a candidate. Prediction is used only for assignment.
    """
    h = int(roi.shape[0])
    strip_count = int(np.clip(round(h / 28.0), 13, 21))
    ys = np.linspace(0, h - 1, strip_count).astype(int)
    band_half = max(2, int(round(h / max(strip_count * 4.2, 1))))
    match_radius = max(2.5, min(7.0, seed_spacing_px * 0.20))

    tracks = [
        {
            "points": [], "seed_x": float(x), "prominence_sum": 0.0,
            "profile_contrast_sum": 0.0, "matched_strips": 0,
        }
        for x in seeds
    ]
    counts, thresholds = [], []

    for y in ys:
        ya, yb = max(0, y - band_half), min(h, y + band_half + 1)
        block = roi[ya:yb].astype(np.float64)
        row = 0.62 * np.mean(block, axis=0) + 0.38 * np.quantile(block, 0.72, axis=0)
        validation_row = np.mean(validation_roi[ya:yb].astype(np.float64), axis=0)
        validation_dynamic = max(float(np.quantile(validation_row, 0.90) - np.quantile(validation_row, 0.10)), 1e-6)
        peaks, proms, thr = _detect_peaks(row, min_spacing_px, prominence_ratio=0.13, config=config)
        counts.append(int(len(peaks)))
        thresholds.append(float(thr))
        if len(peaks) == 0:
            continue

        predictions = np.asarray(
            [_bounded_prediction(tr, float(y), seed_spacing_px, config.ridge_prediction_points) for tr in tracks],
            dtype=np.float64,
        )
        dist = np.abs(predictions[:, None] - peaks[None, :])
        big = 1e6
        cost = np.where(dist <= match_radius, dist / max(match_radius, 1e-6), big)
        # Stronger measured peaks only break ties; distance remains the primary evidence.
        pnorm = np.clip(proms / max(float(np.quantile(proms, 0.90)), 1e-9), 0.0, 1.0)
        cost = cost + 0.04 * (1.0 - pnorm[None, :])
        rr, cc = linear_sum_assignment(cost)
        for r, c in zip(rr, cc):
            if cost[r, c] >= big:
                continue
            tr = tracks[int(r)]
            x = int(round(float(peaks[int(c)])))
            x = int(np.clip(x, 0, len(validation_row) - 1))
            side = max(2, min(10, int(round(seed_spacing_px * 0.22))))
            left = validation_row[max(0, x - 2 * side):max(0, x - side)]
            right = validation_row[min(len(validation_row), x + side):min(len(validation_row), x + 2 * side)]
            baseline = np.concatenate((left, right))
            local_contrast = abs(float(validation_row[x]) - float(np.median(baseline))) / validation_dynamic if len(baseline) else 0.0
            tr["points"].append((float(peaks[int(c)]), float(y)))
            tr["prominence_sum"] += float(proms[int(c)])
            tr["profile_contrast_sum"] += float(local_contrast)
            tr["matched_strips"] += 1

    for tr in tracks:
        n = max(int(tr["matched_strips"]), 1)
        tr["mean_peak_prominence"] = float(tr["prominence_sum"] / n)
        tr["mean_profile_contrast"] = float(tr["profile_contrast_sum"] / n)

    # The Steerable response proposes the seed; this independent normalized-gray
    # contrast check suppresses track candidates that are much weaker than their
    # neighbours.  It never runs when it could leave too few tracks to measure.
    contrast_values = np.asarray([tr["mean_profile_contrast"] for tr in tracks], dtype=np.float64)
    contrast_reference = float(np.median(contrast_values)) if len(contrast_values) else 0.0
    contrast_floor = max(
        float(config.ridge_track_profile_contrast_floor),
        contrast_reference * float(config.ridge_track_profile_contrast_relative_floor),
    )
    retained_tracks = [tr for tr in tracks if float(tr["mean_profile_contrast"]) >= contrast_floor]
    min_retained = int(config.min_valid_centerlines + config.ridge_track_filter_min_extra)
    filtered = retained_tracks if len(retained_tracks) >= min_retained else tracks
    rejected_count = int(len(tracks) - len(filtered))

    return filtered, int(strip_count), {
        "match_radius_px": float(match_radius),
        "strip_count": int(strip_count),
        "mean_detected_peaks_per_strip": float(np.mean(counts)) if counts else 0.0,
        "median_strip_prominence_threshold": float(np.median(thresholds)) if thresholds else 0.0,
        "track_profile_contrast_reference": float(contrast_reference),
        "track_profile_contrast_floor": float(contrast_floor),
        "track_profile_rejected_count": rejected_count,
    }


def ridge_detection_and_centerline_linking(
    response: np.ndarray,
    line_direction_deg: float,
    mm_per_px_x_working: float,
    mm_per_px_y_working: float,
    config: EngineConfig = DEFAULT_CONFIG,
    validation_image: np.ndarray | None = None,
) -> dict:
    """Ridge Detection + Centerline Linking, evidence-driven and seed-anchored."""
    rotation_deg = float(line_direction_deg) - 90.0
    aligned = rotate_keep_size(response, rotation_deg, border_value=0.0)
    aligned_validation = rotate_keep_size(validation_image, rotation_deg, border_value=0.0) if validation_image is not None else aligned
    h, w = aligned.shape[:2]
    y0, y1 = int(h * 0.10), int(h * 0.90)
    x0, x1 = int(w * 0.08), int(w * 0.92)
    roi = aligned[y0:y1, x0:x1]
    validation_roi = aligned_validation[y0:y1, x0:x1]
    if min(roi.shape[:2]) < 70:
        raise ValueError("RIDGE_ROI_TOO_SMALL")

    mm_normal = _effective_mm_per_px_normal(line_direction_deg, mm_per_px_x_working, mm_per_px_y_working)
    min_spacing_px = 10.0 / (config.density_max_per_cm * mm_normal)
    max_spacing_px = 10.0 / (config.density_min_per_cm * mm_normal)

    # Global evidence: long parallel ridges accumulate in this profile.
    profile = 0.65 * np.mean(roi, axis=0) + 0.35 * np.quantile(roi, 0.70, axis=0)
    profile = gaussian_filter1d(profile.astype(np.float64), sigma=float(config.ridge_global_smoothing_sigma))
    dynamic = _profile_dynamic(profile)
    prominence = max(dynamic * 0.13, 0.004)
    peak_distance = max(4, int(np.floor(min_spacing_px * config.ridge_peak_distance_ratio)))
    peaks, props = find_peaks(profile, prominence=prominence, distance=peak_distance)
    if len(peaks) < config.min_valid_centerlines:
        peaks, props = find_peaks(profile, prominence=max(prominence * 0.70, 0.003), distance=peak_distance)
    if len(peaks) < config.min_valid_centerlines:
        raise ValueError("INSUFFICIENT_RIDGE_SEEDS")

    seed_positions = peaks.astype(np.float64)
    seed_prom = np.asarray(props.get("prominences", np.ones(len(peaks))), dtype=np.float64)
    order = np.argsort(seed_positions)
    seed_positions, seed_prom = seed_positions[order], seed_prom[order]

    # Merge only physically implausible duplicate ridges; Ground Truth is never used.
    merge_dist = max(1.8, min_spacing_px * config.ridge_seed_merge_ratio)
    seeds, merged_prom = [], []
    for x, p in zip(seed_positions, seed_prom):
        if not seeds or x - seeds[-1] >= merge_dist:
            seeds.append(float(x)); merged_prom.append(float(p))
        elif p > merged_prom[-1]:
            seeds[-1] = float(x); merged_prom[-1] = float(p)
    seeds = np.asarray(seeds, dtype=np.float64)
    if len(seeds) < config.min_valid_centerlines:
        raise ValueError("INSUFFICIENT_RIDGE_SEEDS")

    diffs = np.diff(seeds)
    seed_spacing = float(np.median(diffs)) if len(diffs) else float(min_spacing_px)
    tracks, sampled_strips, diag = _validate_seed_tracks(
        roi, validation_roi, seeds, min_spacing_px, seed_spacing, config
    )

    return {
        "aligned_response": roi,
        # 保留与响应图同几何位置的归一化灰度 ROI，供后续独立周期校验使用。
        "aligned_validation": validation_roi,
        "raw_tracks": tracks,
        "sampled_rows": int(sampled_strips),
        "rotation_deg": round(rotation_deg, 4),
        "working_mm_per_px_normal": float(mm_normal),
        "min_spacing_px_from_physical_range": float(min_spacing_px),
        "max_spacing_px_from_physical_range": float(max_spacing_px),
        "x_link_tolerance_px": float(diag["match_radius_px"]),
        "ridge_seed_count": int(len(seeds)),
        "ridge_seed_median_spacing_px": float(seed_spacing),
        "profile_prominence": float(prominence),
        "mean_detected_peaks_per_strip": float(diag["mean_detected_peaks_per_strip"]),
        "strip_count": int(diag["strip_count"]),
        "track_profile_rejected_count": int(diag["track_profile_rejected_count"]),
        "track_profile_contrast_floor": float(diag["track_profile_contrast_floor"]),
        "aligned_crop_offset": {"x": x0, "y": y0},
    }
