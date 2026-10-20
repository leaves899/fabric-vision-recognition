"""Paired directional filtering with competing angle/source/polarity hypotheses.

The old single-image engine remains an unchanged, separately reviewable baseline.
Only its tensor, linking, coordinate and density primitives are reused.
"""
from __future__ import annotations

import cv2
import numpy as np
from scipy.ndimage import gaussian_filter, gaussian_filter1d
from scipy.signal import find_peaks

from .primitives import (
    Config, angular_distance, density_from_tracks, direction_field, grayscale,
    link_ridges, normalize, refine_by_directional_coherence, rotate_frame,
)


def _axes(front_field, back_field, cfg):
    hist = .5 * (np.asarray(front_field['histogram']) + np.asarray(back_field['histogram']))
    indices = find_peaks(np.tile(hist, 3), distance=12)[0]
    indices = indices[(indices >= 180) & (indices < 360)] - 180
    selected = []
    for p in sorted(indices, key=lambda x: -hist[x]):
        if all(angular_distance(p, a['angle_deg']) >= cfg.direction_separation_deg for a in selected):
            score = float(hist[p] / max(np.median(hist), 1e-9))
            mass = float(sum(hist[x] for x in range(180) if angular_distance(p, x) <= 12))
            selected.append(dict(angle_deg=float(p), peak_to_median=score, mass=mass,
                                 sufficient=bool(score >= 1.8 and mass >= .07)))
            if len(selected) == 2:
                break
    selected.sort(key=lambda a: a['angle_deg'])
    return selected, hist


def _responses(normalized, valid, angle, primitive, intensity=None):
    frame, footprint, matrix = rotate_frame(normalized, angle)
    # Check extrema on the underlying intensity: variance normalization can
    # create a dark moat on each side of a single bright fiber.
    intensity_frame = (cv2.warpAffine(intensity, matrix, (frame.shape[1], frame.shape[0]),
                                     flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT_101)
                       if intensity is not None else frame)
    moving_valid = cv2.warpAffine(valid.astype(np.uint8), matrix, (frame.shape[1], frame.shape[0]),
                                  flags=cv2.INTER_NEAREST)
    footprint &= moving_valid
    factor = min(frame.shape) / primitive.reference_size
    sigmas = [max(.9, s * factor) for s in primitive.ridge_scales]
    derivatives, extrema = [], []
    for s in sigmas:
        derivatives.append(-s * s * gaussian_filter(frame, (s, 3 * s), order=(2, 0)))
        gradient = gaussian_filter(intensity_frame, (s, 3 * s), order=(1, 0))
        before, after = np.roll(gradient, 1, axis=0), np.roll(gradient, -1, axis=0)
        extrema.append({'bright': (before > 0) & (after < 0),
                        'dark': (before < 0) & (after > 0)})
    ny = max(3, int(np.ceil(4 * max(sigmas))))
    nx = max(3, int(np.ceil(12 * max(sigmas))))
    safe = cv2.erode(footprint, np.ones((2 * ny + 1, 2 * nx + 1), np.uint8),
                     borderType=cv2.BORDER_CONSTANT, borderValue=0) > 0
    responses = {}
    for polarity, sign in [('bright', 1), ('dark', -1)]:
        # A ridge must be a normal intensity extremum. Curvature alone has
        # opposite-sign side lobes, which otherwise double the detected count.
        raw = np.median([np.maximum(sign * derivative, 0) * support[polarity]
                         for derivative, support in zip(derivatives, extrema)], axis=0)
        values = raw[safe]
        scale = max(float(np.percentile(values, 98)) if len(values) else 0, 1e-6)
        response = np.clip(raw / scale, 0, 2)
        response[~safe] = 0
        responses[polarity] = response
    return responses, safe, sigmas, matrix


def _score(tracks, safe, density):
    kept = [t for t in tracks if t['accepted_candidate']]
    if len(kept) < 2:
        return 0.
    area = max(int(safe.sum()), 1)
    lengths = sum(t['span_px'] * t['observed_coverage'] for t in kept)
    continuity = np.median([min(1., t['span_fraction']) * t['observed_coverage'] for t in kept])
    section_support = density.get('valid_sections', 0) / 7
    cv = density.get('spacing_cv', 2.)
    # This ranks image hypotheses, not physical accuracy or calibrated density.
    return float(.45 * continuity + .25 * section_support + .20 / (1 + cv)
                 + .10 * min(1., lengths / np.sqrt(area) / 20))


