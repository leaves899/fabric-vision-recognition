from __future__ import annotations

import cv2
import numpy as np

from .config import EngineConfig, DEFAULT_CONFIG
from .preprocess import crop_roi, local_normalize, resize_max_side, to_gray


def normalize_transmission(
    image: np.ndarray,
    config: EngineConfig = DEFAULT_CONFIG,
) -> tuple[np.ndarray, dict]:
    """③ 几何 + 光照归一化。

    当前 PoC 没有真实 Camera Profile / Homography 输入，不能伪造透视校正。
    固定工位、近似正视时几何矩阵使用 identity，并在 metadata 中明确标记。
    光照归一化使用 CLAHE Local Normalization。
    """
    roi, roi_meta = crop_roi(image, config.roi_ratio)
    gray = to_gray(roi)
    gray, scale = resize_max_side(gray, config.density_max_side)
    normalized = local_normalize(gray)
    return normalized, {
        "roi": roi_meta,
        "resize_scale": float(scale),
        "geometry_mode": "IDENTITY_FIXED_STATION_POC",
        "homography_applied": False,
        "local_normalization": "CLAHE",
    }
