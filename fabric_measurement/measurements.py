"""Normal reflectance profiles, competing edges, pitch gates and robust widths."""
from __future__ import annotations

import numpy as np
from scipy.ndimage import gaussian_filter1d, map_coordinates
from scipy.signal import find_peaks

from .primitives import grayscale


def profile_width(profile, offsets):
    """Select two gradient edges bracketing a ridge center, with explicit rejection."""
    p = gaussian_filter1d(np.asarray(profile, float), .8)
    x = np.asarray(offsets, float)
    center = int(np.argmin(abs(x)))
    border = max(2, len(p) // 8)
    baseline = float(np.median(np.r_[p[:border], p[-border:]]))
    sign = 1 if p[center] >= baseline else -1
    z = sign * (p - baseline)
    nearby = np.flatnonzero(abs(x) <= min(3., .15 * (x[-1] - x[0])))
    peak = int(nearby[np.argmax(z[nearby])])
    amplitude = float(z[peak])
    if amplitude < .04:
        return None, 'low_center_to_background_contrast'
    gradient = np.gradient(z, x)
    left_edges = find_peaks(gradient, prominence=.005)[0]
    right_edges = find_peaks(-gradient, prominence=.005)[0]
    left_edges = left_edges[(left_edges < peak) & (gradient[left_edges] > .008)]
    right_edges = right_edges[(right_edges > peak) & (gradient[right_edges] < -.008)]
    if not len(left_edges) or not len(right_edges):
        return None, 'missing_gradient_edge_support'
    pairs = []
    for li in left_edges:
        for ri in right_edges:
            symmetry = abs((x[li] + x[ri]) / 2 - x[peak])
            edge_score = min(gradient[li], -gradient[ri]) / (1 + symmetry)
            pairs.append((edge_score, int(li), int(ri)))
    _, li, ri = max(pairs)
    lx, rx = float(x[li]), float(x[ri])
    width = rx - lx
    if width <= 1 or abs((lx + rx) / 2 - x[peak]) > width * .4:
        return None, 'too_narrow_or_asymmetric_profile'
    return dict(width_px=float(width), edge_offsets_px=[lx, rx], peak_offset_px=float(x[peak]),
                contrast=amplitude, polarity='bright' if sign > 0 else 'dark',
                left_edge_candidates=x[left_edges].tolist(), right_edge_candidates=x[right_edges].tolist()), None


def measure_widths(front, families, cfg, mm_per_px=None, registration_ok=True):
    gray = grayscale(front)
    h, w = gray.shape
    output = []
    for family in families:
        pitch = family['density'].get('median_spacing_px')
        samples, rejected = [], {}
        examined = 0
        if pitch is not None and np.isfinite(pitch) and pitch >= 4:
            half = min(pitch * .45, min(h, w) * .12)
            offsets = np.arange(-half, half + .25, .5)
            for track in family['tracks']:
                if not track['accepted_candidate']:
                    continue
                pts = np.asarray(track['points_xy'])
                for i in range(1, len(pts) - 1, max(1, len(pts) // 20)):
                    examined += 1
                    tangent = pts[i + 1] - pts[i - 1]
                    tangent /= max(float(np.linalg.norm(tangent)), 1e-9)
                    normal = np.array([-tangent[1], tangent[0]])
                    xy = pts[i] + offsets[:, None] * normal
                    if np.any(xy[:, 0] < 1) or np.any(xy[:, 0] >= w - 1) or np.any(xy[:, 1] < 1) or np.any(xy[:, 1] >= h - 1):
                        rejected['outside_image'] = rejected.get('outside_image', 0) + 1
                        continue
                    profile = map_coordinates(gray, [xy[:, 1], xy[:, 0]], order=1, mode='nearest')
                    result, reason = profile_width(profile, offsets)
                    if reason is None and result['width_px'] > pitch * .8:
                        reason = 'width_exceeds_pitch_constraint'
                    if reason:
                        rejected[reason] = rejected.get(reason, 0) + 1
                        continue
                    edges = [list(pts[i] + e * normal) for e in result['edge_offsets_px']]
                    samples.append(dict(track_id=track['id'], center_xy=pts[i].tolist(), edges_xy=edges,
                                        **result, retained=True))
        values = np.array([s['width_px'] for s in samples])
        if len(values):
            med = float(np.median(values))
            mad = float(np.median(abs(values - med)))
            keep = abs(values - med) <= max(1.5, 3 * 1.4826 * mad)
            for sample, use in zip(samples, keep):
                sample['retained'] = bool(use)
            values = values[keep]
        tracks = len({s['track_id'] for s in samples if s['retained']})
        reasons = []
        if len(values) < cfg.widths_min_samples or tracks < cfg.widths_min_tracks:
            reasons.append('insufficient_valid_profiles_or_tracks')
        cv = float(np.std(values) / np.mean(values)) if len(values) else None
        if cv is not None and cv > cfg.widths_max_cv:
            reasons.append('width_distribution_unstable')
        if not registration_ok:
            reasons.append('paired_registration_not_verified')
        if family['status'] != 'INTERNAL_CONSISTENT_CANDIDATE':
            reasons.append('centerline_family_low_confidence')
        percentiles = np.percentile(values, [10, 50, 90]).tolist() if len(values) else None
        output.append(dict(family=family['id'], identity=family['identity'],
                           status='PASS' if not reasons else 'LOW_CONFIDENCE' if len(values) else 'UNAVAILABLE',
                           reasons=reasons, definition='distance between a supported pair of normal-profile gradient edges',
                           p10_p50_p90_px=percentiles,
                           p10_p50_p90_mm=[v * mm_per_px for v in percentiles] if percentiles and mm_per_px else None,
                           profiles_examined=examined, valid_profiles=len(values), valid_tracks=tracks,
                           width_cv=cv, rejection_counts=rejected, samples=samples,
                           physical_accuracy='NOT_EVALUATED'))
    return output


def density_summary(families, calibration):
    items = {}
    for family in families:
        d = family['density']
        item = dict(family=family['id'], identity=family['identity'], status=family['status'],
                    count_per_px=d.get('count_density_per_px'), spacing_per_px=d.get('spacing_density_per_px'),
                    count_per_cm=d.get('count_density_per_cm'), spacing_per_cm=d.get('spacing_density_per_cm'),
                    path_relative_disagreement=d.get('path_relative_disagreement'),
                    reasons=family['reasons'], physical_accuracy='NOT_EVALUATED')
        candidate_scale = calibration['candidate_mm_per_px']
        item['candidate_count_per_cm'] = item['count_per_px'] * 10 / candidate_scale if item['count_per_px'] and candidate_scale else None
        item['candidate_spacing_per_cm'] = item['spacing_per_px'] * 10 / candidate_scale if item['spacing_per_px'] and candidate_scale else None
        items[family['identity'] if family['identity'] != 'unassigned' else family['id']] = item
    a, b = items.get('warp_candidate'), items.get('weft_candidate')
    ratios = {}
    for key in ['count', 'spacing']:
        ratios['candidate_ratio_' + key] = a[key + '_per_px'] / b[key + '_per_px'] if a and b and a[key + '_per_px'] and b[key + '_per_px'] else None
        ratios['ratio_' + key] = ratios['candidate_ratio_' + key] if a and b and all(f['status'] == 'INTERNAL_CONSISTENT_CANDIDATE' for f in families) else None
    return dict(families=items, calibration_status=calibration['status'], **ratios,
                dependency='Both density paths use the same detected centers; agreement is not independent truth')