def detect_pair(front, back, valid, cfg, mm_per_px=None, warp_angle=None):
    primitive = Config()
    fg = grayscale(front)
    bg = grayscale(back) if back is not None else None
    ff, local = direction_field(fg, primitive)
    bf = direction_field(bg, primitive)[0] if bg is not None else None
    axes, histogram = _axes(ff, bf or ff, cfg)
    info = dict(method="independent peaks of multiscale structure tensor histograms",
                reflection=ff, transmission=bf, joint_histogram=histogram.tolist(), axes=axes,
                input_mode='PAIRED' if bg is not None else 'REFLECTION_ONLY',
                forced_orthogonality=False, physical_accuracy="NOT_EVALUATED")
    families, images = [], {}
    if float(np.std(fg)) < .012 or (bg is not None and float(np.std(bg)) < .012) or len(axes) != 2:
        info['status'] = 'REJECTED'
        return families, info, images, local
    normed = {'reflection': normalize(fg, primitive)}
    if bg is not None:
        normed['transmission'] = normalize(bg, primitive)
    for index, axis in enumerate(axes):
        angle = axis['angle_deg']
        angles = [angle]
        proposals = []
        for name, normalized in normed.items():
            refined, diagnostic = refine_by_directional_coherence(normalized, angle, primitive)
            allowed = angular_distance(refined, angle) <= cfg.projection_max_drift_deg and not diagnostic['boundary_peak']
            proposals.append(dict(source=name, allowed=bool(allowed), **diagnostic))
            if allowed and all(angular_distance(refined, a) >= 3 for a in angles):
                angles.append(refined)
        hypotheses = []
        for candidate_angle in angles:
            all_responses, safes, sigmas, matrices = {}, {}, {}, {}
            for name, normalized in normed.items():
                response, safe, sigma, matrix = _responses(normalized, valid, candidate_angle, primitive,
                                                           fg if name == 'reflection' else bg)
                all_responses[name], safes[name], sigmas[name], matrices[name] = response, safe, sigma, matrix
            sources = {name: response for name, response in all_responses.items()}
            if bg is not None:
                sources['paired'] = {pol: .7 * np.maximum(all_responses['reflection'][pol], all_responses['transmission'][pol])
                                    + .3 * np.minimum(all_responses['reflection'][pol], all_responses['transmission'][pol])
                                     for pol in cfg.response_polarities}
            for source, responses in sources.items():
                reference = source if source != 'paired' else 'reflection'
                safe = safes[reference] if source != 'paired' else safes['reflection'] & safes['transmission']
                sigma, matrix = sigmas[reference], matrices[reference]
                for polarity in cfg.response_polarities:
                    response = responses[polarity].copy()
                    response[~safe] = 0
                    tracks, linking = link_ridges(response, safe, primitive, sigma)
                    inverse = cv2.invertAffineTransform(matrix)
                    for track in tracks:
                        xy = np.asarray(track['points'])[:, :2]
                        track['points_xy'] = (xy @ inverse[:, :2].T + inverse[:, 2]).tolist()
                    density = density_from_tracks(tracks, safe, linking['sample_step_px'], primitive,
                                                   10 / mm_per_px if mm_per_px else None)
                    score = _score(tracks, safe, density)
                    hypotheses.append(dict(source=source, polarity=polarity, angle_deg=float(candidate_angle),
                                           score=score, tracks=tracks, linking=linking, density=density,
                                           matrix=matrix, safe=safe, response=response))
        hypotheses.sort(key=lambda x: -x['score'])
        # Report 5.2 maps transmission centerlines into the reflection image.
        # Reflection/paired responses remain diagnostics; they cannot silently
        # replace the transmission centers used for the report measurements.
        measurement_source = 'transmission' if bg is not None else 'reflection'
        measurement_hypotheses = [h for h in hypotheses if h['source'] == measurement_source]
        best = measurement_hypotheses[0]
        alternatives = [dict(source=h['source'], polarity=h['polarity'], angle_deg=h['angle_deg'],
                             score=h['score'], retained_tracks=sum(t['accepted_candidate'] for t in h['tracks']),
                             density_status=h['density']['status']) for h in hypotheses]
        competing = [h for h in measurement_hypotheses[1:] if h['polarity'] != best['polarity'] or angular_distance(h['angle_deg'], best['angle_deg']) >= 5]
        margin = best['score'] - competing[0]['score'] if competing else None
        reasons = list(best['density']['reasons'])
        if not axis['sufficient']:
            reasons.append('weak_tensor_axis')
        if margin is not None and margin < .05:
            reasons.append('competing_angle_or_polarity_hypothesis')
        if bg is None:
            reasons.append('reflection_only_candidate')
        family = dict(id='AB'[index], identity='unassigned', angle_deg=best['angle_deg'],
                      tensor_angle_deg=angle, source=best['source'], polarity=best['polarity'],
                      tracks=best['tracks'], total_tracks=len(best['tracks']),
                      retained_tracks=sum(t['accepted_candidate'] for t in best['tracks']),
                      linking=best['linking'], source_to_frame=best['matrix'].tolist(),
                      density=best['density'], hypotheses=alternatives, hypothesis_margin=margin,
                      refinement_proposals=proposals, reasons=reasons,
                      status='LOW_CONFIDENCE' if reasons else 'INTERNAL_CONSISTENT_CANDIDATE',
                      physical_accuracy='NOT_EVALUATED')
        families.append(family)
        h, w = fg.shape
        images[family['id']] = cv2.warpAffine(best['response'], cv2.invertAffineTransform(best['matrix']),
                                            (w, h), flags=cv2.INTER_LINEAR)
    if len(families) == 2 and angular_distance(*[f['angle_deg'] for f in families]) < cfg.direction_separation_deg:
        for family in families:
            family['reasons'].append('refined_directions_not_separable')
            family['status'] = 'LOW_CONFIDENCE'
    if warp_angle is not None and len(families) == 2:
        if not np.isfinite(warp_angle):
            raise ValueError('warp_angle must be finite')
        distances = [angular_distance(f['angle_deg'], warp_angle) for f in families]
        order = np.argsort(distances)
        if distances[order[0]] <= 25 and distances[order[1]] - distances[order[0]] >= 15:
            families[int(order[0])]['identity'] = 'warp_candidate'
            families[int(order[1])]['identity'] = 'weft_candidate'
    info['status'] = 'INTERNAL_CONSISTENT_CANDIDATE' if all(f['status'] == 'INTERNAL_CONSISTENT_CANDIDATE' for f in families) else 'LOW_CONFIDENCE'
    return families, info, images, local
