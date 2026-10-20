from __future__ import annotations

import cv2
import numpy as np

from .config import EngineConfig, DEFAULT_CONFIG
from .preprocess import resize_max_side, to_gray


def _gradient_image(image: np.ndarray) -> np.ndarray:
    gray = to_gray(image).astype(np.float32) / 255.0
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    magnitude = cv2.magnitude(gx, gy)
    return cv2.GaussianBlur(magnitude, (0, 0), 1.0)


def estimate_reflection_registration(front: np.ndarray, transmission: np.ndarray, config: EngineConfig = DEFAULT_CONFIG) -> dict:
    """Estimate a translation-only transmission-to-reflection registration.

    The PoC accepts only a measured phase-correlation alignment. Width measurement is
    refused when the two images do not expose enough common geometric evidence.
    """
    if front.shape[:2] != transmission.shape[:2]:
        return {"status": "FAIL", "reasons": ["WIDTH_PAIR_SIZE_MISMATCH"]}

    front_grad, scale = resize_max_side(_gradient_image(front), config.width_registration_max_side)
    trans_grad, _ = resize_max_side(_gradient_image(transmission), config.width_registration_max_side)
    window = cv2.createHanningWindow((front_grad.shape[1], front_grad.shape[0]), cv2.CV_32F)
    shift, response = cv2.phaseCorrelate(trans_grad, front_grad, window)
    dx, dy = float(shift[0] / scale), float(shift[1] / scale)

    baseline = float(np.mean(np.abs(front_grad - trans_grad)))
    matrix_small = np.array([[1.0, 0.0, shift[0]], [0.0, 1.0, shift[1]]], dtype=np.float32)
    shifted = cv2.warpAffine(
        trans_grad, matrix_small, (front_grad.shape[1], front_grad.shape[0]),
        flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT,
    )
    aligned = float(np.mean(np.abs(front_grad - shifted)))
    improvement = (baseline - aligned) / max(baseline, 1e-9)
    reasons: list[str] = []
    if response < config.width_registration_min_response:
        reasons.append("WIDTH_REGISTRATION_WEAK")
    if improvement < config.width_registration_min_improvement and abs(dx) + abs(dy) > 1.0:
        reasons.append("WIDTH_REGISTRATION_NO_IMPROVEMENT")
    return {
        "status": "FAIL" if reasons else "PASS",
        "reasons": reasons,
        "method": "GRADIENT_PHASE_CORRELATION_TRANSLATION",
        "matrix_transmission_to_reflection": [[1.0, 0.0, dx], [0.0, 1.0, dy]],
        "phase_response": round(float(response), 5),
        "gradient_alignment_improvement": round(float(improvement), 5),
    }


def map_centerlines_to_reflection(seed: dict, normalization: dict, matrix: np.ndarray) -> list[np.ndarray]:
    """Return clean transmission centerline points in original reflection coordinates."""
    h, w = seed["normalized_shape"]
    rotation = float(seed["rotation_deg"])
    forward = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), rotation, 1.0)
    inverse = cv2.invertAffineTransform(forward)
    offset = seed["aligned_crop_offset"]
    scale = float(normalization["resize_scale"])
    roi = normalization["roi"]
    result: list[np.ndarray] = []
    for centerline in seed["centerlines"]:
        pts = np.asarray(centerline["points"], dtype=np.float32)
        if len(pts) < 4:
            continue
        aligned = pts.copy()
        aligned[:, 0] += float(offset["x"])
        aligned[:, 1] += float(offset["y"])
        restored = cv2.transform(aligned[None, :, :], inverse)[0]
        restored[:, 0] = restored[:, 0] / scale + float(roi["x"])
        restored[:, 1] = restored[:, 1] / scale + float(roi["y"])
        result.append(cv2.transform(restored[None, :, :], matrix)[0])
    return result


# 保留旧名称，避免宽度模块内已有调用发生行为变化。
def _source_centerlines(seed: dict, normalization: dict, matrix: np.ndarray) -> list[np.ndarray]:
    return map_centerlines_to_reflection(seed, normalization, matrix)


