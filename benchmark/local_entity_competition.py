"""G1 local physical-entity evidence with explicit competing hypotheses.

This module does not modify or call the frozen V4/V5 implementation.  It uses
the archived *original* phone photo bytes for every measurement.  Coordinates
from the 2x annotation image are only mapped back to the original crop.

A1/A2 and their operator-confirmed interval count calibrate the A-family
geometry.  B1/B2 only locate possible interlacing crossings.  A3 is not read
until :func:`evaluate_a3_holdout`, after all image features and candidates are
frozen.  A human two-point trajectory is not a visible-pixel mask, so the
experiment can propose auditable evidence but cannot certify yarn pixels on
its own.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np

from benchmark.manual_annotation import validate_annotation


ROOT = Path(__file__).resolve().parents[1]
PRIMARY_SAMPLES = ("U20261013_01", "U20261013_03", "U20261013_06")
DEVELOPMENT_FABRICS = frozenset(("U20261013_01", "U20261013_03"))
INDEPENDENT_FABRICS = frozenset(
    ("U20261013_02", "U20261013_05", "U20261013_06")
)

# Fixed after inspection of A1/A2 calibration evidence on 01/03.  A3 never
# enters these weights or thresholds.  Values are intentionally conservative:
# uncertain competition must abstain.
FEATURE_WEIGHTS = {
    "paired_boundary": 0.18,
    "width_consistency": 0.12,
    "visible_continuity": 0.14,
    "axis_coherence": 0.12,
    "anchor_polarity": 0.08,
    "anchor_morphology": 0.26,
    "occlusion_resumption": 0.10,
}
MIN_COMPETITION_MARGIN = 0.10
MIN_ENTITY_SCORE = 0.48
MIN_LATTICE_VS_HALF_PHASE_MEDIAN_MARGIN = 0.20


def _axial_distance(a: float, b: float) -> float:
    return abs((a - b + 90.0) % 180.0 - 90.0)


def _line_axis(segment: Iterable[Iterable[float]]) -> float:
    p = np.asarray(segment, np.float64)
    delta = p[1] - p[0]
    return float(math.degrees(math.atan2(delta[1], delta[0])) % 180.0)


def _signed_axis(segment: Iterable[Iterable[float]]) -> float:
    p = np.asarray(segment, np.float64)
    delta = p[1] - p[0]
    angle = math.degrees(math.atan2(delta[1], delta[0]))
    while angle >= 90.0:
        angle -= 180.0
    while angle < -90.0:
        angle += 180.0
    return float(angle)


def zoom_segment_to_original(ann: dict, segment: Iterable[Iterable[float]]) -> np.ndarray:
    """Map annotation coordinates to original camera pixels without image use."""
    crop = np.asarray(ann["crop_original_xyxy"][:2], np.float64)
    scale = float(ann["enlargement_scale"])
    if scale <= 0:
        raise ValueError("invalid enlargement scale")
    return np.asarray(segment, np.float64) / scale + crop


def _transform(points: np.ndarray, affine: np.ndarray) -> np.ndarray:
    pts = np.asarray(points, np.float64).reshape(1, -1, 2)
    return cv2.transform(pts, affine)[0]


def _rotate_bound(image: np.ndarray, angle: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    h, w = image.shape[:2]
    center = (w / 2.0, h / 2.0)
    affine = cv2.getRotationMatrix2D(center, angle, 1.0)
    cosine, sine = abs(affine[0, 0]), abs(affine[0, 1])
    out_w = int(math.ceil(h * sine + w * cosine))
    out_h = int(math.ceil(h * cosine + w * sine))
    affine[0, 2] += out_w / 2.0 - center[0]
    affine[1, 2] += out_h / 2.0 - center[1]
    rotated = cv2.warpAffine(
        image,
        affine,
        (out_w, out_h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0),
    )
    mask = cv2.warpAffine(
        np.ones((h, w), np.uint8),
        affine,
        (out_w, out_h),
        flags=cv2.INTER_NEAREST,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=0,
    ).astype(bool)
    return rotated, mask, affine


@dataclass(frozen=True)
class Geometry:
    crop_bgr: np.ndarray
    rotated_bgr: np.ndarray
    valid_mask: np.ndarray
    affine: np.ndarray
    inverse_affine: np.ndarray
    crop_origin_xy: tuple[int, int]
    a1_y: float
    a2_y: float
    signed_pitch: float
    pitch: float
    a_axis_original_deg: float
    b_axis_rotated_deg: float | None
    b_lines: tuple[tuple[np.ndarray, np.ndarray], ...]


def prepare_geometry(original_bgr: np.ndarray, ann: dict) -> Geometry:
    """Rectify the original camera crop using calibration roles only."""
    if ann.get("annotation_target") != "PHYSICAL_YARN_REFERENCE":
        raise ValueError("PHYSICAL_YARN_REFERENCE annotation required")
    seg = ann["segments"]
    intervals = ann.get("same_family_intervals")
    if (
        not seg.get("reference")
        or not seg.get("check_same")
        or ann.get("same_family_intervals_confirmed") is not True
        or type(intervals) is not int
        or intervals < 1
    ):
        raise ValueError("confirmed A1/A2 interval geometry required")
    x0, y0, x1, y1 = map(int, ann["crop_original_xyxy"])
    crop = original_bgr[y0:y1, x0:x1].copy()
    if crop.size == 0:
        raise ValueError("annotation crop is outside original photo")
    a1 = zoom_segment_to_original(ann, seg["reference"]) - (x0, y0)
    a2 = zoom_segment_to_original(ann, seg["check_same"]) - (x0, y0)
    angle = _signed_axis(a1)
    rotated, valid, affine = _rotate_bound(crop, angle)
    ra1, ra2 = _transform(a1, affine), _transform(a2, affine)
    a1_y, a2_y = float(ra1[:, 1].mean()), float(ra2[:, 1].mean())
    signed_pitch = (a2_y - a1_y) / intervals
    pitch = abs(signed_pitch)
    if pitch < 2.5:
        raise ValueError("original-camera pitch is under-resolved")

    b_lines: list[tuple[np.ndarray, np.ndarray]] = []
    b_axis = None
    b1 = seg.get("check_cross")
    b2 = seg.get("check_cross_second")
    b_intervals = ann.get("cross_family_intervals")
    if (
        b1
        and b2
        and ann.get("cross_family_intervals_confirmed") is True
        and type(b_intervals) is int
        and b_intervals >= 1
    ):
        rb1 = _transform(zoom_segment_to_original(ann, b1) - (x0, y0), affine)
        rb2 = _transform(zoom_segment_to_original(ann, b2) - (x0, y0), affine)
        d = rb1[1] - rb1[0]
        b_axis = _line_axis(rb1)
        # Translation between B1/B2 is measured normal to B1, not as a
        # horizontal-only shortcut.  Generate a calibrated family of lines.
        normal = np.array([-d[1], d[0]], np.float64)
        normal /= max(np.linalg.norm(normal), 1e-9)
        signed_span = float(np.dot(rb2.mean(axis=0) - rb1.mean(axis=0), normal))
        step = signed_span / b_intervals
        for k in range(-180, 181):
            shift = normal * (k * step)
            p0, p1 = rb1[0] + shift, rb1[1] + shift
            mid = (p0 + p1) / 2.0
            if -100 <= mid[0] <= rotated.shape[1] + 100:
                b_lines.append((p0, p1))

    return Geometry(
        crop_bgr=crop,
        rotated_bgr=rotated,
        valid_mask=valid,
        affine=affine,
        inverse_affine=cv2.invertAffineTransform(affine),
        crop_origin_xy=(x0, y0),
        a1_y=a1_y,
        a2_y=a2_y,
        signed_pitch=signed_pitch,
        pitch=pitch,
        a_axis_original_deg=_line_axis(a1),
        b_axis_rotated_deg=b_axis,
        b_lines=tuple(b_lines),
    )


def _gray_float(bgr: np.ndarray) -> np.ndarray:
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    return lab[:, :, 0].astype(np.float32) / 255.0


def _bilinear(image: np.ndarray, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    return cv2.remap(
        image,
        x.astype(np.float32),
        y.astype(np.float32),
        cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=0,
    )


def _sample_patch(
    gray: np.ndarray,
    valid: np.ndarray,
    center: np.ndarray,
    axis: np.ndarray,
    pitch: float,
    *,
    length_pitch: float = 0.90,
    width_pitch: float = 1.55,
) -> tuple[np.ndarray, np.ndarray]:
    axis = np.asarray(axis, np.float64)
    axis /= max(np.linalg.norm(axis), 1e-9)
    normal = np.array([-axis[1], axis[0]])
    ns = max(9, int(round(length_pitch * pitch * 2)) | 1)
    nn = max(13, int(round(width_pitch * pitch * 2)) | 1)
    s = np.linspace(-length_pitch * pitch / 2, length_pitch * pitch / 2, ns)
    n = np.linspace(-width_pitch * pitch / 2, width_pitch * pitch / 2, nn)
    xx = center[0] + axis[0] * s[None, :] + normal[0] * n[:, None]
    yy = center[1] + axis[1] * s[None, :] + normal[1] * n[:, None]
    patch = _bilinear(gray, xx, yy)
    mask = cv2.remap(
        valid.astype(np.uint8),
        xx.astype(np.float32),
        yy.astype(np.float32),
        cv2.INTER_NEAREST,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=0,
    ).astype(bool)
    return patch, mask


def _profile_features(patch: np.ndarray, mask: np.ndarray, pitch: float) -> dict | None:
    if patch.size == 0 or float(mask.mean()) < 0.92:
        return None
    profile = np.median(patch, axis=1)
    sigma = max(0.7, len(profile) / 45.0)
    smooth = cv2.GaussianBlur(profile[:, None], (0, 0), sigmaX=0, sigmaY=sigma).ravel()
    center = (len(smooth) - 1) / 2.0
    step = 1.55 * pitch / max(1, len(smooth) - 1)
    # Patch coordinates are sampled at roughly two samples per source pixel.
    widths_px = np.linspace(0.24 * pitch, 0.92 * pitch, 15)
    grad = np.gradient(smooth)
    noise = float(np.median(np.abs(grad - np.median(grad))) * 1.4826 + 0.004)
    best = None
    for width in widths_px:
        half_idx = width / max(step, 1e-6) / 2.0
        li = int(round(center - half_idx))
        ri = int(round(center + half_idx))
        if li < 1 or ri >= len(grad) - 1:
            continue
        opposite = -grad[li] * grad[ri]
        pair = min(abs(float(grad[li])), abs(float(grad[ri]))) / noise if opposite > 0 else 0.0
        symmetry = min(abs(float(grad[li])), abs(float(grad[ri]))) / (
            max(abs(float(grad[li])), abs(float(grad[ri]))) + 1e-9
        )
        value = pair * (0.55 + 0.45 * symmetry)
        if best is None or value > best[0]:
            best = (value, width, pair, symmetry, li, ri)
    if best is None:
        return None
    _, width, pair, symmetry, li, ri = best
    ci = int(round(center))
    band_half = max(1, int(round((ri - li) * 0.22)))
    inner = float(np.mean(smooth[ci - band_half : ci + band_half + 1]))
    flank = float((smooth[max(0, li - band_half) : li + 1].mean() +
                   smooth[ri : min(len(smooth), ri + band_half + 1)].mean()) / 2.0)
    local_scale = float(np.std(smooth[max(0, li - 2) : min(len(smooth), ri + 3)]) + 0.015)
    signed_contrast = (inner - flank) / local_scale
    gy, gx = np.gradient(patch.astype(np.float32))
    normal_energy = float(np.median(np.abs(gy)))
    axial_energy = float(np.median(np.abs(gx)))
    coherence = (normal_energy - axial_energy) / (normal_energy + axial_energy + 1e-6)
    descriptor_x = np.linspace(0, len(smooth) - 1, 33)
    descriptor = np.interp(descriptor_x, np.arange(len(smooth)), smooth)
    descriptor -= np.median(descriptor)
    descriptor /= max(float(np.linalg.norm(descriptor)), 1e-6)
    return {
        "paired_boundary_raw": float(pair),
        "boundary_symmetry": float(symmetry),
        "apparent_width_px": float(width),
        "signed_center_contrast": float(signed_contrast),
        "axis_coherence_raw": float(coherence),
        "_shape_descriptor": descriptor,
    }


def _line_valid_range(valid: np.ndarray, point: np.ndarray, axis: np.ndarray) -> tuple[float, float]:
    h, w = valid.shape
    axis = axis / max(np.linalg.norm(axis), 1e-9)
    limits = []
    for coordinate, component, bound in (
        (point[0], axis[0], w - 1),
        (point[1], axis[1], h - 1),
    ):
        if abs(component) < 1e-8:
            continue
        limits.extend(((0 - coordinate) / component, (bound - coordinate) / component))
    if not limits:
        return 0.0, 0.0
    low, high = -1e9, 1e9
    for coordinate, component, bound in (
        (point[0], axis[0], w - 1),
        (point[1], axis[1], h - 1),
    ):
        if abs(component) < 1e-8:
            if not 0 <= coordinate <= bound:
                return 0.0, 0.0
            continue
        a, b = (0 - coordinate) / component, (bound - coordinate) / component
        low, high = max(low, min(a, b)), min(high, max(a, b))
    return float(low), float(high)


def _crossing_x(line: tuple[np.ndarray, np.ndarray], y: float) -> float | None:
    p0, p1 = line
    dy = float(p1[1] - p0[1])
    if abs(dy) < 1e-6:
        return None
    t = (y - p0[1]) / dy
    return float(p0[0] + t * (p1[0] - p0[0]))


def _line_intersection(point: np.ndarray, axis: np.ndarray,
                       line: tuple[np.ndarray, np.ndarray]) -> np.ndarray | None:
    """Intersection of an arbitrary hypothesis path and calibrated B line."""
    p = np.asarray(point, np.float64)
    u = np.asarray(axis, np.float64)
    q0, q1 = line
    v = q1 - q0
    matrix = np.column_stack((u, -v))
    determinant = float(np.linalg.det(matrix))
    if abs(determinant) < 1e-7:
        return None
    t = float(np.linalg.solve(matrix, q0 - p)[0])
    return p + t * u


def _descriptor_similarity(descriptor: np.ndarray, template: np.ndarray | None) -> float:
    if template is None:
        return 0.0
    values = []
    # Small image-only alignment tolerance for hand-drawn reference positions;
    # no A3 coordinate or class label is used to select the shift.
    for shift in range(-3, 4):
        if shift < 0:
            a, b = descriptor[-shift:], template[:shift]
        elif shift > 0:
            a, b = descriptor[:-shift], template[shift:]
        else:
            a, b = descriptor, template
        denom = float(np.linalg.norm(a) * np.linalg.norm(b))
        values.append(float(np.dot(a, b) / denom) if denom > 1e-8 else 0.0)
    return float(np.clip((max(values) + 1.0) / 2.0, 0.0, 1.0))


def _score_path(
    gray: np.ndarray,
    valid: np.ndarray,
    point: np.ndarray,
    axis: np.ndarray,
    pitch: float,
    anchor_polarity: float,
    *,
    anchor_template: np.ndarray | None = None,
    crossing_points: Iterable[Iterable[float]] = (),
) -> dict:
    axis = np.asarray(axis, np.float64)
    axis /= max(np.linalg.norm(axis), 1e-9)
    lo, hi = _line_valid_range(valid, point, axis)
    margin = 1.2 * pitch
    lo, hi = lo + margin, hi - margin
    if hi <= lo:
        return {"status": "INSUFFICIENT_VALID_PIXELS", "score": 0.0, "windows": []}
    ts = np.linspace(lo, hi, 13)
    windows = []
    for t in ts:
        center = point + t * axis
        patch, mask = _sample_patch(gray, valid, center, axis, pitch)
        features = _profile_features(patch, mask, pitch)
        if features is not None:
            features["center_xy"] = [round(float(center[0]), 2), round(float(center[1]), 2)]
            windows.append(features)
    if len(windows) < 7:
        return {
            "status": "INSUFFICIENT_VALID_PIXELS",
            "score": 0.0,
            "windows": [
                {k: v for k, v in item.items() if k != "_shape_descriptor"}
                for item in windows
            ],
        }

    pair = np.asarray([x["paired_boundary_raw"] for x in windows])
    widths = np.asarray([x["apparent_width_px"] for x in windows])
    coherence = np.asarray([x["axis_coherence_raw"] for x in windows])
    contrasts = np.asarray([x["signed_center_contrast"] for x in windows])
    morphology = np.asarray([
        _descriptor_similarity(x["_shape_descriptor"], anchor_template) for x in windows
    ])
    paired_boundary = float(np.median(np.clip(pair / 3.0, 0.0, 1.0)))
    width_cv = float(1.4826 * np.median(np.abs(widths - np.median(widths))) /
                     max(np.median(widths), 1e-6))
    width_consistency = float(np.clip(1.0 - width_cv / 0.38, 0.0, 1.0))
    visible_flags = pair >= 1.25
    visible_continuity = float(visible_flags.mean())
    longest = 0
    current = 0
    for flag in visible_flags:
        current = current + 1 if flag else 0
        longest = max(longest, current)
    longest_fraction = longest / len(visible_flags)
    visible_continuity = 0.55 * visible_continuity + 0.45 * longest_fraction
    axis_coherence = float(np.clip((np.median(coherence) + 0.12) / 0.62, 0.0, 1.0))
    polarity = float(np.median(contrasts))
    anchor_polarity_score = float(np.clip((polarity * anchor_polarity + 0.10) / 0.80, 0.0, 1.0))
    anchor_morphology = float(np.median(morphology))

    # At calibrated B-family crossings, a physical A entity can disappear and
    # resume at the same transverse coordinate.  Count only symmetric left/right
    # recovery; a single dark/bright diagonal streak does not satisfy this.
    resumes = []
    dominances = []
    crossings = []
    normal = np.array([-axis[1], axis[0]])
    for raw_center in crossing_points:
        center = np.asarray(raw_center, np.float64)
        if not (0 <= center[0] < gray.shape[1] and 0 <= center[1] < gray.shape[0]):
            continue
        offsets = (-0.42 * pitch, 0.0, 0.42 * pitch)
        local = []
        for offset in offsets:
            patch, mask = _sample_patch(
                gray, valid, center + axis * offset, axis, pitch,
                length_pitch=0.42, width_pitch=1.45,
            )
            local.append(_profile_features(patch, mask, pitch))
        if any(item is None for item in local):
            continue
        strength = [min(1.0, item["paired_boundary_raw"] / 3.0) for item in local]
        symmetric_outside = min(strength[0], strength[2])
        resume = float(np.clip(symmetric_outside - strength[1], 0.0, 1.0))
        resumes.append(resume)
        radius = max(3, int(round(0.55 * pitch)))
        x0, y0 = int(round(center[0])), int(round(center[1]))
        patch = gray[max(0, y0 - radius):y0 + radius + 1,
                     max(0, x0 - radius):x0 + radius + 1]
        if min(patch.shape, default=0) >= 5:
            gy, gx = np.gradient(patch)
            # A line has gradients along its normal; B has the orthogonal energy.
            a_energy = float(np.mean(np.abs(gx * normal[0] + gy * normal[1])))
            b_energy = float(np.mean(np.abs(gx * axis[0] + gy * axis[1])))
            dominance = (a_energy - b_energy) / (a_energy + b_energy + 1e-6)
            dominances.append(dominance)
        else:
            dominance = 0.0
        crossings.append({
            "xy": [round(float(center[0]), 2), round(float(center[1]), 2)],
            "left_center_right_boundary": [round(v, 3) for v in strength],
            "symmetric_resumption": round(resume, 3),
            "orientation_dominance_A_minus_B": round(float(dominance), 3),
        })
    if len(resumes) >= 4:
        meaningful = float(np.mean(np.asarray(resumes) >= 0.12))
        signs = np.sign(np.asarray(dominances))
        transitions = float(np.mean(signs[1:] != signs[:-1])) if len(signs) >= 2 else 0.0
        diversity = float(np.clip(np.std(dominances) / 0.24, 0.0, 1.0))
        occlusion_resumption = 0.55 * meaningful + 0.25 * transitions + 0.20 * diversity
        topology_status = "OBSERVED_COMPETING_ORIENTATION_SEQUENCE"
    else:
        occlusion_resumption = 0.0
        transitions = None
        topology_status = "NOT_ENOUGH_CALIBRATED_CROSSINGS"

    components = {
        "paired_boundary": paired_boundary,
        "width_consistency": width_consistency,
        "visible_continuity": visible_continuity,
        "axis_coherence": axis_coherence,
        "anchor_polarity": anchor_polarity_score,
        "anchor_morphology": anchor_morphology,
        "occlusion_resumption": float(occlusion_resumption),
    }
    score = sum(FEATURE_WEIGHTS[k] * components[k] for k in FEATURE_WEIGHTS)
    return {
        "status": "SCORED_LOCAL_ENTITY_HYPOTHESIS",
        "score": round(float(score), 4),
        "components": {k: round(float(v), 4) for k, v in components.items()},
        "median_apparent_width_original_px": round(float(np.median(widths)), 3),
        "apparent_width_mad_fraction": round(width_cv, 4),
        "median_signed_center_contrast": round(polarity, 4),
        "visible_window_fraction": round(float(visible_flags.mean()), 4),
        "longest_visible_run_fraction": round(float(longest_fraction), 4),
        "topology_status": topology_status,
        "orientation_dominance_transition_fraction": (
            round(transitions, 4) if transitions is not None else None
        ),
        "crossings": crossings,
        "windows": [
            {k: v for k, v in item.items() if k != "_shape_descriptor"}
            for item in windows
        ],
    }


def _dominant_non_yarn_texture_axis(gray: np.ndarray, valid: np.ndarray) -> tuple[float, float]:
    """Return a diagonal surface-texture competitor, never a yarn decision."""
    blurred = cv2.GaussianBlur(gray, (0, 0), 0.8)
    gx = cv2.Sobel(blurred, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(blurred, cv2.CV_32F, 0, 1, ksize=3)
    magnitude = np.hypot(gx, gy)
    line_angle = (np.degrees(np.arctan2(gy, gx)) + 90.0) % 180.0
    bins = np.arange(181)
    hist, _ = np.histogram(line_angle[valid], bins=bins, weights=magnitude[valid])
    hist = np.convolve(np.r_[hist[-5:], hist, hist[:5]], np.ones(11) / 11.0, mode="valid")
    angles = np.arange(180, dtype=np.float64) + 0.5
    allowed = np.array([
        _axial_distance(a, 0.0) >= 13.0 and _axial_distance(a, 90.0) >= 13.0
        for a in angles
    ])
    if not np.any(allowed) or float(hist.sum()) <= 0:
        return 45.0, 0.0
    masked = np.where(allowed, hist, -1.0)
    idx = int(np.argmax(masked))
    strength = float(hist[idx] / (np.max(hist) + 1e-9))
    return float(angles[idx]), strength


def _candidate_y_values(geometry: Geometry) -> list[float]:
    h = geometry.rotated_bgr.shape[0]
    values = []
    for k in range(-200, 201):
        y = geometry.a1_y + k * geometry.signed_pitch
        if 1.2 * geometry.pitch <= y <= h - 1.2 * geometry.pitch:
            values.append(float(y))
    return values


def _calibration_anchor_signature(
    gray: np.ndarray, geometry: Geometry
) -> tuple[float, np.ndarray | None, dict]:
    axis = np.array([1.0, 0.0])
    x = geometry.rotated_bgr.shape[1] / 2.0
    evidence = []
    descriptors = []
    for y in (geometry.a1_y, geometry.a2_y):
        patch, mask = _sample_patch(gray, geometry.valid_mask, np.array([x, y]), axis, geometry.pitch,
                                    length_pitch=2.5, width_pitch=1.55)
        feat = _profile_features(patch, mask, geometry.pitch)
        if feat is not None:
            evidence.append(float(feat["signed_center_contrast"]))
            descriptors.append(feat["_shape_descriptor"])
    median = float(np.median(evidence)) if evidence else 0.0
    # Zero/ambiguous contrast does not silently choose a per-fabric polarity.
    polarity = 1.0 if median >= 0.12 else -1.0 if median <= -0.12 else 0.0
    template = None
    if descriptors:
        template = np.median(np.asarray(descriptors), axis=0)
        template /= max(float(np.linalg.norm(template)), 1e-6)
    return polarity, template, {
        "source_roles": ["reference", "check_same"],
        "signed_contrasts": [round(v, 4) for v in evidence],
        "selected_sign": int(polarity),
        "ambiguous": polarity == 0.0,
    }


def infer_hypotheses(original_bgr: np.ndarray, ann: dict) -> tuple[dict, Geometry]:
    """Generate/score candidates without reading A3 (holdout_same)."""
    geometry = prepare_geometry(original_bgr, ann)
    gray = _gray_float(geometry.rotated_bgr)
    polarity, anchor_template, polarity_meta = _calibration_anchor_signature(gray, geometry)
    yarn_ys = _candidate_y_values(geometry)
    gap_ys = [y + 0.5 * geometry.signed_pitch for y in yarn_ys]
    gap_ys = [y for y in gap_ys if geometry.pitch <= y < gray.shape[0] - geometry.pitch]
    x_center = gray.shape[1] / 2.0

    def crossings(y: float) -> list[list[float]]:
        xs = [_crossing_x(line, y) for line in geometry.b_lines]
        return [[x, y] for x in sorted(
            x for x in xs if x is not None and geometry.pitch <= x < gray.shape[1] - geometry.pitch
        )]

    yarn_records = []
    for y in yarn_ys:
        score = _score_path(
            gray, geometry.valid_mask, np.array([x_center, y]), np.array([1.0, 0.0]),
            geometry.pitch, polarity, anchor_template=anchor_template,
            crossing_points=crossings(y),
        )
        yarn_records.append({"path_y": round(y, 3), **score})
    gap_records = []
    for y in gap_ys:
        score = _score_path(
            gray, geometry.valid_mask, np.array([x_center, y]), np.array([1.0, 0.0]),
            geometry.pitch, polarity, anchor_template=anchor_template,
            crossing_points=crossings(y),
        )
        gap_records.append({"path_y": round(y, 3), **score})

    twill_axis, twill_strength = _dominant_non_yarn_texture_axis(gray, geometry.valid_mask)
    theta = math.radians(twill_axis)
    twill_direction = np.array([math.cos(theta), math.sin(theta)])
    twill_normal = np.array([-twill_direction[1], twill_direction[0]])
    center = np.array([gray.shape[1] / 2.0, gray.shape[0] / 2.0])
    twill_records = []
    for offset in (-geometry.pitch, 0.0, geometry.pitch):
        point = center + twill_normal * offset
        twill_crossings = [
            cross for line in geometry.b_lines
            if (cross := _line_intersection(point, twill_direction, line)) is not None
        ]
        score = _score_path(
            gray, geometry.valid_mask, point, twill_direction, geometry.pitch,
            polarity, anchor_template=anchor_template,
            crossing_points=twill_crossings,
        )
        twill_records.append({
            "point_xy": [round(float(point[0]), 3), round(float(point[1]), 3)],
            "axis_deg_in_A_rectified_image": round(twill_axis, 3),
            **score,
        })

    def distribution(records: list[dict]) -> dict:
        scores = [float(r["score"]) for r in records if r.get("status") == "SCORED_LOCAL_ENTITY_HYPOTHESIS"]
        return {
            "scored_count_NOT_physical_yarn_count": len(scores),
            "median": round(float(np.median(scores)), 4) if scores else None,
            "q75": round(float(np.percentile(scores, 75)), 4) if scores else None,
            "maximum": round(max(scores), 4) if scores else None,
        }

    yarn_distribution = distribution(yarn_records)
    gap_distribution = distribution(gap_records)
    if yarn_distribution["median"] is None or gap_distribution["median"] is None:
        period_margin = None
        period_status = "ABSTAIN_NOT_ENOUGH_PERIOD_COMPETITION"
    else:
        period_margin = float(yarn_distribution["median"] - gap_distribution["median"])
        period_status = (
            "LATTICE_PHASE_SEPARATED_FROM_HALF_PHASE_COUNTEREXAMPLE"
            if period_margin >= MIN_LATTICE_VS_HALF_PHASE_MEDIAN_MARGIN
            else "ABSTAIN_WRONG_PERIOD_OR_PHASE_COMPETITION"
        )
    result = {
        "sample_id": ann["sample_id"],
        "status": "CANDIDATE_EVIDENCE_REQUIRES_INDEPENDENT_HUMAN_REVIEW",
        "measurement_source": "ARCHIVED_ORIGINAL_PHONE_PHOTO_PIXELS",
        "original_image_path": ann["original_image_path"],
        "annotation_2x_used_only_for_coordinate_mapping": True,
        "inference_roles": [
            "reference", "check_same", "same_family_intervals",
            "check_cross", "check_cross_second", "cross_family_intervals",
        ],
        "excluded_until_evaluation": "holdout_same",
        "a3_read_during_inference": False,
        "feature_split": (
            "DEVELOPMENT_FEATURE_SELECTION" if ann["sample_id"] in DEVELOPMENT_FABRICS
            else "INDEPENDENT_FABRIC_VALIDATION"
        ),
        "operator_A_axis_deg": round(geometry.a_axis_original_deg, 3),
        "physical_pitch_original_px_from_A1_A2": round(geometry.pitch, 4),
        "anchor_polarity_calibration": polarity_meta,
        "twill_surface_competitor_axis_rectified_deg": round(twill_axis, 3),
        "twill_axis_histogram_relative_strength": round(twill_strength, 4),
        "fixed_feature_weights": FEATURE_WEIGHTS,
        "fixed_decision_thresholds": {
            "minimum_entity_score": MIN_ENTITY_SCORE,
            "minimum_competition_margin": MIN_COMPETITION_MARGIN,
            "minimum_lattice_vs_half_phase_median_margin": MIN_LATTICE_VS_HALF_PHASE_MEDIAN_MARGIN,
        },
        "period_counterexample_status": period_status,
        "lattice_vs_half_phase_median_margin": (
            round(period_margin, 4) if period_margin is not None else None
        ),
        "hypothesis_distributions": {
            "PHYSICAL_A_LATTICE_HYPOTHESES": yarn_distribution,
            "HALF_PHASE_GAP_HYPOTHESES": gap_distribution,
            "DIAGONAL_TWILL_SURFACE_HYPOTHESES": distribution(twill_records),
        },
        "physical_yarn_hypotheses_NOT_truth": yarn_records,
        "gap_hypotheses_NOT_truth": gap_records,
        "twill_texture_hypotheses_NOT_truth": twill_records,
        "verified_physical_yarn_count": None,
        "limitations": [
            "A1/A2 paths are approximate physical-yarn references, not visible centerline masks.",
            "Generated gap/twill competitors are hypotheses until independently human reviewed.",
            "A local double boundary alone can also be produced by a dark gap or printed stripe.",
            "No roots/cm or whole-image actual-yarn count is produced.",
        ],
    }
    return result, geometry


def evaluate_a3_holdout(inferred: dict, geometry: Geometry, ann: dict) -> dict:
    """Read A3 only after inference; never update weights, phase, or candidates."""
    segment = ann.get("segments", {}).get("holdout_same")
    if not segment:
        return {"status": "NOT_EVALUATED_NO_A3", "used_for_inference": False}
    x0, y0 = geometry.crop_origin_xy
    a3 = zoom_segment_to_original(ann, segment) - (x0, y0)
    ra3 = _transform(a3, geometry.affine)
    y = float(ra3[:, 1].mean())
    midpoint = ra3.mean(axis=0)
    yarn = min(inferred["physical_yarn_hypotheses_NOT_truth"], key=lambda r: abs(r["path_y"] - y))
    gap = min(inferred["gap_hypotheses_NOT_truth"], key=lambda r: abs(r["path_y"] - y))
    twill = min(
        inferred["twill_texture_hypotheses_NOT_truth"],
        key=lambda r: np.linalg.norm(np.asarray(r["point_xy"]) - midpoint),
    )
    positive_score = float(yarn["score"])
    negative_scores = [float(gap["score"]), float(twill["score"])]
    margin = positive_score - max(negative_scores)
    reference_support = (
        positive_score >= MIN_ENTITY_SCORE and margin >= MIN_COMPETITION_MARGIN
        and inferred.get("period_counterexample_status")
        == "LATTICE_PHASE_SEPARATED_FROM_HALF_PHASE_COUNTEREXAMPLE"
    )
    split = inferred["feature_split"]
    return {
        "status": (
            "IMAGE_EVIDENCE_PREFERS_A3_NEAREST_PHYSICAL_LATTICE_HYPOTHESIS"
            if reference_support
            else "ABSTAIN_COMPETING_HYPOTHESES_NOT_SEPARATED"
        ),
        "evaluation_role": "A3_HOLDOUT_APPROXIMATE_PHYSICAL_YARN_REFERENCE",
        "used_for_inference": False,
        "used_for_feature_selection_or_threshold_tuning": False,
        "fabric_split": split,
        "a3_is_visible_pixel_ground_truth": False,
        "a3_rectified_mean_y": round(y, 3),
        "nearest_physical_lattice_hypothesis_y": yarn["path_y"],
        "nearest_half_phase_gap_hypothesis_y": gap["path_y"],
        "physical_reference_hypothesis_score": round(positive_score, 4),
        "gap_competitor_score": round(float(gap["score"]), 4),
        "twill_competitor_score": round(float(twill["score"]), 4),
        "competition_margin": round(margin, 4),
        "period_counterexample_status": inferred.get("period_counterexample_status"),
        "automated_reference_support": bool(reference_support),
        "independent_human_patch_review": "PENDING",
        "physical_identity_verified": False,
        "selected_records": {"physical": yarn, "gap": gap, "twill": twill},
    }


def _text(canvas: np.ndarray, lines: Iterable[str], x: int = 12, y: int = 26,
          color: tuple[int, int, int] = (245, 245, 245)) -> None:
    for line in lines:
        cv2.putText(canvas, str(line), (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.48,
                    color, 1, cv2.LINE_AA)
        y += 21


def _fit_width(image: np.ndarray, width: int = 900) -> np.ndarray:
    if image.shape[1] <= width:
        return image
    scale = width / image.shape[1]
    return cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)


def _line_panel(geometry: Geometry, inferred: dict, held: dict, mode: str) -> np.ndarray:
    panel = geometry.rotated_bgr.copy()
    h, w = panel.shape[:2]
    if mode == "entity":
        for record in inferred["gap_hypotheses_NOT_truth"]:
            y = int(round(record["path_y"]))
            cv2.line(panel, (0, y), (w - 1, y), (0, 0, 180), 1, cv2.LINE_AA)
        for record in inferred["physical_yarn_hypotheses_NOT_truth"]:
            y = int(round(record["path_y"]))
            score = float(record["score"])
            color = (20, 210, 30) if score >= MIN_ENTITY_SCORE else (0, 170, 230)
            cv2.line(panel, (0, y), (w - 1, y), color, 1, cv2.LINE_AA)
            for window in record.get("windows", []):
                if window["paired_boundary_raw"] >= 1.25:
                    x, yy = map(int, map(round, window["center_xy"]))
                    cv2.circle(panel, (x, yy), 2, (255, 240, 20), -1, cv2.LINE_AA)
        title = "GREEN/ORANGE=A lattice hypothesis; RED=half-phase gap; CYAN=paired edges"
    else:
        record = held["selected_records"]["physical"]
        for crossing in record.get("crossings", []):
            x, y = map(int, map(round, crossing["xy"]))
            resume = crossing["symmetric_resumption"]
            dominance = crossing["orientation_dominance_A_minus_B"]
            color = (40, 220, 40) if resume >= 0.12 else (0, 160, 240)
            cv2.circle(panel, (x, y), max(3, int(round(geometry.pitch * 0.25))), color, 1, cv2.LINE_AA)
            if dominance >= 0:
                cv2.line(panel, (x - 5, y), (x + 5, y), (255, 255, 255), 1)
            else:
                cv2.line(panel, (x, y - 5), (x, y + 5), (255, 255, 255), 1)
        title = "Crossings: GREEN=symmetric disappear/resume; tick=A/B local dominance"
    banner = np.zeros((62, panel.shape[1], 3), np.uint8)
    _text(banner, [title, "All measurements: original phone pixels; display rectification only"], y=22)
    return _fit_width(np.vstack((banner, panel)))


def _oriented_display_patch(
    geometry: Geometry, record: dict, kind: str, midpoint: np.ndarray
) -> np.ndarray:
    gray = _gray_float(geometry.rotated_bgr)
    if kind in ("physical", "gap"):
        point = np.array([midpoint[0], float(record["path_y"])])
        axis = np.array([1.0, 0.0])
    else:
        point = np.asarray(record["point_xy"], np.float64)
        theta = math.radians(float(record["axis_deg_in_A_rectified_image"]))
        axis = np.array([math.cos(theta), math.sin(theta)])
    patch, mask = _sample_patch(
        gray, geometry.valid_mask, point, axis, geometry.pitch,
        length_pitch=9.0, width_pitch=3.2,
    )
    patch = np.uint8(np.clip(patch * 255.0, 0, 255))
    patch[~mask] = 0
    display = cv2.cvtColor(patch, cv2.COLOR_GRAY2BGR)
    display = cv2.resize(display, (420, 180), interpolation=cv2.INTER_NEAREST)
    cv2.line(display, (0, display.shape[0] // 2),
             (display.shape[1] - 1, display.shape[0] // 2), (0, 220, 255), 1)
    return display


def write_evidence_images(out_dir: Path, ann: dict, inferred: dict,
                          held: dict, geometry: Geometry) -> list[dict]:
    out_dir.mkdir(parents=True, exist_ok=True)
    entity = _line_panel(geometry, inferred, held, "entity")
    cv2.imwrite(str(out_dir / "local_entity_evidence.jpg"), entity)
    topology = _line_panel(geometry, inferred, held, "topology")
    cv2.imwrite(str(out_dir / "occlusion_topology.jpg"), topology)

    x0, y0 = geometry.crop_origin_xy
    a3 = zoom_segment_to_original(ann, ann["segments"]["holdout_same"]) - (x0, y0)
    midpoint = _transform(a3, geometry.affine).mean(axis=0)
    rows = []
    review_entries = []
    kinds = ("physical", "gap", "twill")
    labels = {
        "physical": "A3-nearest A-lattice hypothesis (NOT pixel truth)",
        "gap": "half-phase gap competitor (NOT reviewed truth)",
        "twill": "diagonal texture competitor (NOT reviewed truth)",
    }
    for kind in kinds:
        record = held["selected_records"][kind]
        patch = _oriented_display_patch(geometry, record, kind, midpoint)
        header = np.zeros((70, patch.shape[1], 3), np.uint8)
        _text(header, [labels[kind], f"entity score={record['score']:.4f}"], y=23)
        rows.append(np.vstack((header, patch)))
        blind = hashlib.sha256(f"{ann['sample_id']}:{kind}:g1".encode()).hexdigest()[:10].upper()
        review_entries.append({
            "blind_patch_id": blind,
            "sample_id": ann["sample_id"],
            "display_panel": kind,
            "candidate_role_for_machine_audit_NOT_truth": kind,
            "review_state": "PENDING",
        })
    comparison = np.hstack(rows)
    cv2.imwrite(str(out_dir / "competing_hypotheses.jpg"), comparison)

    # Blind review sheet deliberately hides the machine role and shuffles by a
    # deterministic hash.  The separate manifest preserves reproducibility.
    shuffled = sorted(zip(review_entries, rows), key=lambda pair: pair[0]["blind_patch_id"])
    blind_panels = []
    for panel_index, (entry, row) in enumerate(shuffled):
        entry["blind_review_panel_index_left_to_right"] = panel_index
        patch = row[70:].copy()
        header = np.zeros((70, patch.shape[1], 3), np.uint8)
        _text(header, [f"BLIND ID {entry['blind_patch_id']}",
                       "Review: YARN / GAP / TWILL / UNCERTAIN"], y=23)
        blind_panels.append(np.vstack((header, patch)))
    cv2.imwrite(str(out_dir / "blind_review_sheet.jpg"), np.hstack(blind_panels))
    return review_entries


def _load_original(root: Path, ann: dict) -> np.ndarray:
    path = root / ann["original_image_path"]
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != ann["original_image_sha256"]:
        raise RuntimeError(f"original photo hash mismatch: {ann['sample_id']}")
    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f"cannot decode original photo: {ann['sample_id']}")
    return image


def _compact_record(record: dict, *, keep_crossings: bool = False) -> dict:
    compact = {
        k: v for k, v in record.items()
        if k not in ("windows", "crossings")
    }
    compact["longitudinal_window_count"] = len(record.get("windows", []))
    compact["calibrated_crossing_count"] = len(record.get("crossings", []))
    if keep_crossings:
        compact["crossings"] = record.get("crossings", [])
    return compact


def _compact_payload(inferred: dict, held: dict) -> dict:
    inference = dict(inferred)
    for key in (
        "physical_yarn_hypotheses_NOT_truth",
        "gap_hypotheses_NOT_truth",
        "twill_texture_hypotheses_NOT_truth",
    ):
        inference[key] = [_compact_record(item) for item in inferred[key]]
    evaluation = dict(held)
    if "selected_records" in held:
        evaluation["selected_records"] = {
            key: _compact_record(value, keep_crossings=True)
            for key, value in held["selected_records"].items()
        }
    return {"inference_without_A3": inference, "independent_A3_evaluation": evaluation}


def experiment(root: Path, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    results = []
    review_entries = []
    files = sorted((root / "datasets/annotations/drafts").glob("U20261013_*.json"))
    for file in files:
        ann = validate_annotation(root, json.loads(file.read_text(encoding="utf-8")))
        if ann.get("review_state") != "OPERATOR_REVIEWED":
            continue
        original = _load_original(root, ann)
        inferred, geometry = infer_hypotheses(original, ann)
        held = evaluate_a3_holdout(inferred, geometry, ann)
        sample_out = out / ann["sample_id"]
        review_entries.extend(write_evidence_images(sample_out, ann, inferred, held, geometry))
        payload = _compact_payload(inferred, held)
        (sample_out / "result.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        results.append({
            "sample_id": ann["sample_id"],
            "split": inferred["feature_split"],
            "a3_status": held["status"],
            "physical_reference_hypothesis_score": held.get("physical_reference_hypothesis_score"),
            "gap_competitor_score": held.get("gap_competitor_score"),
            "twill_competitor_score": held.get("twill_competitor_score"),
            "competition_margin": held.get("competition_margin"),
            "automated_reference_support": held.get("automated_reference_support"),
            "independent_human_patch_review": "PENDING",
            "physical_identity_verified": False,
        })
        print(
            f"{ann['sample_id']} split={inferred['feature_split']} "
            f"A3={held['status']} score={held.get('physical_reference_hypothesis_score')} "
            f"gap={held.get('gap_competitor_score')} twill={held.get('twill_competitor_score')} "
            f"margin={held.get('competition_margin')}",
            flush=True,
        )

    independent = [r for r in results if r["split"] == "INDEPENDENT_FABRIC_VALIDATION"]
    auto_supported = sum(bool(r["automated_reference_support"]) for r in independent)
    summary = {
        "goal": "G1_LOCAL_ENTITY_OCCLUSION_COMPETING_HYPOTHESES",
        "g1_verdict": "G1_NOT_EVALUATED",
        "verdict_reason": (
            "Independent fabric A3 references are approximate physical trajectories, not visible-pixel "
            "positive masks, and generated gap/twill negatives have not received blind human review."
        ),
        "development_fabrics": sorted(DEVELOPMENT_FABRICS),
        "independent_validation_fabrics": sorted(INDEPENDENT_FABRICS),
        "independent_fabrics_with_automated_reference_preference_NOT_accuracy": auto_supported,
        "independent_fabric_count": len(independent),
        "independent_human_review_complete": False,
        "accuracy_or_error_rate_evaluable": False,
        "candidate_counts_are_not_actual_yarn_counts": True,
        "results": results,
    }
    (out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    blind_manifest = [
        {
            "blind_patch_id": item["blind_patch_id"],
            "sample_id": item["sample_id"],
            "review_sheet": f"{item['sample_id']}/blind_review_sheet.jpg",
            "panel_index_left_to_right": item["blind_review_panel_index_left_to_right"],
            "review_state": "PENDING",
        }
        for item in review_entries
    ]
    (out / "review_manifest.json").write_text(
        json.dumps({"review_state": "PENDING", "machine_roles_hidden": True,
                    "entries": blind_manifest},
                   ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (out / "machine_role_key_NOT_HUMAN_TRUTH.json").write_text(
        json.dumps({
            "warning": "Machine candidate roles are not human ground truth; keep this key sealed during review.",
            "entries": review_entries,
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    with (out / "independent_review_form.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "blind_patch_id", "reviewer", "reviewed_at", "physical_class",
            "paired_boundaries_visible", "same_entity_resumes_after_crossing",
            "confidence", "notes",
        ])
        for item in sorted(review_entries, key=lambda x: x["blind_patch_id"]):
            writer.writerow([item["blind_patch_id"], "", "", "", "", "", "", ""])
    if len(results) < 5:
        raise RuntimeError("expected five operator-reviewed U20261013 samples")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path, default=Path("experiments/g1-local-entity-evidence"))
    args = parser.parse_args()
    root = args.root.resolve()
    out = args.out if args.out.is_absolute() else root / args.out
    experiment(root, out)


if __name__ == "__main__":
    main()
