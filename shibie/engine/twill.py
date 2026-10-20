from __future__ import annotations

import cv2
import numpy as np

from .config import EngineConfig, DEFAULT_CONFIG
from .preprocess import center_crop, local_normalize, resize_max_side, to_gray
from .width import estimate_reflection_registration, map_centerlines_to_reflection


def _angular_distance(angle_a: np.ndarray | float, angle_b: float) -> np.ndarray | float:
    return np.abs(((np.asarray(angle_a) - float(angle_b) + 90.0) % 180.0) - 90.0)


def _dominant_orientation(angles: np.ndarray, weights: np.ndarray) -> tuple[float, float, float]:
    """Return dominant undirected line orientation, share and circular spread."""
    bins = np.arange(0.0, 182.5, 2.5)
    hist, _ = np.histogram(angles, bins=bins, weights=weights)
    total = max(float(np.sum(hist)), 1e-9)
    best = int(np.argmax(hist))
    centre = float((bins[best] + bins[best + 1]) * 0.5)
    delta = _angular_distance(angles, centre)
    support = delta <= 12.5
    if np.any(support):
        doubled = np.deg2rad(2.0 * angles[support])
        vector = np.sum(weights[support] * np.exp(1j * doubled))
        centre = float((np.degrees(np.angle(vector)) * 0.5) % 180.0)
    delta = _angular_distance(angles, centre)
    support = delta <= 12.5
    dominance = float(np.sum(weights[support]) / total)
    # 离散度只描述最终方向簇本身；全量线段包含经纬纱表面纹理，不能拿来惩罚已选方向。
    spread = float(np.sqrt(np.average(delta[support] * delta[support], weights=weights[support])))
    return centre, dominance, spread


def _direction_name(angle: float) -> str:
    # Image convention: / rises toward the right and is reported as right twill;
    # \\ falls toward the right and is reported as left twill.
    return "right" if np.sin(np.deg2rad(2.0 * angle)) < 0.0 else "left"