def _sample_profile(gray: np.ndarray, point: np.ndarray, normal: np.ndarray, half_range: float, step: float) -> tuple[np.ndarray, np.ndarray]:
    offsets = np.arange(-half_range, half_range + step * 0.5, step, dtype=np.float32)
    coords = point[None, :] + offsets[:, None] * normal[None, :]
    values = cv2.remap(
        gray, coords[:, 0:1], coords[:, 1:2], cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REFLECT101,
    ).reshape(-1).astype(np.float64)
    return offsets.astype(np.float64), values


def _tile_quality(gray: np.ndarray, point: np.ndarray, config: EngineConfig) -> dict:
    """Score a local reflection tile for width measurement without rejecting it outright."""
    half = int(config.width_tile_half_size_px)
    x, y = int(round(float(point[0]))), int(round(float(point[1])))
    tile = gray[max(0, y - half):min(gray.shape[0], y + half + 1), max(0, x - half):min(gray.shape[1], x + half + 1)]
    if min(tile.shape[:2]) < max(12, half):
        return {"score": config.width_tile_min_weight, "contrast": 0.0, "laplacian_variance": 0.0, "exposure_penalty": 1.0}
    values = tile.astype(np.float32)
    p10, p90 = np.percentile(values, [10, 90])
    contrast = float(p90 - p10)
    laplacian_variance = float(cv2.Laplacian(values, cv2.CV_32F).var())
    exposure_penalty = float(np.mean((tile <= 3) | (tile >= 252)))
    contrast_score = float(np.clip((contrast - config.width_tile_min_contrast) / max(config.width_tile_good_contrast - config.width_tile_min_contrast, 1e-6), 0.0, 1.0))
    sharpness_score = float(np.clip((laplacian_variance - config.width_tile_min_laplacian) / max(config.width_tile_good_laplacian - config.width_tile_min_laplacian, 1e-6), 0.0, 1.0))
    exposure_score = float(np.clip(1.0 - exposure_penalty / 0.30, 0.0, 1.0))
    score = config.width_tile_min_weight + (1.0 - config.width_tile_min_weight) * (0.45 * contrast_score + 0.40 * sharpness_score + 0.15 * exposure_score)
    return {
        "score": float(score), "contrast": round(contrast, 4), "laplacian_variance": round(laplacian_variance, 4),
        "exposure_penalty": round(exposure_penalty, 5),
    }


def _gradient_peak_indices(gradient: np.ndarray, candidates: np.ndarray, limit: int) -> np.ndarray:
    """Return the strongest local gradient maxima without collapsing to one edge."""
    if len(candidates) == 0:
        return np.empty(0, dtype=int)
    magnitude = np.abs(gradient)
    peaks = [int(i) for i in candidates if 0 < i < len(gradient) - 1 and magnitude[i] >= magnitude[i - 1] and magnitude[i] >= magnitude[i + 1]]
    if not peaks:
        peaks = [int(i) for i in candidates]
    peaks.sort(key=lambda i: float(magnitude[i]), reverse=True)
    # Suppress duplicate samples on the same blurred edge, while retaining distinct edges.
    selected: list[int] = []
    for index in peaks:
        if all(abs(index - prior) > 2 for prior in selected):
            selected.append(index)
        if len(selected) >= limit:
            break
    return np.asarray(selected, dtype=int)


def _subpixel_peak_offset(magnitude: np.ndarray, index: int) -> float:
    """Fit a parabola around one gradient maximum and return its fractional shift."""
    if index <= 0 or index >= len(magnitude) - 1:
        return 0.0
    left, centre, right = float(magnitude[index - 1]), float(magnitude[index]), float(magnitude[index + 1])
    denominator = left - 2.0 * centre + right
    if abs(denominator) < 1e-9:
        return 0.0
    return float(np.clip(0.5 * (left - right) / denominator, -0.5, 0.5))


