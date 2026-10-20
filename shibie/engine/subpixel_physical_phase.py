from __future__ import annotations
"""Experimental fractional-pitch physical-centre audit (image inputs only).

This module is deliberately separate from V0.6.3 and the frozen multiwindow
baseline. Neither labels, weave type, simulator metadata nor GT pitch may
enter inference. A periodic intensity peak is not, by itself, a yarn.
"""
import math
import cv2
import numpy as np
from scipy.ndimage import gaussian_filter1d


def _gray_profile(patch, family):
    if family not in ("warp", "weft"):
        raise ValueError("UNKNOWN_FAMILY")
    gray = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY)
    return np.median(gray, axis=0 if family == "warp" else 1).astype(np.float64)


def _continuous_acf(signal, lag):
    """Normalized high-pass lag agreement on continuous (interpolated) x."""
    a = np.asarray(signal, dtype=np.float64)
    sigma = max(12., .07 * len(a))
    a = a - gaussian_filter1d(a, sigma, mode="reflect")
    x = np.arange(len(a), dtype=np.float64)
    cutoff = int(math.ceil(lag + 2))
    if cutoff >= len(a) - 32:
        return 0.
    xs = x[cutoff:-cutoff]
    u = np.interp(xs, x, a)
    v = np.interp(xs + lag, x, a)
    u -= u.mean()
    v -= v.mean()
    denom = float(np.linalg.norm(u) * np.linalg.norm(v))
    return float(np.dot(u, v) / denom) if denom > 1.e-9 else 0.


def refine_pitch_subpixel(r_profile, t_profile, integer_candidate):
    """Local search ONLY near a pitch already proposed by image ACF.

    No division/multiplication hypothesis is invented here. Half/double
    competition remains the responsibility of multiwindow_pitch.
    """
    p = float(integer_candidate)
    if not (7. <= p <= 60.) or not np.isfinite(p):
        return {"status": "UNDETERMINED", "reason": "PITCH_UNUSABLE"}
    offsets = np.arange(-.80, .801, .05)
    trials = []
    for delta in offsets:
        candidate = p + float(delta)
        if candidate <= 6.5:
            continue
        rt = [_continuous_acf(s, candidate) for s in (r_profile, t_profile)]
        # Mean support plus cross-modality support: no intensity polarity prior.
        score = .5 * (rt[0] + rt[1]) + .12 * min(rt)
        trials.append((score, candidate, rt))
    if not trials:
        return {"status": "UNDETERMINED", "reason": "NO_PERIOD_SUPPORT"}
    best = max(trials, key=lambda v: v[0])
    boundary = abs(best[1] - p) >= .79
    return {"status": "CANDIDATE_ONLY", "pitch_px": round(best[1], 4),
            "fractional_offset_px": round(best[1]-p, 4),
            "rt_period_support": [round(float(v), 4) for v in best[2]],
            "joint_period_support": round(float(best[0]), 4),
            "boundary_solution": bool(boundary),
            "reason": "SUBPIXEL_PERIOD_STILL_NOT_ENTITY_PROOF"}


def _fold_fractional(signal, pitch, oversample=4):
    """Phase-align true floating-point periods; never round pitch to an int."""
    a = np.asarray(signal, dtype=np.float64)
    bins = int(math.ceil(pitch * oversample))
    periods = np.arange(1, int((len(a) - pitch) / pitch), dtype=np.float64)
    if len(periods) < 3:
        return None
    phases = np.linspace(0, pitch, bins, endpoint=False, dtype=np.float64)
    xs = phases[:, None] + periods[None, :] * pitch
    values = np.interp(xs.ravel(), np.arange(len(a)), a).reshape(xs.shape)
    fold = np.median(values, axis=1)
    fold = gaussian_filter1d(fold, max(.65, .055 * bins), mode="wrap")
    return phases, fold


