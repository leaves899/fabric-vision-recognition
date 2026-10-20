"""Independent twill evidence, observed crossing matrices and empirical reference rules."""
from __future__ import annotations

import cv2
import numpy as np
from scipy.ndimage import gaussian_filter1d, map_coordinates

from .primitives import Config, angular_distance, direction_field, grayscale, normalize


def twill_analysis(front, families, cfg):
    gray = grayscale(front)
    scale = min(1., 512 / max(gray.shape))
    small = cv2.resize(gray, None, fx=scale, fy=scale)
    norm = normalize(small, Config())
    axes = [f['angle_deg'] for f in families]
    angles = np.arange(0, 180, 3.)
    allowed = np.array([all(angular_distance(a, axis) > cfg.twill_exclude_yarn_deg for axis in axes) for a in angles])
    spectra = []
    for wavelength in (8., 12., 18.):
        scores = []
        k = int(np.ceil(wavelength * 4)) | 1
        for angle in angles:
            theta = np.deg2rad((angle + 90) % 180)
            # Quadrature pair removes dependence on phase/bright versus dark floats.
            kernels = [cv2.getGaborKernel((k, k), wavelength * .55, theta, wavelength, .5, phase, ktype=cv2.CV_32F)
                       for phase in (0, np.pi / 2)]
            responses = []
            for kernel in kernels:
                kernel -= kernel.mean()
                kernel /= max(float(np.linalg.norm(kernel)), 1e-9)
                responses.append(cv2.filter2D(norm, cv2.CV_32F, kernel))
            margin = k // 2
            energy = responses[0] ** 2 + responses[1] ** 2
            inner = energy[margin:-margin, margin:-margin]
            scores.append(float(np.mean(inner)) if inner.size else 0.)
        spectra.append(np.asarray(scores))
    scaled = np.array([s / max(float(np.max(s)), 1e-9) for s in spectra])
    combined = np.mean(scaled, axis=0)
    candidate_scores = np.where(allowed, combined, -1)
    best = int(np.argmax(candidate_scores))
    angle = float(angles[best]) if allowed.any() and max(float(np.max(s)) for s in spectra) > 1e-6 else None
    winners = [float(angles[np.argmax(np.where(allowed, s, -1))]) for s in scaled] if allowed.any() else []
    edge = cv2.Canny(np.uint8(small * 255), 50, 130)
    lines = cv2.HoughLinesP(edge, 1, np.pi / 180, threshold=25,
                            minLineLength=max(16, min(small.shape) // 10), maxLineGap=6)
    segments = []
    for line in lines[:, 0] if lines is not None else []:
        x1, y1, x2, y2 = map(float, line)
        a = float(np.degrees(np.arctan2(y2 - y1, x2 - x1)) % 180)
        length = float(np.hypot(x2 - x1, y2 - y1))
        if all(angular_distance(a, axis) > cfg.twill_exclude_yarn_deg for axis in axes):
            segments.append(dict(xy=[[x1 / scale, y1 / scale], [x2 / scale, y2 / scale]], angle_deg=a, length_px=length / scale,
                                 supports_candidate=bool(angle is not None and angular_distance(a, angle) <= 12)))
    supported = [s for s in segments if s['supports_candidate']]
    support_fraction = sum(s['length_px'] for s in supported) / max(sum(s['length_px'] for s in segments), 1e-9)
    field, _ = direction_field(small, Config())
    tensor = np.asarray(field['histogram'])
    mass = float(sum(tensor[i] for i in range(180) if angle is not None and angular_distance(i, angle) <= 12))
    dispersion = max([angular_distance(a, angle) for a in winners], default=90.) if angle is not None else None
    reasons = []
    if angle is None or len(supported) < 3:
        reasons.append('insufficient_Hough_support')
    if support_fraction < .35:
        reasons.append('weak_direction_support_fraction')
    if dispersion is None or dispersion > 12:
        reasons.append('multiscale_Gabor_disagreement')
    if mass < .08:
        reasons.append('weak_local_tensor_support')
    gabor_angle = angle
    hough_dispersion = None
    if len(supported) >= 3:
        phases = np.deg2rad([2 * s['angle_deg'] for s in supported])
        weights = np.array([s['length_px'] for s in supported])
        vector = np.sum(weights * np.exp(1j * phases)) / weights.sum()
        angle = float(np.degrees(np.angle(vector)) / 2 % 180)
        hough_dispersion = float(np.degrees(np.sqrt(max(0., -2 * np.log(max(abs(vector), 1e-9))))) / 2)
        if hough_dispersion > 10:
            reasons.append('Hough_angle_dispersion')
    return dict(status='PASS' if not reasons else 'LOW_CONFIDENCE' if angle is not None else 'UNAVAILABLE',
                reasons=reasons, image_angle_deg=angle, acute_angle_deg=min(angle, 180 - angle) if angle is not None else None,
                gabor_angle_deg=gabor_angle, hough_dispersion_deg=hough_dispersion,
                angle_source='length_weighted_Hough_cluster' if len(supported) >= 3 else 'Gabor_candidate',
                direction_scope='image slant only; face, mirroring and warp identity must be checked for physical twill handedness',
                direction='right_rising' if angle is not None and angle > 90 else 'left_rising' if angle is not None and 0 < angle < 90 else 'UNDETERMINED',
                direction_convention='right_rising=/ rises toward upper right; left_rising=\\ rises toward upper left; image y points down',
                multiscale_winner_deg=winners, multiscale_max_deviation_deg=dispersion,
                Hough_support_fraction=support_fraction, tensor_mass_within_12deg=mass,
                spectra=dict(angles_deg=angles.tolist(), wavelengths_px=[8, 12, 18], scores=[s.tolist() for s in spectra]),
                segments=segments, physical_accuracy='NOT_EVALUATED')


def template_match(matrix, cfg):
    m = np.asarray(matrix, int)
    if m.ndim != 2:
        raise ValueError('Float matrix must be two dimensional')
    known = m >= 0
    if np.any(m > 1) or np.any(m < -1):
        raise ValueError('Float matrix cells must be -1 unknown, 0 B top, 1 A top')
    candidates = []
    yy, xx = np.indices(m.shape)
    for name, repeat, top_count in [('1/1', 2, 1), ('2/1', 3, 2), ('3/1', 4, 3)]:
        fits = []
        for slope in (-1, 1):
            for phase in range(repeat):
                pattern = ((yy + slope * xx + phase) % repeat < top_count).astype(int)
                for invert in (False, True):
                    expected = 1 - pattern if invert else pattern
                    score = float(np.mean(m[known] == expected[known])) if known.any() else 0.
                    fits.append(dict(agreement=score, slope=slope, phase=phase, inverted=invert))
        candidates.append(dict(template=name, repeat=repeat, **max(fits, key=lambda f: f['agreement'])))
    candidates.sort(key=lambda c: -c['agreement'])
    coverage = float(known.mean()) if m.size else 0.
    margin = candidates[0]['agreement'] - candidates[1]['agreement']
    reasons = []
    if int(known.sum()) < cfg.weave_min_known or min(m.shape, default=0) < 4:
        reasons.append('insufficient_known_crossings_or_repeats')
    if coverage < cfg.weave_min_coverage:
        reasons.append('insufficient_float_matrix_coverage')
    if candidates[0]['agreement'] < cfg.weave_min_agreement:
        reasons.append('template_agreement_below_threshold')
    if margin < cfg.weave_min_margin:
        reasons.append('competing_templates')
    if min(m.shape, default=0) < 2 * candidates[0]['repeat']:
        reasons.append('fewer_than_two_complete_template_repeats')
    return dict(status='CANDIDATE' if not reasons else 'LOW_CONFIDENCE', reasons=reasons,
                candidate=candidates[0]['template'] if not reasons else None,
                ranked_templates=candidates, margin=margin, known_cells=int(known.sum()), coverage=coverage)


def _track_segments(track, step):
    xy = np.asarray(track['points_xy'])
    frame = np.asarray(track['points'])
    supported = np.diff(frame[:, 0]) <= step * 1.5
    return xy[:-1][supported], xy[1:][supported]


def _intersection(aa, ab, ba, bb):
    if not len(aa) or not len(ba):
        return None
    r = ab - aa
    s = bb - ba
    def cross(a, b):
        return a[..., 0] * b[..., 1] - a[..., 1] * b[..., 0]
    den = cross(r[:, None], s[None])
    delta = ba[None] - aa[:, None]
    nonparallel = abs(den) > 1e-8
    safe_den = np.where(nonparallel, den, 1.)
    t = cross(delta, s[None]) / safe_den
    u = cross(delta, r[:, None]) / safe_den
    hits = np.argwhere(nonparallel & (t >= 0) & (t <= 1) & (u >= 0) & (u <= 1))
    if not len(hits):
        return None
    # A tangled pair with distinct multiple crossings is not a single grid cell.
    pts = np.array([aa[i] + t[i, j] * r[i] for i, j in hits])
    if np.max(np.linalg.norm(pts - pts[0], axis=1)) > 2:
        return None
    return pts.mean(axis=0)


def weave_analysis(front, families, response_images, cfg, registration_ok=True):
    if len(families) != 2:
        return dict(status='UNAVAILABLE', reasons=['two_centerline_families_required'], candidate=None,
                    matrix=[], intersections=[], float_lengths=[])
    h, w = front.shape[:2]
    groups = []
    for family in families:
        angle = np.deg2rad(family['angle_deg'])
        normal = np.array([-np.sin(angle), np.cos(angle)])
        tracks = [t for t in family['tracks'] if t['accepted_candidate']]
        tracks.sort(key=lambda t: float(np.median(np.asarray(t['points_xy']) @ normal)))
        groups.append(tracks)
    matrix = np.full((len(groups[0]), len(groups[1])), -1, int)
    gray = grayscale(front)
    intersections = []
    segments = [[_track_segments(t, f['linking']['sample_step_px']) for t in group]
                for f, group in zip(families, groups)]
    for i, a in enumerate(groups[0]):
        aa, ab = segments[0][i]
        for j, b in enumerate(groups[1]):
            ba, bb = segments[1][j]
            point = _intersection(aa, ab, ba, bb)
            if point is None or not (4 <= point[0] < w - 4 and 4 <= point[1] < h - 4):
                continue
            contrasts = []
            for family in families:
                angle = np.deg2rad(family['angle_deg'])
                tangent = np.array([np.cos(angle), np.sin(angle)])
                normal = np.array([-tangent[1], tangent[0]])
                # Short tangent segment versus its two parallel flanks.
                pitch = family['density'].get('median_spacing_px') or 12.
                radius = float(np.clip(pitch * .15, 2, 6))
                positions = np.linspace(-radius, radius, 7)
                means = []
                for flank in (-radius, 0, radius):
                    xy = point + positions[:, None] * tangent + flank * normal
                    means.append(float(np.mean(map_coordinates(gray, [xy[:, 1], xy[:, 0]], order=1, mode='nearest'))))
                contrasts.append(abs(means[1] - .5 * (means[0] + means[2])))
            denominator = sum(contrasts)
            confidence = abs(contrasts[0] - contrasts[1]) / max(denominator, 1e-9)
            cell = int(contrasts[0] > contrasts[1]) if denominator >= .04 and confidence >= .25 else -1
            matrix[i, j] = cell
            intersections.append(dict(A_track=a['id'], B_track=b['id'], row=i, col=j, xy=point.tolist(),
                                      directional_contrasts=contrasts, confidence=confidence, float_state=cell))
    match = template_match(matrix, cfg)
    if any(f['status'] != 'INTERNAL_CONSISTENT_CANDIDATE' for f in families):
        match['reasons'].append('centerline_topology_or_spacing_not_verified')
    if not registration_ok:
        match['reasons'].append('paired_registration_not_verified')
    if match['reasons']:
        match['status'] = 'LOW_CONFIDENCE'
        match['candidate'] = None
    float_lengths = []
    for axis in (0, 1):
        for line in (matrix if axis == 0 else matrix.T):
            run, previous = 0, -1
            for cell in list(line) + [-1]:
                if cell >= 0 and cell == previous:
                    run += 1
                else:
                    if run:
                        float_lengths.append(dict(axis=axis, state=int(previous), length=run))
                    run = 1 if cell >= 0 else 0
                previous = cell
    return dict(**match, matrix=matrix.tolist(), row_A_track_ids=[t['id'] for t in groups[0]],
                col_B_track_ids=[t['id'] for t in groups[1]], intersections=intersections,
                float_lengths=float_lengths, cell_encoding={'unknown': -1, 'B_top_candidate': 0, 'A_top_candidate': 1},
                conditional_on_complete_yarn_order=True,
                caveat='Directional contrast supplies float candidates, not verified physical over-under labels or complete yarn order',
                physical_accuracy='NOT_EVALUATED')


def yarn_reference(widths, densities, rules):
    """Configurable empirical bins; never invent the report's undisclosed mapping."""
    for rule in rules:
        for key in ['width_mm', 'density_per_cm', 'Ne', 'source']:
            if key not in rule:
                raise ValueError('Empirical rule missing ' + key)
        for key in ['width_mm', 'density_per_cm', 'Ne']:
            bounds = rule[key]
            if len(bounds) != 2 or not all(np.isfinite(v) and v > 0 for v in bounds) or bounds[0] > bounds[1]:
                raise ValueError('Empirical rule requires ordered positive finite bounds: ' + key)
        if not rule['source']:
            raise ValueError('Empirical rule requires provenance')
    output = []
    for width in widths:
        identity = width['identity']
        d = densities['families'].get(identity)
        wmm = width['p10_p50_p90_mm']
        reasons = []
        if not rules:
            reasons.append('report_empirical_bins_not_provided')
        if wmm is None or not d or d['count_per_cm'] is None:
            reasons.append('confirmed_width_and_density_required')
        matches = []
        if not reasons:
            for rule in rules:
                if rule.get('identity', identity) == identity and rule['width_mm'][0] <= wmm[1] <= rule['width_mm'][1] and rule['density_per_cm'][0] <= d['count_per_cm'] <= rule['density_per_cm'][1]:
                    matches.append(rule)
        if len(matches) != 1 and not reasons:
            reasons.append('no_unique_empirical_bin')
        rule = matches[0] if len(matches) == 1 else None
        output.append(dict(family=width['family'], identity=identity,
                           status='AVAILABLE' if rule and not reasons else 'UNAVAILABLE', reasons=reasons,
                           Ne=rule['Ne'] if rule and not reasons else None,
                           tex=[590.5 / rule['Ne'][1], 590.5 / rule['Ne'][0]] if rule and not reasons else None,
                           rule_source=rule['source'] if rule and not reasons else None,
                           input_quality=width['status'], reference_only=True, physical_accuracy='NOT_EVALUATED'))
    return output