def _extract_diagonal_segments(
    normalized: np.ndarray,
    warp_direction_deg: float,
    weft_direction_deg: float,
    config: EngineConfig,
    support_mask: np.ndarray | None = None,
    target_angle_deg: float | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    edges = cv2.Canny(normalized, config.twill_canny_low, config.twill_canny_high, apertureSize=3, L2gradient=True)
    if support_mask is not None:
        edges = cv2.bitwise_and(edges, edges, mask=support_mask.astype(np.uint8))
    lines = cv2.HoughLinesP(
        edges, 1, np.pi / 180.0, threshold=config.twill_hough_threshold,
        minLineLength=config.twill_min_line_length_px, maxLineGap=config.twill_max_line_gap_px,
    )
    if lines is None:
        return np.empty((0, 4)), np.empty(0), np.empty(0)
    segments = lines.reshape(-1, 4).astype(np.float64)
    dx, dy = segments[:, 2] - segments[:, 0], segments[:, 3] - segments[:, 1]
    lengths = np.hypot(dx, dy)
    angles = np.degrees(np.arctan2(dy, dx)) % 180.0
    axis_distance = np.minimum(_angular_distance(angles, warp_direction_deg), _angular_distance(angles, weft_direction_deg))
    keep = (lengths >= config.twill_min_line_length_px) & (axis_distance >= config.twill_axis_exclusion_deg)
    if target_angle_deg is not None:
        # Gabor bands and Canny edges peak on adjacent pixels.  The band therefore
        # constrains the admissible Hough direction instead of erasing those edges.
        keep &= _angular_distance(angles, target_angle_deg) <= config.twill_direction_tolerance_deg
    return segments[keep], lengths[keep], angles[keep]


def _band_segment_support(
    segments: np.ndarray,
    lengths: np.ndarray,
    angles: np.ndarray,
    band_mask: np.ndarray,
    target_angle_deg: float,
    tolerance_deg: float,
) -> tuple[float, float, int]:
    """Measure direction support only among Hough segments crossing the accepted band.

    The global Hough pool often contains unrelated diagonal highlights.  Sampling
    several points along each segment keeps those lines out of the denominator when
    the local Gabor/direction-field stage has already identified a coherent band.
    """
    if len(segments) == 0 or band_mask.size == 0:
        return 0.0, 0.0, 0
    height, width = band_mask.shape[:2]
    fractions = np.linspace(0.2, 0.8, 4, dtype=np.float64)
    overlap_lengths: list[float] = []
    overlap_angles: list[float] = []
    for segment, length, angle in zip(segments, lengths, angles):
        x1, y1, x2, y2 = segment
        xs = np.rint(x1 + (x2 - x1) * fractions).astype(int)
        ys = np.rint(y1 + (y2 - y1) * fractions).astype(int)
        valid = (xs >= 0) & (xs < width) & (ys >= 0) & (ys < height)
        if int(np.sum(valid)) < 2:
            continue
        overlap = float(np.mean(band_mask[ys[valid], xs[valid]] > 0))
        if overlap < 0.5:
            continue
        overlap_lengths.append(float(length) * overlap)
        overlap_angles.append(float(angle))
    if not overlap_lengths:
        return 0.0, 0.0, 0
    support_lengths = np.asarray(overlap_lengths, dtype=np.float64)
    support_angles = np.asarray(overlap_angles, dtype=np.float64)
    aligned = _angular_distance(support_angles, target_angle_deg) <= tolerance_deg
    total = max(float(np.sum(support_lengths)), 1e-9)
    return float(np.sum(support_lengths[aligned]) / total), total, int(len(support_lengths))


def _local_line_field(gray: np.ndarray, sigma: float) -> tuple[np.ndarray, np.ndarray]:
    """Return local line orientation and tensor coherence on the reflection ROI."""
    f = gray.astype(np.float32) / 255.0
    gx = cv2.Sobel(f, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(f, cv2.CV_32F, 0, 1, ksize=3)
    k = int(max(3, round(sigma * 6))) | 1
    jxx = cv2.GaussianBlur(gx * gx, (k, k), sigma)
    jyy = cv2.GaussianBlur(gy * gy, (k, k), sigma)
    jxy = cv2.GaussianBlur(gx * gy, (k, k), sigma)
    coherence = np.sqrt((jxx - jyy) ** 2 + 4.0 * jxy * jxy) / (jxx + jyy + 1e-8)
    gradient_angle = 0.5 * np.arctan2(2.0 * jxy, jxx - jyy)
    return (np.degrees(gradient_angle) + 90.0) % 180.0, coherence


def _gabor_band_candidates(
    normalized: np.ndarray,
    warp_direction_deg: float,
    weft_direction_deg: float,
    config: EngineConfig,
) -> list[dict]:
    """Find connected, locally coherent diagonal texture bands before Hough fitting."""
    field_angle, coherence = _local_line_field(normalized, config.twill_direction_field_sigma)
    h, w = normalized.shape[:2]
    f = normalized.astype(np.float32) / 255.0
    candidates: list[dict] = []
    for angle in range(0, 180, config.twill_gabor_angle_step_deg):
        axis_distance = min(float(_angular_distance(angle, warp_direction_deg)), float(_angular_distance(angle, weft_direction_deg)))
        if axis_distance < config.twill_axis_exclusion_deg:
            continue
        responses = []
        # OpenCV Gabor theta is the filter normal; add 90 degrees for a line-direction candidate.
        theta = np.deg2rad((angle + 90.0) % 180.0)
        for sigma in config.twill_gabor_sigmas:
            size = int(max(9, round(sigma * 6))) | 1
            wavelengths = config.twill_gabor_wavelengths_px or (config.twill_gabor_wavelength_px,)
            for wavelength in wavelengths:
                kernel = cv2.getGaborKernel(
                    (size, size), sigma, theta, wavelength,
                    0.60, 0.0, ktype=cv2.CV_32F,
                )
                response = np.abs(cv2.filter2D(f, cv2.CV_32F, kernel))
                median = float(np.median(response))
                mad = float(1.4826 * np.median(np.abs(response - median)))
                responses.append((response - median) / max(mad, 1e-6))
        response = np.max(np.stack(responses), axis=0)
        matching = _angular_distance(field_angle, float(angle)) <= config.twill_direction_tolerance_deg
        valid = matching & (coherence >= config.twill_direction_field_min_coherence)
        if int(np.sum(valid)) < 40:
            continue
        threshold = float(np.quantile(response[valid], config.twill_band_response_quantile))
        mask = (valid & (response >= threshold)).astype(np.uint8)
        close_size = max(3, int(config.twill_band_close_kernel_px)) | 1
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((close_size, close_size), dtype=np.uint8))
        if config.twill_band_dilate_px > 0:
            dilate_size = max(3, int(config.twill_band_dilate_px) * 2 + 1)
            mask = cv2.dilate(mask, np.ones((dilate_size, dilate_size), dtype=np.uint8))
        count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
        min_area = max(40, int(h * w * config.twill_band_min_area_ratio))
        kept = np.zeros_like(mask)
        component_area = 0
        for index in range(1, count):
            area = int(stats[index, cv2.CC_STAT_AREA])
            if area >= min_area:
                kept[labels == index] = 255
                component_area += area
        coverage = float(component_area / max(h * w, 1))
        if coverage < config.twill_band_min_coverage:
            continue
        candidates.append({
            "image_line_angle_deg": float(angle),
            "direction_field_coverage": coverage,
            "component_count": int(np.sum(stats[1:, cv2.CC_STAT_AREA] >= min_area)),
            "mean_response": float(np.mean(response[kept > 0])),
            "mask": kept,
        })
    candidates.sort(key=lambda item: (item["direction_field_coverage"], item["mean_response"]), reverse=True)
    return candidates


def _estimate_twill_period(mask: np.ndarray, line_angle_deg: float, config: EngineConfig) -> tuple[float | None, float]:
    """Estimate a non-trivial periodic peak along the normal of accepted bands."""
    h, w = mask.shape[:2]
    rotation = float(line_angle_deg) - 90.0
    aligned = cv2.warpAffine(mask.astype(np.float32), cv2.getRotationMatrix2D((w / 2.0, h / 2.0), rotation, 1.0), (w, h))
    profile = np.mean(aligned, axis=0)
    profile -= float(np.mean(profile))
    energy = float(np.dot(profile, profile))
    if energy < 1e-6:
        return None, 0.0
    correlation = np.correlate(profile, profile, mode="full")[len(profile) - 1:] / energy
    minimum = max(4, int(config.twill_period_min_px))
    maximum = min(len(profile) // 3, int(config.twill_period_max_px))
    if maximum <= minimum:
        return None, 0.0
    values = correlation[minimum:maximum + 1]
    local_peaks = np.flatnonzero((values[1:-1] >= values[:-2]) & (values[1:-1] >= values[2:])) + 1
    if not len(local_peaks):
        return None, 0.0
    best = int(local_peaks[np.argmax(values[local_peaks])]) + minimum
    peak = float(correlation[best])
    return (float(best), peak) if peak >= config.twill_period_min_peak_ratio else (None, peak)


def _fit_line(points: np.ndarray) -> tuple[np.ndarray, np.ndarray] | None:
    if len(points) < 4:
        return None
    centre = np.mean(points, axis=0)
    _, _, vh = np.linalg.svd(points - centre, full_matrices=False)
    direction = vh[0]
    norm = float(np.linalg.norm(direction))
    if norm < 1e-9:
        return None
    return centre, direction / norm


def _intersection(first: tuple[np.ndarray, np.ndarray], second: tuple[np.ndarray, np.ndarray]) -> np.ndarray | None:
    p, dp = first
    q, dq = second
    matrix = np.column_stack((dp, -dq))
    if abs(float(np.linalg.det(matrix))) < 1e-4:
        return None
    t, _ = np.linalg.solve(matrix, q - p)
    return p + float(t) * dp


def _sample_line_contrast(gray: np.ndarray, point: np.ndarray, direction: np.ndarray, half_length: float) -> float:
    """Return a robust directional contrast around one yarn crossing.

    Several adjacent profiles and two probe scales reduce the influence of a
    single highlight, shadow or fibre edge.  The score is normalized by local
    profile noise, so crossings from unevenly illuminated tiles remain comparable.
    """
    direction = np.asarray(direction, dtype=np.float32)
    direction /= max(float(np.linalg.norm(direction)), 1e-9)
    normal = np.asarray([-direction[1], direction[0]], dtype=np.float32)
    scores: list[float] = []
    for scale in (0.72, 1.0):
        radius = max(2.0, float(half_length) * scale)
        offsets = np.linspace(-radius, radius, 17, dtype=np.float32)
        for parallel_shift in (-0.22, 0.0, 0.22):
            origin = point + direction * (float(half_length) * parallel_shift)
            coords = (origin[None, :] + offsets[:, None] * normal[None, :]).astype(np.float32)
            values = cv2.remap(
                gray, coords[:, 0:1], coords[:, 1:2], cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_REFLECT101,
            ).reshape(-1).astype(np.float64)
            trend = np.linspace(float(values[0]), float(values[-1]), len(values))
            residual = values - trend
            span = float(np.percentile(residual, 85) - np.percentile(residual, 15))
            differences = np.diff(residual)
            noise = float(1.4826 * np.median(np.abs(differences - np.median(differences))))
            scores.append(span / max(1.0, noise))
    return float(np.median(scores))


def _intersection_confidence(
    warp_contrast: float,
    weft_contrast: float,
    contrast_threshold: float,
    contrast_scale: float,
    signal_scale: float,
) -> float:
    """Score a retained crossing by separation, signal strength and threshold margin."""
    warp = max(float(warp_contrast), 0.0)
    weft = max(float(weft_contrast), 0.0)
    difference = abs(warp - weft)
    signal = warp + weft
    separation = difference / max(signal, 1e-9)
    strength = min(1.0, signal / max(float(signal_scale), 1e-9))
    margin = min(
        1.0,
        max(0.0, (difference - float(contrast_threshold)) / max(float(contrast_scale) - float(contrast_threshold), 1e-9)),
    )
    return float(np.clip(0.45 * separation + 0.35 * strength + 0.20 * margin, 0.05, 1.0))


def _binary_run_lengths(signs: dict[tuple[int, int], float], axis: int) -> list[int]:
    """Measure contiguous visible-float runs across rows or columns of a crossing grid."""
    groups: dict[int, list[tuple[int, float]]] = {}
    for (row, column), value in signs.items():
        group, position = (row, column) if axis == 1 else (column, row)
        groups.setdefault(group, []).append((position, value))
    lengths: list[int] = []
    for values in groups.values():
        values.sort(key=lambda item: item[0])
        last_position, last_value, length = values[0][0], values[0][1], 1
        for position, value in values[1:]:
            if position == last_position + 1 and value == last_value:
                length += 1
            else:
                lengths.append(length)
                length = 1
            last_position, last_value = position, value
        lengths.append(length)
    return lengths


def _diagonal_float_chains(
    signs: dict[tuple[int, int], float],
    points: dict[tuple[int, int], np.ndarray],
    step: tuple[int, int],
    min_points: int,
) -> list[dict]:
    """Find same-state float chains along one centreline-grid diagonal."""
    chains: list[dict] = []
    visited: set[tuple[int, int]] = set()
    for node in sorted(signs):
        if node in visited:
            continue
        previous = (node[0] - step[0], node[1] - step[1])
        if previous in signs and signs[previous] == signs[node]:
            continue
        chain = [node]
        next_node = (node[0] + step[0], node[1] + step[1])
        while next_node in signs and signs[next_node] == signs[node]:
            chain.append(next_node)
            next_node = (next_node[0] + step[0], next_node[1] + step[1])
        visited.update(chain)
        if len(chain) < min_points:
            continue
        coordinates = np.asarray([points[item] for item in chain], dtype=np.float64)
        fit = _fit_line(coordinates)
        if fit is None:
            continue
        _, direction = fit
        angle = float(np.degrees(np.arctan2(direction[1], direction[0])) % 180.0)
        chains.append({
            "node_count": int(len(chain)),
            "state": "warp_visible" if signs[node] > 0 else "weft_visible",
            "image_line_angle_deg": round(angle, 3),
            "points": coordinates,
        })
    return chains


def _circular_run_lengths(values: list[float]) -> list[int]:
    """Return runs in a row, allowing a repeat pattern to wrap at the edge."""
    if not values:
        return []
    runs: list[int] = []
    current = 1
    for previous, value in zip(values, values[1:]):
        if value == previous:
            current += 1
        else:
            runs.append(current)
            current = 1
    runs.append(current)
    if len(runs) > 1 and values[0] == values[-1]:
        runs[0] += runs.pop()
    return runs


def _linear_run_lengths(values: list[float]) -> list[int]:
    if not values:
        return []
    runs: list[int] = []
    current = 1
    for previous, value in zip(values, values[1:]):
        if value == previous:
            current += 1
        else:
            runs.append(current)
            current = 1
    runs.append(current)
    return runs


def _weave_template_scores(matrix: np.ndarray, confidence: np.ndarray | None = None) -> dict[str, float]:
    """Compare the valid float matrix with canonical 1/1, 2/1 and 3/1 repeats.

    This is a structural consistency check, not a learned classifier.  All cyclic
    shifts, transposition and sign inversion are tested because the first visible
    yarn and warp/weft naming are not fixed by the image crop.
    """
    size = 12
    templates: dict[str, np.ndarray] = {}
    plain = np.fromfunction(lambda row, col: np.where((row + col) % 2 == 0, 1.0, -1.0), (size, size))
    templates["plain"] = plain
    for repeat in (2, 3):
        template = np.empty((size, size), dtype=np.float32)
        for row in range(size):
            for column in range(size):
                template[row, column] = 1.0 if ((column - row) % (repeat + 1)) < repeat else -1.0
        templates[f"{repeat}/1"] = template
    scores: dict[str, float] = {}
    for name, template in templates.items():
        best = 0.0
        for transpose in (False, True):
            candidate = template.T if transpose else template
            for invert in (False, True):
                oriented = -candidate if invert else candidate
                for row_shift in range(repeat + 1 if name != "plain" else 2):
                    for column_shift in range(repeat + 1 if name != "plain" else 2):
                        shifted = np.roll(oriented, (row_shift, column_shift), axis=(0, 1))
                        height = min(matrix.shape[0], size)
                        width = min(matrix.shape[1], size)
                        observed = matrix[:height, :width]
                        expected = shifted[:height, :width]
                        valid = np.isfinite(observed)
                        if confidence is not None:
                            observed_confidence = np.asarray(confidence[:height, :width], dtype=np.float64)
                            valid &= np.isfinite(observed_confidence) & (observed_confidence > 0.0)
                        if int(np.sum(valid)) < 9:
                            continue
                        matches = observed[valid] == expected[valid]
                        if confidence is None:
                            score = float(np.mean(matches))
                        else:
                            observed_confidence = np.clip(observed_confidence[valid], 0.0, 1.0)
                            weight_sum = float(np.sum(observed_confidence))
                            if weight_sum <= 1e-9:
                                continue
                            score = float(np.sum(observed_confidence * matches) / weight_sum)
                        best = max(best, score)
        scores[name] = best
    return scores


def _classify_weave_matrix(
    signs: dict[tuple[int, int], float],
    config: EngineConfig,
    intersection_confidence: dict[tuple[int, int], float] | None = None,
) -> dict:
    """Classify a small interlacing matrix using float-run and repeat evidence.

    The matrix is an evidence-level representation: +1 means warp-visible and -1
    means weft-visible.  It is deliberately conservative and reports LOW when the
    available grid cannot support a repeat-unit decision.
    """
    if not signs:
        return {
            "weave_type": None, "weave_status": "NOT_AVAILABLE",
            "weave_candidate": None, "weave_result_kind": "NO_EVIDENCE",
            "candidate_confidence": 0.0,
            "reasons": ["WEAVE_FLOAT_MATRIX_EMPTY"], "valid_ratio": 0.0,
        }
    rows = sorted({row for row, _ in signs})
    columns = sorted({column for _, column in signs})
    matrix = np.full((len(rows), len(columns)), np.nan, dtype=np.float32)
    confidence_matrix = np.zeros((len(rows), len(columns)), dtype=np.float32)
    row_index = {value: index for index, value in enumerate(rows)}
    column_index = {value: index for index, value in enumerate(columns)}
    for (row, column), value in signs.items():
        matrix[row_index[row], column_index[column]] = float(value)
        confidence_matrix[row_index[row], column_index[column]] = float(np.clip(
            np.nan_to_num((intersection_confidence or {}).get((row, column), 1.0), nan=0.0, posinf=1.0, neginf=0.0),
            0.0, 1.0,
        ))
    valid = np.isfinite(matrix)
    valid_ratio = float(np.mean(valid))
    if matrix.shape[0] < 3 or matrix.shape[1] < 3 or valid_ratio < 0.70:
        return {
            "weave_type": None, "weave_status": "LOW_CONFIDENCE",
            "weave_candidate": None, "weave_result_kind": "CANDIDATE_UNCERTAIN",
            "candidate_confidence": round(valid_ratio * 0.5, 4),
            "reasons": ["WEAVE_FLOAT_MATRIX_INSUFFICIENT"],
            "valid_ratio": round(valid_ratio, 4),
            "matrix_shape": [int(matrix.shape[0]), int(matrix.shape[1])],
        }

    # Find the strongest repeated rectangular tile.  This is evidence for a
    # repeat unit, not a learned classifier.
    best_repeat: tuple[float, int, int] | None = None
    for row_period in range(1, min(6, matrix.shape[0] // 2) + 1):
        for column_period in range(1, min(6, matrix.shape[1] // 2) + 1):
            row_first = matrix[:-row_period, :]
            row_second = matrix[row_period:, :]
            col_first = matrix[:, :-column_period]
            col_second = matrix[:, column_period:]
            row_mask = np.isfinite(row_first) & np.isfinite(row_second)
            col_mask = np.isfinite(col_first) & np.isfinite(col_second)
            if int(np.sum(row_mask)) < 9 or int(np.sum(col_mask)) < 9:
                continue
            row_weights = np.minimum(
                confidence_matrix[:-row_period, :][row_mask],
                confidence_matrix[row_period:, :][row_mask],
            )
            col_weights = np.minimum(
                confidence_matrix[:, :-column_period][col_mask],
                confidence_matrix[:, column_period:][col_mask],
            )
            row_weight_sum = float(np.sum(row_weights))
            col_weight_sum = float(np.sum(col_weights))
            if row_weight_sum <= 1e-9 or col_weight_sum <= 1e-9:
                continue
            row_score = float(np.sum(row_weights * (row_first[row_mask] == row_second[row_mask])) / row_weight_sum)
            col_score = float(np.sum(col_weights * (col_first[col_mask] == col_second[col_mask])) / col_weight_sum)
            score = min(row_score, col_score)
            candidate = (score, row_period, column_period)
            if best_repeat is None or score > best_repeat[0] or (
                score == best_repeat[0] and row_period * column_period < best_repeat[1] * best_repeat[2]
            ):
                best_repeat = candidate

    row_runs: list[int] = []
    column_runs: list[int] = []
    for row in matrix:
        values = row[np.isfinite(row)].tolist()
        row_runs.extend(_linear_run_lengths(values))
    for column in matrix.T:
        values = column[np.isfinite(column)].tolist()
        column_runs.extend(_linear_run_lengths(values))
    all_runs = row_runs + column_runs
    if not all_runs:
        return {
            "weave_type": None, "weave_status": "LOW_CONFIDENCE",
            "weave_candidate": None, "weave_result_kind": "CANDIDATE_UNCERTAIN",
            "candidate_confidence": round(valid_ratio * 0.5, 4),
            "reasons": ["WEAVE_FLOAT_RUNS_EMPTY"], "valid_ratio": round(valid_ratio, 4),
        }
    max_run = int(max(all_runs))
    run_counts = {length: int(sum(run == length for run in all_runs)) for length in (2, 3)}
    dominant_float_run = max(run_counts, key=run_counts.get) if max(run_counts.values()) else max_run
    adjacent_pairs = []
    for row in matrix:
        values = row[np.isfinite(row)]
        if len(values) > 1:
            adjacent_pairs.extend((values[:-1] != values[1:]).tolist())
    for column in matrix.T:
        values = column[np.isfinite(column)]
        if len(values) > 1:
            adjacent_pairs.extend((values[:-1] != values[1:]).tolist())
    alternation_ratio = float(np.mean(adjacent_pairs)) if adjacent_pairs else 0.0
    non_single_runs = [run for run in all_runs if run >= 2]
    dominant_run_ratio = float(
        sum(run == dominant_float_run for run in non_single_runs) / max(len(non_single_runs), 1)
    )
    run_one = int(sum(run == 1 for run in all_runs))
    run_one_ratio = float(run_one / len(all_runs))
    repeat_score = float(best_repeat[0]) if best_repeat is not None else 0.0
    valid_confidence = confidence_matrix[valid]
    confidence_mean = float(np.mean(valid_confidence)) if valid_confidence.size else 0.0
    confidence_weight_sum = float(np.sum(valid_confidence))
    repeat_unit = [int(best_repeat[1]), int(best_repeat[2])] if best_repeat is not None else None
    template_scores = _weave_template_scores(matrix, confidence_matrix)
    ranked_templates = sorted(template_scores.items(), key=lambda item: item[1], reverse=True)
    template_candidate = ranked_templates[0][0]
    template_score = float(ranked_templates[0][1])
    template_margin = template_score - float(ranked_templates[1][1])
    weave_type = None
    if (
        template_candidate == "plain"
        and template_score >= 0.70
        and template_margin >= 0.08
        and alternation_ratio >= 0.70
    ):
        weave_type = "plain"
    elif (
        dominant_float_run in (2, 3)
        and run_one_ratio >= 0.30
        and dominant_run_ratio >= 0.35
        and repeat_score >= 0.70
        and template_candidate == f"{dominant_float_run}/1"
        and template_score >= 0.62
        and template_margin >= 0.01
    ):
        weave_type = f"{dominant_float_run}/1"
    # Long-float/satin-like patterns are outside the current 2/1 and 3/1
    # recognition scope. Keep their evidence, but do not report a PASS type.
    unsupported_long_float = max_run >= 4 and repeat_score >= 0.70
    reasons: list[str] = []
    if repeat_score < 0.55:
        reasons.append("WEAVE_REPEAT_CONSISTENCY_LOW")
    if weave_type is None and alternation_ratio >= 0.86:
        reasons.append("WEAVE_PLAIN_PATTERN_AMBIGUOUS")
    if weave_type is None:
        reasons.append("WEAVE_PATTERN_NOT_IN_V1_RULES")
    if unsupported_long_float and "WEAVE_PATTERN_NOT_IN_V1_RULES" not in reasons:
        reasons.append("WEAVE_LONG_FLOAT_OUTSIDE_V1_SCOPE")
    if weave_type is None and template_score < 0.62:
        reasons.append("WEAVE_TEMPLATE_MATCH_LOW")
    status = "PASS" if weave_type is not None and not reasons else "LOW_CONFIDENCE"
    candidate_confidence = float(valid_ratio * confidence_mean * repeat_score)
    if weave_type is not None:
        candidate_confidence *= min(1.0, 0.5 + 0.5 * max(dominant_run_ratio, alternation_ratio))
    result_kind = "CANDIDATE" if weave_type is not None else "CANDIDATE_UNCERTAIN"
    return {
        "weave_type": weave_type,
        "weave_status": status,
        "weave_candidate": weave_type,
        "weave_result_kind": result_kind,
        "candidate_confidence": round(candidate_confidence, 4),
        "reasons": reasons,
        "valid_ratio": round(valid_ratio, 4),
        "matrix_shape": [int(matrix.shape[0]), int(matrix.shape[1])],
        "max_float_run": max_run,
        "unsupported_long_float": bool(unsupported_long_float),
        "dominant_float_run": int(dominant_float_run),
        "float_run_counts": run_counts,
        "alternation_ratio": round(alternation_ratio, 4),
        "dominant_run_ratio": round(dominant_run_ratio, 4),
        "run_one_ratio": round(run_one_ratio, 4),
        "repeat_consistency": round(repeat_score, 4),
        "repeat_weight_sum": round(confidence_weight_sum, 4),
        "repeat_unit": repeat_unit,
        "template_scores": {key: round(value, 4) for key, value in template_scores.items()},
        "template_candidate": template_candidate,
        "template_score": round(template_score, 4),
        "template_margin": round(template_margin, 4),
        "template_weight_mean": round(confidence_mean, 4),
        "template_weight_sum": round(confidence_weight_sum, 4),
        "float_matrix": [[int(value) if np.isfinite(value) else 0 for value in row] for row in matrix],
    }


def _interlacing_topology(
    front: np.ndarray,
    transmission: np.ndarray | None,
    warp_seed: dict | None,
    weft_seed: dict | None,
    normalization: dict | None,
    config: EngineConfig,
) -> dict:
    """Build a centreline-defined crossing grid for later twill/weave evidence.

    The grid reads existing cleaned centreline geometry only.  It intentionally does
    not create, shift, or clean any density centreline.
    """
    if transmission is None or warp_seed is None or weft_seed is None or normalization is None:
        return {"status": "NOT_AVAILABLE", "reasons": ["TWILL_CENTERLINE_CONTEXT_UNAVAILABLE"], "intersection_count": 0}
    registration = estimate_reflection_registration(front, transmission, config)
    if registration["status"] == "FAIL":
        return {"status": "NOT_AVAILABLE", "reasons": ["TWILL_CENTERLINE_REGISTRATION_UNAVAILABLE"], "intersection_count": 0}
    matrix = np.asarray(registration["matrix_transmission_to_reflection"], dtype=np.float32)
    warp_lines = [line for line in map_centerlines_to_reflection(warp_seed, normalization, matrix) if len(line) >= 4]
    weft_lines = [line for line in map_centerlines_to_reflection(weft_seed, normalization, matrix) if len(line) >= 4]
    limit = int(config.twill_topology_max_centerlines)
    warp_lines = warp_lines[max(0, (len(warp_lines) - limit) // 2):][:limit]
    weft_lines = weft_lines[max(0, (len(weft_lines) - limit) // 2):][:limit]
    warp_fits = [fit for line in warp_lines if (fit := _fit_line(np.asarray(line, dtype=np.float64))) is not None]
    weft_fits = [fit for line in weft_lines if (fit := _fit_line(np.asarray(line, dtype=np.float64))) is not None]
    if len(warp_fits) < 4 or len(weft_fits) < 4:
        return {"status": "NOT_AVAILABLE", "reasons": ["TWILL_CENTERLINE_GRID_INSUFFICIENT"], "intersection_count": 0}
    gray = local_normalize(to_gray(front))
    warp_pitch = float(warp_seed["median_center_spacing_px"]) / float(normalization["resize_scale"])
    weft_pitch = float(weft_seed["median_center_spacing_px"]) / float(normalization["resize_scale"])
    half = max(2.0, min(warp_pitch, weft_pitch) * float(config.twill_topology_probe_ratio))
    scores = []
    crossing_points: dict[tuple[int, int], np.ndarray] = {}
    for warp_index, warp_line in enumerate(warp_fits):
        for weft_index, weft_line in enumerate(weft_fits):
            point = _intersection(warp_line, weft_line)
            if point is None or point[0] < half or point[1] < half or point[0] >= gray.shape[1] - half or point[1] >= gray.shape[0] - half:
                continue
            warp_contrast = _sample_line_contrast(gray, point, warp_line[1], half)
            weft_contrast = _sample_line_contrast(gray, point, weft_line[1], half)
            scores.append((warp_index, weft_index, warp_contrast, weft_contrast, warp_contrast - weft_contrast))
            crossing_points[(warp_index, weft_index)] = point
    if len(scores) < config.twill_topology_min_intersections:
        return {"status": "NOT_AVAILABLE", "reasons": ["TWILL_INTERSECTION_EVIDENCE_INSUFFICIENT"], "intersection_count": int(len(scores))}
    values = np.asarray([score for _, _, _, _, score in scores], dtype=np.float64)
    warp_values = np.asarray([score for _, _, score, _, _ in scores], dtype=np.float64)
    weft_values = np.asarray([score for _, _, _, score, _ in scores], dtype=np.float64)
    absolute_values = np.abs(values)
    contrast_scale = float(np.median(absolute_values))
    signal_scale = float(np.median(warp_values + weft_values))
    contrast_threshold = contrast_scale * float(config.twill_topology_min_contrast_ratio)
    signs = {
        (i, j): (1.0 if value >= 0.0 else -1.0)
        for (i, j, _, _, value) in scores
        if abs(float(value)) >= contrast_threshold
    }
    intersection_confidence = {
        (i, j): _intersection_confidence(
            warp_contrast, weft_contrast, contrast_threshold, contrast_scale, signal_scale,
        )
        for (i, j, warp_contrast, weft_contrast, value) in scores
        if (i, j) in signs
    }
    if len(signs) < config.twill_topology_min_intersections:
        return {
            "status": "AVAILABLE",
            "reasons": ["TWILL_FLOAT_CONTRAST_INSUFFICIENT"],
            "weave_type": None,
            "weave_status": "LOW_CONFIDENCE",
            "weave_candidate": None,
            "weave_result_kind": "CANDIDATE_UNCERTAIN",
            "candidate_confidence": 0.0,
            "weave_evidence": {
                "valid_ratio": round(float(len(signs) / max(len(scores), 1)), 4),
                "contrast_threshold": round(contrast_threshold, 4),
                "intersection_confidence_mean": round(float(np.mean(list(intersection_confidence.values()))) if intersection_confidence else 0.0, 4),
            },
            "intersection_count": int(len(scores)),
            "valid_float_intersection_count": int(len(signs)),
        }
    horizontal_runs = _binary_run_lengths(signs, axis=1)
    vertical_runs = _binary_run_lengths(signs, axis=0)
    all_runs = np.asarray(horizontal_runs + vertical_runs, dtype=np.float64)
    diagonal_pairs = {"down_right": [], "down_left": []}
    for (i, j), value in signs.items():
        for key, neighbour in (("down_right", (i + 1, j + 1)), ("down_left", (i + 1, j - 1))):
            if neighbour in signs:
                diagonal_pairs[key].append(value * signs[neighbour])
    correlations = {key: float(np.mean(pair_values)) if pair_values else 0.0 for key, pair_values in diagonal_pairs.items()}
    dominant_diagonal = max(correlations, key=lambda key: abs(correlations[key]))
    weave = _classify_weave_matrix(signs, config, intersection_confidence)
    chain_specs = {"down_right": (1, 1), "down_left": (1, -1)}
    chains_by_diagonal = {
        key: _diagonal_float_chains(signs, crossing_points, step, config.twill_topology_min_chain_points)
        for key, step in chain_specs.items()
    }
    chain_candidates = []
    for diagonal, chains in chains_by_diagonal.items():
        support = int(sum(chain["node_count"] for chain in chains))
        coverage = float(support / max(len(scores), 1))
        if not chains:
            continue
        weights = np.asarray([chain["node_count"] for chain in chains], dtype=np.float64)
        angles = np.asarray([chain["image_line_angle_deg"] for chain in chains], dtype=np.float64)
        doubled = np.deg2rad(2.0 * angles)
        image_angle = float((np.degrees(np.angle(np.sum(weights * np.exp(1j * doubled)))) * 0.5) % 180.0)
        angle_delta = _angular_distance(angles, image_angle)
        spread = float(np.sqrt(np.average(angle_delta * angle_delta, weights=weights)))
        chain_candidates.append({
            "grid_diagonal": diagonal,
            "image_line_angle_deg": round(image_angle, 3),
            "direction": _direction_name(image_angle),
            "chain_count": int(len(chains)),
            "max_chain_points": int(max(chain["node_count"] for chain in chains)),
            "support_points": support,
            "coverage": round(coverage, 4),
            "angle_spread_deg": round(spread, 3),
        })
    chain_candidates.sort(key=lambda item: (item["coverage"], item["max_chain_points"]), reverse=True)
    return {
        "status": "AVAILABLE",
        "reasons": list(weave["reasons"]),
        "weave_type": weave["weave_type"],
        "weave_status": weave["weave_status"],
        "weave_candidate": weave.get("weave_candidate", weave["weave_type"]),
        "weave_result_kind": weave.get("weave_result_kind", "CANDIDATE_UNCERTAIN"),
        "candidate_confidence": weave.get("candidate_confidence", 0.0),
        "weave_evidence": weave,
        "intersection_count": int(len(scores)),
        "valid_float_intersection_count": int(len(signs)),
        "float_intersection_valid_ratio": round(float(len(signs) / max(len(scores), 1)), 4),
        "float_contrast_median": round(contrast_scale, 4),
        "float_contrast_threshold": round(contrast_threshold, 4),
        "intersection_confidence_mean": round(float(np.mean(list(intersection_confidence.values()))), 4),
        "intersection_confidence_min": round(float(np.min(list(intersection_confidence.values()))), 4),
        "intersection_confidence_weight_sum": round(float(np.sum(list(intersection_confidence.values()))), 4),
        "warp_line_count": int(len(warp_fits)), "weft_line_count": int(len(weft_fits)),
        "contrast_balance": round(float(np.mean(values >= 0.0)), 4),
        "float_run_count": int(len(all_runs)),
        "float_run_p50": round(float(np.percentile(all_runs, 50)), 3),
        "float_run_p90": round(float(np.percentile(all_runs, 90)), 3),
        "float_run_mean": round(float(np.mean(all_runs)), 3),
        "diagonal_correlation": {key: round(value, 4) for key, value in correlations.items()},
        "dominant_diagonal": dominant_diagonal,
        "diagonal_float_chain_candidates": chain_candidates,
        "method": "CLEAN_CENTERLINE_CROSSING_GRID__REFLECTION_DIRECTIONAL_CONTRAST",
    }


def analyze_twill(
    front: np.ndarray,
    warp_direction_deg: float,
    weft_direction_deg: float,
    config: EngineConfig = DEFAULT_CONFIG,
    transmission: np.ndarray | None = None,
    warp_seed: dict | None = None,
    weft_seed: dict | None = None,
    normalization: dict | None = None,
) -> dict:
    """Detect a dominant diagonal surface direction on the reflection image.

    This is intentionally a separate structural-analysis stage.  It does not alter
    the orientation, centreline or density results used as its geometric references.
    """
    gray = center_crop(to_gray(front), 0.86)
    gray, scale = resize_max_side(gray, config.twill_max_side)
    normalized = local_normalize(gray)
    bands = _gabor_band_candidates(normalized, warp_direction_deg, weft_direction_deg, config)
    if not bands:
        return {
            "status": "SEPARATE_RESULTS", "direction": None, "angle_deg": None,
            "direction_status": "FAIL", "angle_status": "FAIL",
            "direction_reasons": ["TWILL_COHERENT_DIAGONAL_BAND_NOT_FOUND"],
            "angle_reasons": ["TWILL_COHERENT_DIAGONAL_BAND_NOT_FOUND"],
            "reasons": ["TWILL_COHERENT_DIAGONAL_BAND_NOT_FOUND"],
            "diagonal_segment_count": 0, "selected_segment_count": 0, "evidence": [],
            "band_evidence": [], "twill_period_px": None,
            "interlacing_topology": {"status": "NOT_USED_BY_TWILL", "reasons": []},
            "weave_type": None, "weave_status": "NOT_AVAILABLE",
            "weave_reasons": ["WEAVE_TWILL_BAND_NOT_FOUND"],
            "method": "REFLECTION_GABOR_ORIENTATION__LOCAL_DIRECTION_FIELD__BAND_HOUGH_GEOMETRY",
        }
    band = bands[0]
    all_segments, all_lengths, all_angles = _extract_diagonal_segments(
        normalized, warp_direction_deg, weft_direction_deg, config,
    )
    segments, lengths, angles = _extract_diagonal_segments(
        normalized, warp_direction_deg, weft_direction_deg, config,
        target_angle_deg=band["image_line_angle_deg"],
    )
    if len(segments) < config.twill_min_segments:
        return {
            "status": "SEPARATE_RESULTS", "direction": None, "angle_deg": None,
            "direction_status": "FAIL", "angle_status": "FAIL",
            "direction_reasons": ["TWILL_BAND_HOUGH_SEGMENTS_INSUFFICIENT"],
            "angle_reasons": ["TWILL_BAND_HOUGH_SEGMENTS_INSUFFICIENT"],
            "reasons": ["TWILL_BAND_HOUGH_SEGMENTS_INSUFFICIENT"],
            "diagonal_segment_count": int(len(segments)), "evidence": [],
            "band_evidence": [{key: round(float(value), 4) if isinstance(value, (float, np.floating)) else value for key, value in band.items() if key != "mask"}],
            "twill_period_px": _estimate_twill_period(band["mask"], band["image_line_angle_deg"], config)[0],
            "interlacing_topology": {"status": "NOT_USED_BY_TWILL", "reasons": []},
            "weave_type": None, "weave_status": "NOT_AVAILABLE",
            "weave_reasons": ["WEAVE_TWILL_SEGMENTS_INSUFFICIENT"],
            "method": "REFLECTION_GABOR_ORIENTATION__LOCAL_DIRECTION_FIELD__BAND_HOUGH_GEOMETRY",
        }

    angle, _, spread = _dominant_orientation(angles, lengths)
    all_length = max(float(np.sum(all_lengths)), 1e-9)
    raw_direction_support = float(
        np.sum(all_lengths[_angular_distance(all_angles, angle) <= config.twill_direction_tolerance_deg])
        / all_length
    )
    candidate_direction_support = float(_dominant_orientation(angles, lengths)[1])
    band_direction_support, band_segment_length, band_segment_count = _band_segment_support(
        all_segments, all_lengths, all_angles, band["mask"], angle,
        config.twill_direction_tolerance_deg,
    )
    # The candidate band is already constrained by Gabor and local orientation.
    # Use it to exclude unrelated diagonal highlights from the direction evidence.
    direction_support = (
        candidate_direction_support
        if len(segments) >= config.twill_band_min_segments
        else (band_direction_support if band_segment_count >= config.twill_band_min_segments else raw_direction_support)
    )
    relative_angle = float(_angular_distance(angle, warp_direction_deg))
    direction = _direction_name(angle)

    scale_votes = []
    for analysis_scale in config.twill_analysis_scales:
        if analysis_scale >= 0.999:
            scaled = normalized
        else:
            scaled = cv2.resize(normalized, None, fx=analysis_scale, fy=analysis_scale, interpolation=cv2.INTER_AREA)
        scale_bands = _gabor_band_candidates(scaled, warp_direction_deg, weft_direction_deg, config)
        if not scale_bands:
            continue
        scale_band = scale_bands[0]
        _, scale_lengths, scale_angles = _extract_diagonal_segments(
            scaled, warp_direction_deg, weft_direction_deg, config,
            target_angle_deg=scale_band["image_line_angle_deg"],
        )
        if len(scale_angles) < config.twill_min_segments:
            continue
        scale_angle, scale_dominance, scale_spread = _dominant_orientation(scale_angles, scale_lengths)
        scale_votes.append({
            "scale": round(float(analysis_scale), 3),
            "image_line_angle_deg": round(float(scale_angle), 3),
            "direction": _direction_name(scale_angle),
            "dominance": round(float(scale_dominance), 5),
            "angle_spread_deg": round(float(scale_spread), 3),
            "segment_count": int(len(scale_angles)),
            "band_coverage": round(float(scale_band["direction_field_coverage"]), 5),
        })
    agree = [
        vote for vote in scale_votes
        if vote["direction"] == direction
        and float(_angular_distance(vote["image_line_angle_deg"], angle)) <= config.twill_scale_angle_tolerance_deg
    ]
    scale_consensus = float(len(agree) / max(len(scale_votes), 1))
    reasons: list[str] = []
    direction_reasons: list[str] = []
    angle_reasons: list[str] = []
    if direction_support < config.twill_low_dominance:
        direction_reasons.append("TWILL_DIRECTION_DOMINANCE_LOW")
    if spread > config.twill_low_spread_deg:
        angle_reasons.append("TWILL_ANGLE_SPREAD_HIGH")
    if scale_consensus < config.twill_scale_consensus_ratio:
        angle_reasons.append("TWILL_SCALE_DIRECTION_INCONSISTENT")
    period_px, period_peak = _estimate_twill_period(band["mask"], angle, config)
    if float(band["direction_field_coverage"]) < config.twill_band_min_coverage:
        direction_reasons.append("TWILL_DIAGONAL_BAND_COVERAGE_LOW")
    direction_status = "PASS" if (
        direction_support >= config.twill_pass_dominance
        and float(band["direction_field_coverage"]) >= config.twill_band_pass_coverage
    ) else "LOW_CONFIDENCE"
    angle_status = "PASS" if (
        spread <= config.twill_pass_spread_deg
        and scale_consensus >= config.twill_scale_consensus_ratio
    ) else "LOW_CONFIDENCE"
    reasons = direction_reasons + angle_reasons
    selected = _angular_distance(angles, angle) <= 12.5
    order = np.argsort(np.where(selected, lengths, -1.0))[::-1]
    evidence = []
    for index in order[:80]:
        if not selected[index]:
            break
        x1, y1, x2, y2 = segments[index]
        evidence.append({
            "line": [round(float(x1 / scale), 2), round(float(y1 / scale), 2), round(float(x2 / scale), 2), round(float(y2 / scale), 2)],
            "angle_deg": round(float(angles[index]), 3), "length_px": round(float(lengths[index] / scale), 3),
        })
    candidate_angle = round(relative_angle, 3)
    candidate_direction = direction
    topology = _interlacing_topology(
        front, transmission, warp_seed, weft_seed, normalization, config,
    )
    weave_type = topology.get("weave_type")
    weave_status = topology.get("weave_status", "NOT_AVAILABLE")
    weave_reasons = topology.get("reasons", [])
    weave_candidate = topology.get("weave_candidate", weave_type)
    weave_result_kind = topology.get("weave_result_kind", "NO_EVIDENCE")
    candidate_confidence = topology.get("candidate_confidence", 0.0)
    return {
        "status": "SEPARATE_RESULTS",
        "direction": candidate_direction if direction_status != "FAIL" else None,
        "angle_deg": candidate_angle if angle_status != "FAIL" else None,
        "candidate_direction": candidate_direction, "candidate_angle_deg": candidate_angle,
        "image_line_angle_deg": round(float(angle), 3), "dominance": round(direction_support, 5),
        "direction_support": round(direction_support, 5), "angle_spread_deg": round(spread, 3),
        "raw_direction_support": round(raw_direction_support, 5),
        "candidate_direction_support": round(candidate_direction_support, 5),
        "band_direction_support": round(band_direction_support, 5),
        "band_segment_count": int(band_segment_count),
        "band_segment_length_px": round(float(band_segment_length), 3),
        "direction_status": direction_status, "angle_status": angle_status,
        "direction_reasons": direction_reasons, "angle_reasons": angle_reasons,
        "weave_type": weave_type, "weave_status": weave_status,
        "weave_reasons": weave_reasons,
        "weave_candidate": weave_candidate,
        "weave_result_kind": weave_result_kind,
        "candidate_confidence": candidate_confidence,
        "diagonal_segment_count": int(len(segments)), "selected_segment_count": int(np.sum(selected)),
        "scale_consensus": round(scale_consensus, 5), "scale_evidence": scale_votes, "reasons": reasons,
        "band_evidence": [{key: round(float(value), 4) if isinstance(value, (float, np.floating)) else value for key, value in band.items() if key != "mask"}],
        "twill_period_px": round(float(period_px / scale), 3) if period_px is not None else None,
        "twill_period_peak": round(float(period_peak), 5),
        "interlacing_topology": topology,
        "method": "REFLECTION_GABOR_ORIENTATION__LOCAL_DIRECTION_FIELD__BAND_HOUGH_GEOMETRY",
        "evidence": evidence,
    }
