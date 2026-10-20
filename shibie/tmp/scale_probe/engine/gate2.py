from __future__ import annotations

import cv2
import numpy as np

from .config import EngineConfig, DEFAULT_CONFIG
from .preprocess import to_gray, resize_max_side


def _metrics(image: np.ndarray) -> dict:
    gray = to_gray(image)
    small, _ = resize_max_side(gray, 1400)
    f = small.astype(np.float32)

    lap_var = float(cv2.Laplacian(small, cv2.CV_32F).var())
    gx = cv2.Sobel(f, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(f, cv2.CV_32F, 0, 1, ksize=3)
    tenengrad = float(np.mean(gx * gx + gy * gy))

    hist = cv2.calcHist([small], [0], None, [256], [0, 256]).ravel()
    hist /= max(float(hist.sum()), 1.0)
    dark_ratio = float(hist[:8].sum())
    bright_ratio = float(hist[248:].sum())

    return {
        "width": int(gray.shape[1]),
        "height": int(gray.shape[0]),
        "laplacian_variance": round(lap_var, 3),
        "tenengrad": round(tenengrad, 3),
        "dark_ratio": round(dark_ratio, 5),
        "bright_ratio": round(bright_ratio, 5),
    }


def _append_quality_reasons(
    prefix: str,
    metrics: dict,
    reasons: list[str],
    hard_reasons: set[str],
    config: EngineConfig,
) -> None:
    """Gate 2 单图质量判定。

    落地单口径：Gate 2 判断输入是否“具备计量条件”。
    因此普通质量下降不直接拒绝；只有严重失焦/严重曝光异常等
    明显不可计量状态才进入 hard_reasons。

    注意：以下阈值仍为 PoC 初始值，不是生产冻结参数。
    """
    lap = float(metrics["laplacian_variance"])
    ten = float(metrics["tenengrad"])

    # 模糊/细节：不再用单一 Laplacian < 10 直接 FAIL。
    # 只有 Laplacian 与 Tenengrad 同时落入严重区间，才判断严重失焦。
    if lap < config.gate2_blur_fail_laplacian and ten < config.gate2_detail_fail_tenengrad:
        code = f"{prefix}_IMAGE_SEVERELY_BLURRED"
        reasons.append(code)
        hard_reasons.add(code)
    else:
        if lap < config.gate2_blur_warn_laplacian:
            reasons.append(f"{prefix}_IMAGE_BLUR_WARNING")
        if ten < config.gate2_detail_warn_tenengrad:
            reasons.append(f"{prefix}_IMAGE_LOW_DETAIL")

    # 曝光：30%~60% 只预警；超过 60% 才视为严重不可计量。
    dark = float(metrics["dark_ratio"])
    bright = float(metrics["bright_ratio"])

    if dark > config.gate2_exposure_fail_ratio:
        code = f"{prefix}_IMAGE_SEVERELY_UNDEREXPOSED"
        reasons.append(code)
        hard_reasons.add(code)
    elif dark > config.gate2_exposure_warn_ratio:
        reasons.append(f"{prefix}_IMAGE_UNDEREXPOSURE_WARNING")

    if bright > config.gate2_exposure_fail_ratio:
        code = f"{prefix}_IMAGE_SEVERELY_OVEREXPOSED"
        reasons.append(code)
        hard_reasons.add(code)
    elif bright > config.gate2_exposure_warn_ratio:
        reasons.append(f"{prefix}_IMAGE_OVEREXPOSURE_WARNING")


def gate2(
    front: np.ndarray,
    transmission: np.ndarray,
    mm_per_px_x: float | None,
    mm_per_px_y: float | None,
    config: EngineConfig = DEFAULT_CONFIG,
) -> dict:
    reasons: list[str] = []
    hard_reasons: set[str] = set()

    if front is None or front.size == 0:
        reasons.append("FRONT_IMAGE_INVALID")
        hard_reasons.add("FRONT_IMAGE_INVALID")
    if transmission is None or transmission.size == 0:
        reasons.append("TRANSMISSION_IMAGE_INVALID")
        hard_reasons.add("TRANSMISSION_IMAGE_INVALID")
    if reasons:
        return {
            "status": "FAIL",
            "reasons": sorted(set(reasons)),
            "metrics": {},
            "threshold_profile": "POC_UNFROZEN_V0.6.2_GATE2_RELAXED",
        }

    fm = _metrics(front)
    tm = _metrics(transmission)

    if front.shape[:2] != transmission.shape[:2]:
        reasons.append("PAIR_IMAGE_SIZE_MISMATCH")
        hard_reasons.add("PAIR_IMAGE_SIZE_MISMATCH")

    if min(fm["width"], fm["height"], tm["width"], tm["height"]) < config.min_image_side:
        reasons.append("IMAGE_RESOLUTION_LOW")
        hard_reasons.add("IMAGE_RESOLUTION_LOW")

    if mm_per_px_x is None or mm_per_px_y is None or mm_per_px_x <= 0 or mm_per_px_y <= 0:
        reasons.append("MM_PER_PX_MISSING_OR_INVALID")
        hard_reasons.add("MM_PER_PX_MISSING_OR_INVALID")
    else:
        if mm_per_px_x > config.max_mm_per_px or mm_per_px_y > config.max_mm_per_px:
            reasons.append("MM_PER_PX_GATE_FAILED")
            hard_reasons.add("MM_PER_PX_GATE_FAILED")

    # 正面图与透射图仍然共同属于 Gate 2 标准输入；不采用“正面坏了仍发布密度”的例外逻辑。
    _append_quality_reasons("FRONT", fm, reasons, hard_reasons, config)
    _append_quality_reasons("TRANSMISSION", tm, reasons, hard_reasons, config)

    status = "FAIL" if hard_reasons else ("LOW_CONFIDENCE" if reasons else "PASS")
    return {
        "status": status,
        "reasons": sorted(set(reasons)),
        "metrics": {"front": fm, "transmission": tm},
        "threshold_profile": "POC_UNFROZEN_V0.6.2_GATE2_RELAXED",
        "thresholds": {
            "blur_warn_laplacian": config.gate2_blur_warn_laplacian,
            "blur_fail_laplacian": config.gate2_blur_fail_laplacian,
            "detail_warn_tenengrad": config.gate2_detail_warn_tenengrad,
            "detail_fail_tenengrad": config.gate2_detail_fail_tenengrad,
            "exposure_warn_ratio": config.gate2_exposure_warn_ratio,
            "exposure_fail_ratio": config.gate2_exposure_fail_ratio,
            "max_mm_per_px": config.max_mm_per_px,
        },
    }
