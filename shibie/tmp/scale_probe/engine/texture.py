from __future__ import annotations

import cv2
import numpy as np

from .preprocess import (
    to_gray, center_crop, resize_max_side, local_normalize
)


TEXTURE_CLASSES = [
    "斜纹清晰 / 经向纹路明显",
    "竹节明显 / 粗纱",
    "细密轻量 / 均匀",
    "磨毛 / 绒面",
    "颗粒 / 凹凸",
    "其他 / 待确认",
]


def classify_surface_texture(front_image: np.ndarray) -> dict:
    """V0.4 保守型表面纹理规则。

    现有报告没有给这 6 类冻结算法和验收数据，所以这里不能把弱规则
    包装成“正式分类器”。只有斜纹方向证据较明确时输出具体类别；
    其余情况优先输出“其他 / 待确认”，避免错误自信。
    """
    gray = to_gray(front_image)
    gray = center_crop(gray, 0.82)
    gray, _ = resize_max_side(gray, 1200)
    gray = local_normalize(gray)

    f = gray.astype(np.float32) / 255.0
    gx = cv2.Sobel(f, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(f, cv2.CV_32F, 0, 1, ksize=3)
    mag = np.sqrt(gx * gx + gy * gy)

    theta = (
        np.degrees(np.arctan2(gy, gx)) + 90.0
    ) % 180.0
    strong = mag > np.quantile(mag, 0.78)

    dominant = 0.0
    dom_angle = 0.0
    if np.any(strong):
        vals = theta[strong]
        hist, _ = np.histogram(
            vals, bins=72, range=(0.0, 180.0)
        )
        hist = hist.astype(np.float64)
        hist /= hist.sum() + 1e-12
        idx = int(np.argmax(hist))
        dominant = float(hist[idx])
        dom_angle = float((idx + 0.5) * 2.5)

    diagonal_dist = min(
        abs(dom_angle - 45.0),
        abs(dom_angle - 135.0)
    )

    if diagonal_dist <= 13.0 and dominant >= 0.035:
        label = TEXTURE_CLASSES[0]
        confidence = "MEDIUM"
        reason = "DIAGONAL_ORIENTATION_EVIDENCE"
    else:
        label = TEXTURE_CLASSES[-1]
        confidence = "LOW"
        reason = "NO_VALIDATED_RULE_FOR_SPECIFIC_TEXTURE"

    return {
        "label": label,
        "confidence": confidence,
        "mode": "conservative_rules_v0.4",
        "reason": reason,
        "features": {
            "dominant_line_angle_deg": round(dom_angle, 2),
            "orientation_dominance": round(dominant, 4),
        },
    }