def edge_pair_candidates(
    offsets: np.ndarray,
    values: np.ndarray,
    min_width_px: float,
    candidates_per_side: int = 4,
) -> list[dict]:
    """Generate credible left/right edge pairs around a known centre point.

    A single strongest gradient per side is vulnerable to fibre texture.  This keeps
    several local peaks, requires opposite edge polarity where available, and leaves
    the final choice to the direction-level consistency step.
    """
    if len(offsets) < 9:
        return []
    smooth = cv2.GaussianBlur(values.astype(np.float32).reshape(1, -1), (0, 0), 1.0).reshape(-1)
    step = float(np.median(np.diff(offsets)))
    gradient = np.gradient(smooth.astype(np.float64), step)
    magnitude = np.abs(gradient)
    left = np.flatnonzero(offsets <= -step)
    right = np.flatnonzero(offsets >= step)
    if len(left) == 0 or len(right) == 0:
        return []
    left_peaks = _gradient_peak_indices(gradient, left, candidates_per_side)
    right_peaks = _gradient_peak_indices(gradient, right, candidates_per_side)
    noise = float(np.median(magnitude) + 1.4826 * np.median(np.abs(magnitude - np.median(magnitude))))
    pairs: list[dict] = []
    for li in left_peaks:
        for ri in right_peaks:
            left_strength, right_strength = float(magnitude[li]), float(magnitude[ri])
            strength = min(left_strength, right_strength)
            left_offset = float(offsets[li] + _subpixel_peak_offset(magnitude, int(li)) * step)
            right_offset = float(offsets[ri] + _subpixel_peak_offset(magnitude, int(ri)) * step)
            width = float(right_offset - left_offset)
            if strength <= max(noise * 1.5, 1e-4) or width < min_width_px:
                continue
            balance = min(left_strength, right_strength) / max(left_strength, right_strength, 1e-9)
            opposite_polarity = float(gradient[li] * gradient[ri]) < 0.0
            # Opposite signed gradients are the expected entry/exit pair of one yarn.
            # Keep same-polarity pairs as weaker fallbacks for inverted or irregular imaging.
            polarity_score = 1.0 if opposite_polarity else 0.45
            pair_score = (strength / max(noise, 1e-6)) * (0.55 + 0.45 * balance) * polarity_score
            pairs.append({
                "left_offset_px": left_offset,
                "right_offset_px": right_offset,
                "width_px": width,
                "edge_strength": strength,
                "edge_balance": balance,
                "opposite_polarity": opposite_polarity,
                "pair_score": float(pair_score),
            })
    return sorted(pairs, key=lambda item: item["pair_score"], reverse=True)


def edge_pair_width(offsets: np.ndarray, values: np.ndarray, min_width_px: float) -> dict | None:
    """Compatibility helper returning the best local candidate edge pair."""
    candidates = edge_pair_candidates(offsets, values, min_width_px)
    return candidates[0] if candidates else None


def _select_consistent_pairs(candidates: list[dict], config: EngineConfig) -> list[dict]:
    """Choose one edge pair per profile using local evidence plus width consistency."""
    if not candidates:
        return []

    def select_group(group: list[dict]) -> list[dict]:
        scores = np.asarray([
            float(item["pair_score"]) * float(item.get("pitch_prior", 1.0)) * float(item.get("tile_score", 1.0))
            for item in group
        ], dtype=np.float64)
        max_score = max(float(np.max(scores)), 1e-9)
        widths = np.asarray([float(item["width_px"]) for item in group], dtype=np.float64)
        support = np.zeros(len(group), dtype=np.float64)
        for index, width in enumerate(widths):
            band = max(config.width_consistency_min_band_px, width * config.width_consistency_band_ratio)
            proximity = np.exp(-0.5 * ((widths - width) / band) ** 2)
            support[index] = float(np.sum((scores / max_score) * proximity))
        reference_width = float(widths[int(np.argmax(support))])
        selected: dict[int, dict] = {}
        for candidate in group:
            profile_index = int(candidate["profile_index"])
            width = float(candidate["width_px"])
            band = max(config.width_consistency_min_band_px, reference_width * config.width_consistency_band_ratio)
            agreement = float(np.exp(-0.5 * ((width - reference_width) / band) ** 2))
            combined = (1.0 - config.width_consistency_weight) * (float(candidate["pair_score"]) / max_score) + config.width_consistency_weight * agreement
            current = selected.get(profile_index)
            if current is None or combined > float(current["selection_score"]):
                selected[profile_index] = {**candidate, "selection_score": round(combined, 5), "width_reference_px": round(reference_width, 4)}
        return list(selected.values())

    return select_group(candidates)


