from __future__ import annotations

import cv2
import numpy as np

from .config import EngineConfig, DEFAULT_CONFIG


def assess_scale_consistency(attempts: list[dict], selected: dict, config: EngineConfig = DEFAULT_CONFIG) -> dict:
    """核验同方向内质量接近的 Steerable 候选是否给出一致密度。

    这是候选质量控制，不参与中心线清洗或双路径密度计算。候选间分歧说明
    图像尺度证据不足，应由可信度层明确标记，而不是按较低数值强行改写结果。
    """
    selected_quality = float(selected["candidate_quality"])
    selected_density = float(selected["density"]["density_per_cm"])
    close = [
        item for item in attempts
        if item["_base_confidence_status"] != "FAIL"
        and abs(float(item["candidate_quality"]) - selected_quality) <= config.steerable_quality_close_margin
    ]
    if len(close) < 2:
        return {
            "status": "NOT_AVAILABLE",
            "reason": "INSUFFICIENT_QUALITY_CLOSE_SCALE_CANDIDATES",
            "candidate_count": len(close),
        }

    densities = [float(item["density"]["density_per_cm"]) for item in close]
    low, high = min(densities), max(densities)
    difference_pct = (high - low) / max((high + low) * 0.5, 1e-9) * 100.0
    contenders = [
        {
            "response_key": item["steerable"]["response_key"],
            "sigma": float(item["steerable"]["selected_sigma"]),
            "polarity": item["steerable"]["selected_polarity"],
            "density_per_cm": round(float(item["density"]["density_per_cm"]), 4),
            "candidate_quality": float(item["candidate_quality"]),
        }
        for item in close
    ]
    return {
        "status": "AVAILABLE",
        "candidate_count": len(close),
        "selected_density_per_cm": round(selected_density, 4),
        "density_min_per_cm": round(low, 4),
        "density_max_per_cm": round(high, 4),
        "density_difference_pct": round(difference_pct, 4),
        "disagreement": difference_pct > config.steerable_density_disagreement_low_pct,
        "quality_margin": config.steerable_quality_close_margin,
        "candidates": contenders,
    }


def _hessian_basis(gray: np.ndarray, sigma: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    f = gray.astype(np.float32) / 255.0
    k = int(max(3, round(sigma * 6))) | 1
    smooth = cv2.GaussianBlur(f, (k, k), sigmaX=sigma, sigmaY=sigma)
    hxx = cv2.Sobel(smooth, cv2.CV_32F, 2, 0, ksize=3)
    hxy = cv2.Sobel(smooth, cv2.CV_32F, 1, 1, ksize=3)
    hyy = cv2.Sobel(smooth, cv2.CV_32F, 0, 2, ksize=3)
    return hxx, hxy, hyy


def _normalize_response(response: np.ndarray) -> np.ndarray:
    p = float(np.quantile(response, 0.995))
    if p > 1e-9:
        response = np.clip(response / p, 0.0, 1.0)
    return response.astype(np.float32)


def steerable_filter_bank(normalized_gray: np.ndarray, line_direction_deg: float, config: EngineConfig = DEFAULT_CONFIG) -> dict:
    """多尺度 Steerable Filter Bank。

    每个尺度分别保留响应，不再先做跨尺度 max，避免细小表面纹理把真实纱线周期淹没。
    dark/bright 两种极性均作为同一路线候选，后续由 Ridge/Centerline 质量选择。
    """
    responses: dict[str, np.ndarray] = {}
    response_meta: dict[str, dict] = {}
    for sigma in config.steerable_sigmas:
        hxx, hxy, hyy = _hessian_basis(normalized_gray, sigma)
        dark_bank, bright_bank = [], []
        for off in config.steerable_offsets_deg:
            line = (float(line_direction_deg) + off) % 180.0
            normal = np.deg2rad((line + 90.0) % 180.0)
            nx, ny = float(np.cos(normal)), float(np.sin(normal))
            dnn = nx * nx * hxx + 2.0 * nx * ny * hxy + ny * ny * hyy
            dark_bank.append(np.maximum(dnn, 0.0))
            bright_bank.append(np.maximum(-dnn, 0.0))
        for polarity, stack in (("dark", dark_bank), ("bright", bright_bank)):
            key = f"{polarity}@{sigma:g}"
            responses[key] = _normalize_response(np.max(np.stack(stack, axis=0), axis=0))
            response_meta[key] = {"polarity": polarity, "sigma": float(sigma)}
    return {
        "responses": responses,
        "response_meta": response_meta,
        "sigmas": list(config.steerable_sigmas),
        "offsets_deg": list(config.steerable_offsets_deg),
        "line_direction_deg": float(line_direction_deg),
    }
