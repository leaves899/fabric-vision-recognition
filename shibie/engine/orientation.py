from __future__ import annotations

import cv2
import numpy as np
from scipy.ndimage import gaussian_filter, gaussian_filter1d
from scipy.signal import find_peaks

from .config import EngineConfig, DEFAULT_CONFIG
from .preprocess import resize_max_side


def angular_distance(a: float, b: float) -> float:
    d = abs(a - b) % 180.0
    return min(d, 180.0 - d)


def _refine_hist_angle(hist: np.ndarray, center: float) -> float:
    idx0 = int(round(center - 0.5)) % 180
    inds = [(idx0 + k) % 180 for k in range(-3, 4)]
    ws = np.asarray([hist[i] for i in inds], dtype=np.float64)
    angs = np.asarray([i + 0.5 for i in inds], dtype=np.float64)
    rad2 = np.deg2rad(angs * 2.0)
    xx = float(np.sum(ws * np.cos(rad2)))
    yy = float(np.sum(ws * np.sin(rad2)))
    if abs(xx) + abs(yy) < 1e-12:
        return float(center % 180.0)
    return float((np.rad2deg(np.arctan2(yy, xx)) / 2.0) % 180.0)


def structure_tensor_directions(
    normalized_gray: np.ndarray,
    config: EngineConfig = DEFAULT_CONFIG,
) -> dict:
    """Structure Tensor 局部方向场 + Top-N 方向候选。

    技术路线不变：Structure Tensor 负责提供纱线方向信息。
    V0.6.3 的变化只是“不让单次直方图峰值直接锁死经纬方向”，
    而是把候选交给 Steerable/Ridge/Centerline 同路线下游验证。
    """
    gray, _ = resize_max_side(normalized_gray, config.orientation_max_side)
    f = gray.astype(np.float32) / 255.0
    gx = cv2.Sobel(f, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(f, cv2.CV_32F, 0, 1, ksize=3)

    sigma = config.tensor_sigma
    jxx = gaussian_filter(gx * gx, sigma=sigma)
    jyy = gaussian_filter(gy * gy, sigma=sigma)
    jxy = gaussian_filter(gx * gy, sigma=sigma)

    energy = jxx + jyy
    coherence = np.sqrt((jxx - jyy) ** 2 + 4.0 * jxy * jxy) / (energy + 1e-8)
    grad_theta = 0.5 * np.arctan2(2.0 * jxy, jxx - jyy)
    line_theta = (np.degrees(grad_theta) + 90.0) % 180.0

    e_thr = float(np.quantile(energy, config.tensor_energy_quantile))
    mask = (energy >= e_thr) & (coherence >= config.tensor_min_coherence)
    vals = line_theta[mask]
    weights = (energy[mask] * coherence[mask]).astype(np.float64)
    if vals.size < 100:
        raise ValueError("ORIENTATION_INSUFFICIENT_SIGNAL")

    hist, _ = np.histogram(vals, bins=180, range=(0.0, 180.0), weights=weights)
    hist = gaussian_filter1d(hist.astype(np.float64), sigma=2.0, mode="wrap")

    # 环形直方图上的局部峰。find_peaks 不懂 wrap，所以把直方图三份拼接后取中段。
    ext = np.concatenate([hist, hist, hist])
    peaks, props = find_peaks(
        ext,
        distance=max(2, int(config.orientation_peak_min_distance_deg)),
        prominence=max(float(np.max(hist)) * 0.018, 1e-12),
    )
    cand = []
    for p in peaks:
        if 180 <= p < 360:
            idx = p - 180
            angle = _refine_hist_angle(hist, float(idx + 0.5))
            strength = float(hist[idx])
            cand.append((strength, angle))

    if not cand:
        idx = int(np.argmax(hist))
        cand = [(float(hist[idx]), _refine_hist_angle(hist, float(idx + 0.5)))]

    # 去掉过近重复峰，保留 Top-N。
    cand.sort(reverse=True, key=lambda x: x[0])
    unique: list[tuple[float, float]] = []
    for strength, angle in cand:
        if all(angular_distance(angle, a) >= 6.0 for _, a in unique):
            unique.append((strength, angle))
        if len(unique) >= config.orientation_candidate_count:
            break

    # 每个强方向都补一个理论正交候选。它不是替代方向算法，只是给下游验证一个候选，
    # 防止斜纹表面方向压过较弱的另一组经/纬纱方向。
    augmented = list(unique)
    for strength, angle in unique[:4]:
        orth = (angle + 90.0) % 180.0
        if all(angular_distance(orth, a) >= 6.0 for _, a in augmented):
            augmented.append((strength * 0.55, orth))
    augmented.sort(reverse=True, key=lambda x: x[0])
    augmented = augmented[: max(config.orientation_candidate_count, 10)]

    # Keep a compact sampling of the already-computed local field for Evidence.
    # This is diagnostic output only and does not participate in direction choice.
    field_samples = []
    sample_step = max(1, int(min(gray.shape) / 24))
    for y in range(sample_step // 2, gray.shape[0], sample_step):
        for x in range(sample_step // 2, gray.shape[1], sample_step):
            if not bool(mask[y, x]):
                continue
            field_samples.append({
                "x": int(x), "y": int(y),
                "angle_deg": round(float(line_theta[y, x]), 3),
                "coherence": round(float(coherence[y, x]), 4),
            })

    # 给出一个初始近正交 pair，最终 pair 由 pipeline 下游验证选择。
    pairs = []
    max_strength = max(s for s, _ in augmented) + 1e-12
    for i in range(len(augmented)):
        for j in range(i + 1, len(augmented)):
            s1, a1 = augmented[i]
            s2, a2 = augmented[j]
            gap = angular_distance(a1, a2)
            if config.orientation_pair_gap_min_deg <= gap <= config.orientation_pair_gap_max_deg:
                orth_score = max(0.0, 1.0 - abs(gap - 90.0) / 20.0)
                hist_score = (s1 + s2) / (2.0 * max_strength)
                pairs.append((0.62 * hist_score + 0.38 * orth_score, a1, a2, gap))
    if not pairs:
        raise ValueError("SECOND_DIRECTION_NOT_FOUND")
    pairs.sort(reverse=True, key=lambda x: x[0])
    _, a, b, gap = pairs[0]

    return {
        "direction_a_deg": round(float(a), 3),
        "direction_b_deg": round(float(b), 3),
        "angle_gap_deg": round(float(gap), 3),
        "mean_coherence": round(float(np.mean(coherence[mask])), 4),
        "valid_orientation_pixels": int(vals.size),
        "field_shape": [int(gray.shape[1]), int(gray.shape[0])],
        "direction_field_samples": field_samples[:900],
        "direction_candidates": [
            {"angle_deg": round(float(a), 3), "strength": round(float(s / max_strength), 5)}
            for s, a in augmented
        ],
    }


def map_warp_weft(a: float, b: float, warp_axis_hint: str = "vertical") -> dict:
    if warp_axis_hint not in ("vertical", "horizontal"):
        raise ValueError("WARP_AXIS_HINT_INVALID")
    target = 90.0 if warp_axis_hint == "vertical" else 0.0
    da = angular_distance(a, target)
    db = angular_distance(b, target)
    ambiguous = abs(da - db) < 7.0
    if da <= db:
        warp, weft = float(a), float(b)
    else:
        warp, weft = float(b), float(a)
    return {
        "warp_direction_deg": warp,
        "weft_direction_deg": weft,
        "mapping_ambiguous": bool(ambiguous),
        "warp_axis_hint": warp_axis_hint,
        "distance_a_to_hint_deg": round(da, 3),
        "distance_b_to_hint_deg": round(db, 3),
    }