def _summary(samples: list[dict], mm_per_px_normal: float, config: EngineConfig) -> dict:
    if not samples:
        return {"status": "FAIL", "reasons": ["WIDTH_NO_VALID_EDGE_PAIRS"], "valid_sample_count": 0, "valid_yarn_count": 0}
    widths = np.asarray([s["width_px"] for s in samples], dtype=np.float64)
    median = float(np.median(widths))
    mad = float(1.4826 * np.median(np.abs(widths - median)))
    tolerance = max(1.0, config.width_outlier_mad_scale * mad)
    filtered = [s for s in samples if abs(float(s["width_px"]) - median) <= tolerance]
    values = np.asarray([s["width_px"] for s in filtered], dtype=np.float64)
    yarn_count = len({int(s["yarn_index"]) for s in filtered})
    reasons: list[str] = []
    if len(filtered) < config.width_min_valid_samples:
        reasons.append("WIDTH_VALID_SAMPLE_COUNT_LOW")
    if yarn_count < config.width_min_valid_yarns:
        reasons.append("WIDTH_VALID_YARN_COUNT_LOW")
    p10, p50, p90 = np.percentile(values, [10, 50, 90]) if len(values) else (np.nan, np.nan, np.nan)
    if np.isfinite(p10) and p10 < config.width_gate_p10_px:
        reasons.append("WIDTH_P10_BELOW_GATE")
    status = "FAIL" if len(filtered) < config.width_min_valid_samples or yarn_count < config.width_min_valid_yarns else ("LOW_CONFIDENCE" if reasons else "PASS")
    return {
        "status": status,
        "reasons": reasons,
        "valid_sample_count": int(len(filtered)),
        "valid_yarn_count": int(yarn_count),
        "rejected_outlier_count": int(len(samples) - len(filtered)),
        "p10_px": round(float(p10), 4), "p50_px": round(float(p50), 4), "p90_px": round(float(p90), 4),
        "p10_mm": round(float(p10 * mm_per_px_normal), 5),
        "p50_mm": round(float(p50 * mm_per_px_normal), 5),
        "p90_mm": round(float(p90 * mm_per_px_normal), 5),
    }