def _bilateral_core(profile, index, polarity):
    n = len(profile)
    center = float(profile[index])
    opposite = float(profile[(index + n // 2) % n])
    contrast = (center - opposite) * polarity
    if contrast <= 0:
        return None
    threshold = (center + opposite) / 2.
    widths = []
    for sign in (-1, 1):
        distance = 0
        for k in range(1, n // 2 + 1):
            if (float(profile[(index + sign*k) % n]) - threshold) * polarity <= 0:
                break
            distance = k
        widths.append(distance)
    ratio = float(sum(widths)) / n
    symmetry = min(widths) / max(max(widths), 1)
    return ratio, contrast, symmetry


def _phase_ranking(r_profile, t_profile, pitch):
    a = _fold_fractional(r_profile, pitch)
    b = _fold_fractional(t_profile, pitch)
    if a is None or b is None:
        return []
    phases, fr = a
    _, ft = b
    scales = [max(float(np.percentile(f, 95)-np.percentile(f, 5)), 2.) for f in (fr, ft)]
    ranked = []
    for j, phase in enumerate(phases):
        responses = []
        for f, scale in ((fr, scales[0]), (ft, scales[1])):
            candidates = []
            for sign in (-1, 1):
                c = _bilateral_core(f, j, sign)
                if c is not None:
                    width, contrast, symmetry = c
                    candidates.append((width, contrast / scale, symmetry, sign))
            responses.append(max(candidates, key=lambda x: x[0]*x[1]*(.65+.35*x[2]))
                             if candidates else (0., 0., 0., 0))
        widths = [x[0] for x in responses]
        strengths = [x[1] for x in responses]
        symmetry = [x[2] for x in responses]
        coherence = min(strengths) / max(max(strengths), 1.e-6)
        occupancy = float(np.mean(widths))
        width_support = np.clip((occupancy - .36) / .28, 0., 1.)
        support = float(np.mean(np.minimum(strengths, 1.5)))
        score = (support * (.34 + .66 * width_support)
                 * (.60 + .40 * coherence)
                 * (.68 + .32 * np.mean(symmetry)))
        ranked.append({"phase_px": float(phase), "score": float(score),
                       "width_fraction": round(occupancy, 4),
                       "R_polarity": int(responses[0][3]),
                       "T_polarity": int(responses[1][3]),
                       "RT_support": round(float(coherence), 4),
                       "bilateral_symmetry": round(float(np.mean(symmetry)), 4)})
    return sorted(ranked, key=lambda x: x["score"], reverse=True)


def _phase_distance(a, b, pitch):
    return abs((float(a) - float(b) + pitch / 2.) % pitch - pitch / 2.)


def _positions(size, phase, pitch):
    kmax = int(math.ceil(size / pitch))
    x = float(phase) + pitch * np.arange(-1, kmax + 1, dtype=np.float64)
    return x[(x >= .7 * pitch) & (x < size - .7 * pitch)]


def validate_centers_fractional(Rpatch, Tpatch, family, initial_pitch):
    """Float pitch and phase, explicit half-period competitor and abstention."""
    if Rpatch.shape != Tpatch.shape:
        raise ValueError("RT_SHAPE_MISMATCH")
    if family not in ("warp", "weft"):
        raise ValueError("UNKNOWN_FAMILY")
    rp = _gray_profile(Rpatch, family)
    tp = _gray_profile(Tpatch, family)
    pitch = refine_pitch_subpixel(rp, tp, initial_pitch)
    if pitch["status"] != "CANDIDATE_ONLY":
        return pitch
    p = pitch["pitch_px"]
    ranked = _phase_ranking(rp, tp, p)
    if not ranked:
        return {"status": "UNDETERMINED", "reason": "INSUFFICIENT_PHASE_SAMPLES",
                "subpixel_period": pitch}
    top = ranked[0]
    competitors = [c for c in ranked
                   if abs(_phase_distance(c["phase_px"], top["phase_px"], p) - p/2.) < .16 * p]
    opposite = max(competitors, key=lambda x: x["score"]) if competitors else None
    margin = top["score"] - opposite["score"] if opposite else top["score"]
    center_positions = _positions(len(rp), top["phase_px"], p)
    optical_width_px = float(top["width_fraction"] * p)
    status = "PASS"
    reason = "FLOATING_PERIOD_BILATERAL_PHASE"
    if len(center_positions) < 5 or top["RT_support"] < .24 or margin < .06 or top["width_fraction"] < .50:
        status, reason = "LOW_CONFIDENCE", "PHASE_COMPETITION_OR_EDGE_AMBIGUOUS"
    if optical_width_px < 12:
        status, reason = "LOW_CONFIDENCE", "OPTICAL_CORE_BELOW_12PX_NOT_CERTIFIED_P10"
    if pitch["boundary_solution"]:
        status, reason = "LOW_CONFIDENCE", "PITCH_OPTIMUM_AT_SEARCH_BOUNDARY"
    # Three independent along-yarn strips: estimate local *phase* at fixed pitch.
    # Do not average across contradictory strip phases.
    gray_r = cv2.cvtColor(Rpatch, cv2.COLOR_BGR2GRAY)
    gray_t = cv2.cvtColor(Tpatch, cv2.COLOR_BGR2GRAY)
    along_axis = 0 if family == "warp" else 1
    stripe_offsets = np.array_split(np.arange(Rpatch.shape[along_axis]), 3)
    drifts = []
    for ix in stripe_offsets:
        rr = np.median(np.take(gray_r, ix, axis=along_axis), axis=along_axis)
        tt = np.median(np.take(gray_t, ix, axis=along_axis), axis=along_axis)
        trial = _phase_ranking(rr, tt, p)
        if trial:
            drifts.append(_phase_distance(trial[0]["phase_px"], top["phase_px"], p) / p)
    drift = max(drifts) if drifts else 1.
    if drift > .26:
        status, reason = "LOW_CONFIDENCE", "LONGITUDINAL_PHASE_INCONSISTENT"
    return {"status": status, "reason": reason,
            "pitch_px": p, "phase_px": round(top["phase_px"], 4),
            "center_positions_px": np.round(center_positions, 3).tolist(),
            "apparent_core_width_px": round(optical_width_px, 3),
            "width_fraction": top["width_fraction"],
            "relative_phase_margin": round(float(margin), 4),
            "continuity_phase_drift_fraction": round(float(drift), 4),
            "R_center_polarity": top["R_polarity"],
            "T_center_polarity": top["T_polarity"],
            "alternative_phase_px": round(opposite["phase_px"], 4) if opposite else None,
            "subpixel_period": pitch, "phase_candidates": ranked[:4],
            "limitations": ["LOCAL_CROSS_SECTION_ONLY", "NOT_COMPLETE_PHYSICAL_YARN_TRACKING"]}
