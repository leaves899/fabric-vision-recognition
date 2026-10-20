from __future__ import annotations

import cv2
import numpy as np


def to_gray(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return image
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def resize_max_side(image: np.ndarray, max_side: int) -> tuple[np.ndarray, float]:
    h, w = image.shape[:2]
    m = max(h, w)
    if m <= max_side:
        return image, 1.0
    scale = max_side / float(m)
    out = cv2.resize(
        image,
        (max(1, int(round(w * scale))), max(1, int(round(h * scale)))),
        interpolation=cv2.INTER_AREA,
    )
    return out, scale


def crop_roi(image: np.ndarray, ratio: float = 0.82) -> tuple[np.ndarray, dict]:
    """PoC ROI。

    可行性路线中的 PoC 目标是人工选择有效织物 ROI；当前前端还未提供框选控件，
    因此这里使用明确标记的中心 ROI 作为临时 PoC 默认，不冒充自动织物分割。
    """
    h, w = image.shape[:2]
    cw = max(64, int(round(w * ratio)))
    ch = max(64, int(round(h * ratio)))
    x0 = max(0, (w - cw) // 2)
    y0 = max(0, (h - ch) // 2)
    roi = image[y0:y0 + ch, x0:x0 + cw]
    return roi, {
        "mode": "CENTER_ROI_POC_DEFAULT",
        "x": int(x0),
        "y": int(y0),
        "width": int(cw),
        "height": int(ch),
    }


def local_normalize(gray: np.ndarray) -> np.ndarray:
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    return clahe.apply(gray)


def rotate_keep_size(image: np.ndarray, angle_deg: float, border_value: float | tuple = 0) -> np.ndarray:
    h, w = image.shape[:2]
    center = (w / 2.0, h / 2.0)
    M = cv2.getRotationMatrix2D(center, angle_deg, 1.0)
    return cv2.warpAffine(
        image,
        M,
        (w, h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=border_value,
    )


def center_crop(image: np.ndarray, ratio: float = 0.82) -> np.ndarray:
    roi, _ = crop_roi(image, ratio)
    return roi