def measure_apparent_widths(
    front: np.ndarray,
    transmission: np.ndarray,
    warp_seed: dict,
    weft_seed: dict,
    normalization: dict,
    mm_per_px_x: float,
    mm_per_px_y: float,
    config: EngineConfig = DEFAULT_CONFIG,
) -> dict:
    registration = estimate_reflection_registration(front, transmission, config)
    if registration["status"] == "FAIL":
        return {"status": "FAIL", "reasons": registration["reasons"], "registration": registration, "warp": None, "weft": None, "evidence": []}

    matrix = np.asarray(registration["matrix_transmission_to_reflection"], dtype=np.float32)
    gray = to_gray(front)
    evidence: list[dict] = []

    def measure_direction(seed: dict, direction_name: str) -> dict:
        theta = np.deg2rad(float(seed["line_direction_deg"]))
        normal = np.asarray([-np.sin(theta), np.cos(theta)], dtype=np.float32)
        normal /= max(float(np.linalg.norm(normal)), 1e-9)
        mm_normal = float(np.sqrt((normal[0] * mm_per_px_x) ** 2 + (normal[1] * mm_per_px_y) ** 2))
        spacing = float(seed["median_center_spacing_px"]) / float(normalization["resize_scale"])
        half_range = float(np.clip(spacing * 0.45, config.width_min_search_half_px, config.width_max_search_half_px))
        candidate_records: list[dict] = []
        profile_index = 0
        for yarn_index, line in enumerate(_source_centerlines(seed, normalization, matrix)):
            if len(line) < 4:
                continue
            indices = np.unique(np.linspace(1, len(line) - 2, config.width_samples_per_centerline).round().astype(int))
            for index in indices:
                point = line[index]
                if point[0] < half_range or point[1] < half_range or point[0] >= gray.shape[1] - half_range or point[1] >= gray.shape[0] - half_range:
                    continue
                offsets, profile = _sample_profile(gray, point, normal, half_range, config.width_profile_step_px)
                tile = _tile_quality(gray, point, config)
                pairs = edge_pair_candidates(
                    offsets, profile, config.width_min_sample_px, config.width_edge_candidates_per_side,
                )
                for pair in pairs:
                    # A sub-fibre texture edge can be sharp but cannot represent a yarn
                    # when it occupies only a tiny fraction of the measured centre pitch.
                    if spacing * config.width_min_spacing_ratio <= pair["width_px"] < spacing * 0.92:
                        pitch_prior = min(1.0, float(pair["width_px"]) / max(spacing * config.width_min_spacing_ratio, 1e-6))
                        candidate_records.append({
                            **pair, "profile_index": profile_index, "yarn_index": yarn_index,
                            "center_x": float(point[0]), "center_y": float(point[1]),
                            "normal_x": float(normal[0]), "normal_y": float(normal[1]),
                            "pitch_prior": float(pitch_prior),
                            "tile_score": float(tile["score"]), "tile_contrast": float(tile["contrast"]),
                            "tile_laplacian_variance": float(tile["laplacian_variance"]),
                        })
                profile_index += 1
        samples = _select_consistent_pairs(candidate_records, config)
        summary = _summary(samples, mm_normal, config)
        summary["candidate_edge_pair_count"] = int(len(candidate_records))
        summary["selected_profile_count"] = int(len(samples))
        summary["max_profiles_per_yarn"] = int(max((sum(int(item["yarn_index"]) == yarn for item in samples) for yarn in {int(item["yarn_index"]) for item in samples}), default=0))
        summary["high_quality_selected_tile_count"] = int(sum(item.get("tile_score", 0.0) >= 0.65 for item in samples))
        summary["selection_method"] = "TILE_QUALITY__MULTI_EDGE_PAIR__PITCH_CONSTRAINT__PROFILE_CONSISTENCY"
        for item in samples[:80]:
            item_normal = np.asarray([item["normal_x"], item["normal_y"]], dtype=np.float32)
            left = np.asarray([item["center_x"], item["center_y"]], dtype=np.float32) + item_normal * item["left_offset_px"]
            right = np.asarray([item["center_x"], item["center_y"]], dtype=np.float32) + item_normal * item["right_offset_px"]
            evidence.append({"direction": direction_name, "center": [round(item["center_x"], 2), round(item["center_y"], 2)], "edge_left": [round(float(left[0]), 2), round(float(left[1]), 2)], "edge_right": [round(float(right[0]), 2), round(float(right[1]), 2)], "width_px": round(float(item["width_px"]), 3), "edge_strength": round(float(item["edge_strength"]), 5), "tile_score": round(float(item.get("tile_score", 0.0)), 4), "tile_contrast": round(float(item.get("tile_contrast", 0.0)), 3), "tile_laplacian_variance": round(float(item.get("tile_laplacian_variance", 0.0)), 3)})
        return {**summary, "measurement_method": "TRANSMISSION_CENTERLINE__REFLECTION_NORMAL_GRADIENT_PAIR", "search_half_range_px": round(half_range, 3), "mm_per_px_normal": round(mm_normal, 7)}

    warp = measure_direction(warp_seed, "warp")
    weft = measure_direction(weft_seed, "weft")
    reasons = [f"WARP_{reason}" for reason in warp["reasons"]] + [f"WEFT_{reason}" for reason in weft["reasons"]]
    status = "FAIL" if warp["status"] == "FAIL" or weft["status"] == "FAIL" else ("LOW_CONFIDENCE" if reasons else "PASS")
    return {"status": status, "reasons": reasons, "registration": registration, "warp": warp, "weft": weft, "evidence": evidence}
