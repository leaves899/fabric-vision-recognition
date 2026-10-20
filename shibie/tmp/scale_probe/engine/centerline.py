from __future__ import annotations

import numpy as np

from .config import EngineConfig, DEFAULT_CONFIG


def _fit_with_evidence_inliers(pts: np.ndarray, min_spacing_px: float, config: EngineConfig):
    """只剔除几何上明显不属于该中心线的已检测 Ridge 点，不补点。"""
    xs, ys = pts[:, 0], pts[:, 1]
    mask = np.ones(len(pts), dtype=bool)
    # 阈值受 PoC residual 上限与物理最小纱间距共同约束，防止无限放宽。
    point_thr = max(2.0, min(float(config.ridge_max_residual_px), float(min_spacing_px) * 0.34))

    for _ in range(2):
        if int(np.sum(mask)) < 4:
            return None
        slope, intercept = np.polyfit(ys[mask], xs[mask], 1)
        err = xs - (slope * ys + intercept)
        med = float(np.median(err[mask]))
        mad = float(1.4826 * np.median(np.abs(err[mask] - med)))
        # MAD 只能收紧/适度调整，不允许把阈值膨胀到很大后把噪声也收进来。
        robust_thr = point_thr if mad < 1e-6 else min(point_thr, max(2.0, 2.8 * mad))
        new_mask = np.abs(err - med) <= robust_thr
        if np.array_equal(new_mask, mask):
            break
        mask = new_mask

    if int(np.sum(mask)) < 4:
        return None
    slope, intercept = np.polyfit(ys[mask], xs[mask], 1)
    pred = slope * ys[mask] + intercept
    residual = float(np.sqrt(np.mean((xs[mask] - pred) ** 2)))
    if residual > point_thr:
        return None
    return float(slope), float(intercept), residual, mask


