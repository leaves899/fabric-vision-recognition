"""Quality, explicit ROI/homography, paired registration and calibration."""
from __future__ import annotations

import cv2
import numpy as np
from scipy.ndimage import gaussian_filter

from .primitives import grayscale


def quality(rgb, cfg):
    gray = grayscale(rgb)
    u8 = np.uint8(np.clip(gray * 255, 0, 255))
    lap = float(cv2.Laplacian(u8, cv2.CV_64F).var())
    gx = cv2.Sobel(u8, cv2.CV_32F, 1, 0)
    gy = cv2.Sobel(u8, cv2.CV_32F, 0, 1)
    ten = float(np.mean(gx * gx + gy * gy))
    clipped = float(np.mean((gray <= .01) | (gray >= .99)))
    contrast = float(np.std(gray))
    reasons = []
    if min(gray.shape) < cfg.min_side:
        reasons.append("resolution_below_exploratory_minimum")
    if contrast < cfg.min_contrast:
        reasons.append("insufficient_contrast")
    if lap < cfg.min_laplacian_variance or ten < cfg.min_tenengrad:
        reasons.append("insufficient_gradient_sharpness")
    if clipped > cfg.max_clipped_fraction:
        reasons.append("too_many_clipped_pixels")
    return dict(status="PASS" if not reasons else "LOW_CONFIDENCE", reasons=reasons,
                laplacian_variance=lap, tenengrad=ten, contrast=contrast,
                clipped_fraction=clipped, histogram=np.bincount(u8.ravel(), minlength=256).tolist(),
                scope="image diagnostics; no optical resolution certification")


def rectify(rgb, corners=None, target_size=None, roi=None):
    h, w = rgb.shape[:2]
    matrix = np.eye(3)
    if corners is not None:
        points = np.asarray(corners, dtype=np.float32)
        if points.shape != (4, 2) or not np.isfinite(points).all():
            raise ValueError("Corners must be four finite TL,TR,BR,BL points")
        if np.any(points[:, 0] < 0) or np.any(points[:, 0] >= w) or np.any(points[:, 1] < 0) or np.any(points[:, 1] >= h):
            raise ValueError("Corners outside image")
        if not cv2.isContourConvex(points) or cv2.contourArea(points, oriented=True) < 64:
            raise ValueError("Corners must describe a nondegenerate convex quadrilateral")
        if target_size is None:
            raise ValueError("Rectification requires explicit target_size (width,height)")
        if len(target_size) != 2 or any(not np.isfinite(v) or int(v) != v for v in target_size):
            raise ValueError("target_size requires two integer dimensions")
        tw, th = map(int, target_size)
        if min(tw, th) < 64 or max(tw, th) > 1200:
            raise ValueError("Rectified target dimensions must be 64..1200")
        target = np.float32([[0, 0], [tw - 1, 0], [tw - 1, th - 1], [0, th - 1]])
        matrix = cv2.getPerspectiveTransform(points, target)
        rgb = cv2.warpPerspective(rgb, matrix, (tw, th))
    if roi is not None:
        if len(roi) != 4 or any(not np.isfinite(v) or int(v) != v for v in roi):
            raise ValueError("ROI requires four integer coordinates")
        x, y, rw, rh = map(int, roi)
        h, w = rgb.shape[:2]
        if min(x, y) < 0 or min(rw, rh) < 64 or x + rw > w or y + rh > h:
            raise ValueError("ROI outside image or smaller than 64px")
        rgb = rgb[y:y + rh, x:x + rw].copy()
        matrix = np.array([[1., 0, -x], [0, 1., -y], [0, 0, 1.]]) @ matrix
    return rgb, matrix


def _registration_image(rgb):
    gray = grayscale(rgb)
    # Local normalization preserves float boundaries across the illumination pair.
    mean = gaussian_filter(gray, 9)
    var = np.maximum(gaussian_filter(gray * gray, 9) - mean * mean, 0)
    return np.float32(np.clip((gray - mean) / np.sqrt(var + .025 ** 2), -3, 3))