def clean_centerlines(
    raw_tracks: list[dict],
    sampled_rows: int,
    min_spacing_px: float,
    config: EngineConfig = DEFAULT_CONFIG,
) -> dict:
    """Centerline Cleaning（证据驱动版）。

    原则：可以剔除错误 Ridge 点，但不为追求“出结果”而补造中心线点。
    coverage 使用真正通过几何一致性检查的 inlier Ridge 数量计算。
    """
    candidates = []
    min_points = max(4, int(np.ceil(float(config.ridge_min_coverage) * max(sampled_rows, 1))))

    for tr in raw_tracks:
        pts = np.asarray(tr.get("points", []), dtype=np.float64)
        if len(pts) < min_points or pts.ndim != 2 or pts.shape[1] < 2:
            continue
        pts = pts[:, :2]
        if np.ptp(pts[:, 1]) < 1e-6:
            continue

        fit = _fit_with_evidence_inliers(pts, min_spacing_px, config)
        if fit is None:
            continue
        slope, intercept, residual, inliers = fit
        inlier_pts = pts[inliers]
        coverage = len(inlier_pts) / max(sampled_rows, 1)
        if coverage < config.ridge_min_coverage:
            continue

        # 全局 seed 来自整幅 ROI 沿纱线方向的稳健聚合，是中心位置的主证据；
        # Strip 级点只验证连续性与几何一致性，不允许局部组织纹把中心线整体拖偏。
        y_mid = float(np.median(inlier_pts[:, 1]))
        fit_center = float(slope * y_mid + intercept)
        seed_x = float(tr.get("seed_x", fit_center))
        # 仅在局部实测点与全局 seed 一致时做极小幅精修，否则保留 global seed。
        refine_limit = max(1.0, min(3.0, float(min_spacing_px) * 0.18))
        x_center = float(seed_x + np.clip(fit_center - seed_x, -refine_limit, refine_limit) * 0.25)
        support = float(tr.get("mean_peak_prominence", 0.0))
        profile_contrast = float(tr.get("mean_profile_contrast", 0.0))
        candidates.append({
            "x": x_center,
            "coverage": float(coverage),
            "residual_px": float(residual),
            "slope_dx_dy": float(slope),
            "point_count": int(len(inlier_pts)),
            "raw_point_count": int(len(pts)),
            "inlier_ratio": float(len(inlier_pts) / max(len(pts), 1)),
            "mean_peak_prominence": support,
            "mean_profile_contrast": profile_contrast,
            "seed_x": seed_x,
            "fit_center_x": fit_center,
            "points": [(float(x), float(y)) for x, y in inlier_pts],
        })

    if len(candidates) < config.min_valid_centerlines:
        raise ValueError("INSUFFICIENT_VALID_CENTERLINES")

    # Evidence-based NMS：只合并小于物理最小间距约 40% 的近重复中心线。
    candidates.sort(key=lambda c: c["x"])
    dedupe_dist = max(1.8, float(min_spacing_px) * config.centerline_dedupe_ratio)
    deduped: list[dict] = []
    for c in candidates:
        if not deduped or c["x"] - deduped[-1]["x"] >= dedupe_dist:
            deduped.append(c)
            continue
        prev = deduped[-1]
        # 选择证据覆盖更多、拟合残差更小的真实轨迹。
        prev_score = 1.15 * prev["coverage"] + 0.15 * prev["inlier_ratio"] - 0.035 * prev["residual_px"] + 0.05 * prev["mean_peak_prominence"]
        cur_score = 1.15 * c["coverage"] + 0.15 * c["inlier_ratio"] - 0.035 * c["residual_px"] + 0.05 * c["mean_peak_prominence"]
        if cur_score > prev_score:
            deduped[-1] = c

    if len(deduped) < config.min_valid_centerlines:
        raise ValueError("INSUFFICIENT_VALID_CENTERLINES")

    # A second, data-driven duplicate check catches two peaks inside one broad
    # yarn even when they are farther apart than the physical NMS distance.
    # Keep the candidate with stronger cross-strip evidence.
    def evidence_score(item: dict) -> float:
        return (
            1.20 * float(item["coverage"])
            + 0.25 * float(item["inlier_ratio"])
            + 0.06 * float(item["mean_peak_prominence"])
            + 0.20 * float(item.get("mean_profile_contrast", 0.0))
            - 0.04 * float(item["residual_px"])
        )

    relative_gap_removed = 0
    for _ in range(max(1, len(deduped))):
        if len(deduped) <= config.min_valid_centerlines:
            break
        positions_probe = np.asarray([item["x"] for item in deduped], dtype=np.float64)
        gaps = np.diff(positions_probe)
        if len(gaps) < 3:
            break
        reference_gap = float(np.median(gaps))
        close = np.flatnonzero(gaps < reference_gap * float(config.centerline_min_relative_gap))
        if len(close) == 0:
            break
        current_cv = float(np.std(gaps) / (np.mean(gaps) + 1e-9))
        accepted = None
        # 从最短的疑似双线开始寻找；一对无效不阻止检查其他过密对。
        for index in close[np.argsort(gaps[close])]:
            index = int(index)
            remove = index if evidence_score(deduped[index]) < evidence_score(deduped[index + 1]) else index + 1
            proposed = deduped[:remove] + deduped[remove + 1:]
            proposed_gaps = np.diff(np.asarray([item["x"] for item in proposed], dtype=np.float64))
            proposed_median = float(np.median(proposed_gaps))
            proposed_cv = float(np.std(proposed_gaps) / (np.mean(proposed_gaps) + 1e-9))
            # 删除一条疑似重复线必须使主测量间距增大，且不能令整体间距更不稳定。
            # 否则会改变中位数的取样位置并反而抬高密度，不能视为有效去重。
            if proposed_median >= reference_gap * 1.01 and proposed_cv <= current_cv + 0.05:
                accepted = proposed
                break
        if accepted is None:
            break
        deduped = accepted
        relative_gap_removed += 1

    if len(deduped) < config.min_valid_centerlines:
        raise ValueError("INSUFFICIENT_VALID_CENTERLINES")

    positions = np.asarray([c["x"] for c in deduped], dtype=np.float64)
    diffs = np.diff(positions)
    if len(diffs) < 3:
        raise ValueError("INSUFFICIENT_CENTER_SPACINGS")

    spacing_p50 = float(np.median(diffs))
    if spacing_p50 <= 0:
        raise ValueError("CENTER_SPACING_INVALID")

    # 不“修复”漏线/双线造成的间距，只把它们作为不稳定性证据交给 Gate 3。
    spacing_cv = float(np.std(diffs) / (np.mean(diffs) + 1e-9))
    mad = float(1.4826 * np.median(np.abs(diffs - spacing_p50)))
    robust_spacing_cv = float(mad / (spacing_p50 + 1e-9))
    gap_outlier_thr = max(0.35 * spacing_p50, 3.0 * mad)
    gap_outliers = np.abs(diffs - spacing_p50) > gap_outlier_thr

    return {
        "centerlines": deduped,
        "center_positions_px": positions,
        "valid_centerline_count": int(len(deduped)),
        "median_center_spacing_px": float(spacing_p50),
        "spacing_cv": float(spacing_cv),
        "robust_spacing_cv": float(robust_spacing_cv),
        "mean_coverage": float(np.mean([c["coverage"] for c in deduped])),
        "mean_inlier_ratio": float(np.mean([c["inlier_ratio"] for c in deduped])),
        "mean_profile_contrast": float(np.mean([c.get("mean_profile_contrast", 0.0) for c in deduped])),
        "outlier_gap_count": int(np.sum(gap_outliers)),
        "dedupe_distance_px": float(dedupe_dist),
        "relative_gap_removed_count": int(relative_gap_removed),
    }