def register_pair(front, back, cfg, prealigned=False):
    if front.shape != back.shape:
        raise ValueError("Pair must have equal ROI dimensions after rectification")
    h, w = front.shape[:2]
    a, b = _registration_image(front), _registration_image(back)
    scale = min(1., 512 / max(h, w))
    aa = cv2.resize(a, None, fx=scale, fy=scale)
    bb = cv2.resize(b, None, fx=scale, fy=scale)
    ecc = None
    matrix = np.eye(3, dtype=np.float32)
    errors = []
    if not prealigned:
        try:
            ecc, low = cv2.findTransformECC(aa, bb, matrix.copy(), cv2.MOTION_HOMOGRAPHY,
                                           (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 120, 1e-5),
                                           None, 5)
            s = np.diag([scale, scale, 1.])
            matrix = np.linalg.inv(s) @ low @ s
            corners = np.float32([[[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]]])
            moved = cv2.perspectiveTransform(corners, matrix)[0]
            if not np.isfinite(matrix).all() or np.max(np.linalg.norm(moved - corners[0], axis=1)) > cfg.max_registration_shift_fraction * min(h, w):
                raise ValueError("ECC transform displacement exceeds allowed fraction")
        except (cv2.error, ValueError) as exc:
            errors.append("registration_estimation_failed: " + str(exc).splitlines()[0])
            matrix = np.eye(3)
    aligned = cv2.warpPerspective(back, matrix, (w, h), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP)
    valid = cv2.warpPerspective(np.ones((h, w), np.uint8), matrix, (w, h),
                                flags=cv2.INTER_NEAREST | cv2.WARP_INVERSE_MAP) > 0
    aligned_normal = _registration_image(aligned)
    checks = []
    radius = max(16, min(h, w) // 12)
    for fy in (.25, .5, .75):
        for fx in (.25, .5, .75):
            x, y = int(w * fx), int(h * fy)
            p = a[y - radius:y + radius, x - radius:x + radius]
            q = aligned_normal[y - radius:y + radius, x - radius:x + radius]
            mask = valid[y - radius:y + radius, x - radius:x + radius]
            if mask.mean() < .98 or np.std(p) < .05 or np.std(q) < .05:
                continue
            # OpenCV's odd optimal-DFT padding can add a half-pixel peak bias.
            # Explicit even optimal dimensions keep an identical pair at (0,0).
            dimensions = []
            for length in p.shape:
                candidate = cv2.getOptimalDFTSize(length)
                while candidate % 2:
                    candidate = cv2.getOptimalDFTSize(candidate + 1)
                dimensions.append(candidate)
            pp = np.pad(p, ((0, dimensions[0]-p.shape[0]), (0, dimensions[1]-p.shape[1])))
            qq = np.pad(q, ((0, dimensions[0]-q.shape[0]), (0, dimensions[1]-q.shape[1])))
            shift, response = cv2.phaseCorrelate(pp, qq)
            residual = float(np.hypot(*shift))
            checks.append(dict(center_xy=[x, y], residual_xy=list(shift), residual_px=residual,
                               response=float(response), reliable=bool(response >= .15)))
    reliable = [c for c in checks if c['reliable']]
    residual = float(np.median([c['residual_px'] for c in reliable])) if reliable else None
    if len(reliable) < 5:
        errors.append("insufficient_local_registration_evidence")
    if residual is None or residual > cfg.registration_max_residual_px:
        errors.append("local_registration_residual_too_large_or_unavailable")
    if ecc is not None and ecc < cfg.registration_min_ecc:
        errors.append("ECC_below_threshold")
    return aligned, valid, dict(status="PASS" if not errors else "LOW_CONFIDENCE", reasons=errors,
                               method="caller prealigned + independent local checks" if prealigned else "ECC homography + local phase correlation",
                               reference_to_moving_matrix=matrix.tolist(), ecc=float(ecc) if ecc is not None else None,
                               local_checks=checks, median_local_residual_px=residual,
                               caveat="Periodic repeats and illumination changes can defeat these diagnostics")


def calibration(mm_per_px=None, confirmed=False):
    if mm_per_px is not None and (not np.isfinite(mm_per_px) or mm_per_px <= 0):
        raise ValueError("mm_per_px must be finite and positive")
    return dict(status="CONFIRMED" if confirmed and mm_per_px else "UNCONFIRMED" if mm_per_px else "UNAVAILABLE",
                mm_per_px=float(mm_per_px) if confirmed and mm_per_px else None,
                candidate_mm_per_px=float(mm_per_px) if mm_per_px else None,
                evidence="explicit caller confirmation" if confirmed and mm_per_px else "no confirmed physical scale")
