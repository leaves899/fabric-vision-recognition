"""V1.5 isolated trial: 2D FFT candidates checked by spatial ACF projections.

Axes are only UNLABELLED CANDIDATES.  FFT and ACF share the same spectrum
(Wiener-Khinchin), and cannot jointly prove physical yarn correspondence.
numpy + Pillow only; no image- or fabric-specific parameter presets.
"""
from __future__ import annotations

import math
import numpy as np
from PIL import Image, ImageFilter

VERSION = "v15-fft-acf-spatial-v3.0"


def axis_distance(a, b):
    d = abs((float(a) - float(b)) % 90.)
    return min(d, 90. - d)


def _period(profile, lo=5., hi=65.):
    """Return short supported ACF lag, avoiding a strong 2x/3x harmonic."""
    z = np.asarray(profile, np.float64)
    n = len(z)
    if n < 88:
        return None
    t = np.linspace(-1., 1., n)
    z -= np.polyval(np.polyfit(t, z, 1), t)
    if z.std() < .65:
        return None
    z *= np.hanning(n)
    z -= z.mean()
    p = np.abs(np.fft.rfft(z, n=2*n))**2
    ac = np.fft.irfft(p, n=2*n)[:n]
    ac /= max(ac[0], 1.e-10)
    ac *= n/np.maximum(n-np.arange(n), 1)
    upper = min(n//3, int(hi))
    lower = max(5, int(lo))
    if lower+2 >= upper:
        return None
    peaks = [i for i in range(lower, upper)
             if ac[i] > ac[i-1] and ac[i] >= ac[i+1]]
    valid = []
    for lag in peaks:
        if ac[lag] < .11:
            continue
        rep = [float(ac[lag*k]) for k in (2, 3) if lag*k < n//2]
        harmonics = float(np.mean(rep)) if rep else 0.
        valid.append((float(ac[lag])*.74 + max(0., harmonics)*.26,
                      lag, float(ac[lag])))
    if not valid:
        return None
    valid.sort(reverse=True)
    top = valid[0]
    strong = [v for v in valid if v[0] >= .91*top[0] and
              (max(top[1], v[1])/min(top[1], v[1]) < 1.08 or
               abs(max(top[1], v[1])/min(top[1], v[1]) -
                   round(max(top[1], v[1])/min(top[1], v[1]))) < .13)]
    strength, period, acf = min(strong, key=lambda v: v[1]) if strong else top
    weaker_half = any(.7*strength < v[0] < .91*strength and
                      1.85 < period/v[1] < 2.15 for v in valid)
    return {"pitch_px": float(period), "support": float(strength),
            "acf": acf, "octave_ambiguous": weaker_half}


def _projection_score(field, angle):
    """Both perpendicular families must survive five long-direction strips."""
    a = np.clip(field+128., 0, 255).astype(np.uint8)
    rotated = np.asarray(
        Image.fromarray(a, "L").rotate(float(angle),
            resample=Image.Resampling.BILINEAR,
            expand=False, fillcolor=128), np.float32)
    side = int(min(rotated.shape)*.64)
    cy, cx = np.array(rotated.shape)//2
    b = rotated[cy-side//2:cy-side//2+side,
                cx-side//2:cx-side//2+side]
    if min(b.shape) < 110:
        return None
    measures = []
    for horizontal in (True, False):
        estimates, contrasts = [], []
        for j in range(5):
            l, r = int(j*side/5), int((j+1)*side/5)
            profile = (b[:, l:r].mean(axis=1) if horizontal
                       else b[l:r, :].mean(axis=0))
            # ACF of an almost-zero projection can still be near one.
            # Absolute projection energy is a necessary additional gate.
            contrasts.append(float(np.std(profile)/max(np.std(b), 1e-6)))
            estimates.append(_period(profile, 5., min(48., side/6.)))
        good = [p for p in estimates
                if p is not None and not p["octave_ambiguous"]]
        if len(good) < 3 or np.median(contrasts) < .35:
            return None
        pitches = np.array([p["pitch_px"] for p in good])
        med = float(np.median(pitches))
        agreeing = [p for p in good
                    if abs(p["pitch_px"]-med)/med < .14]
        if len(agreeing) < 3:
            return None
        inlier_ratio = len(agreeing)/5.
        support = float(np.median([p["support"] for p in agreeing]))
        cv = float(np.std([p["pitch_px"] for p in agreeing])/max(med, 1.))
        measures.append({"pitch_px": med, "support": support,
                         "inlier_ratio": inlier_ratio, "cv": cv,
                         "strip_agreement": len(agreeing),
                         "contrast_ratio": float(np.median(contrasts))})
    score = float(np.sqrt(max(0., measures[0]["support"]) *
                          max(0., measures[1]["support"])))
    score *= math.sqrt(measures[0]["inlier_ratio"] *
                       measures[1]["inlier_ratio"])
    score *= math.sqrt(measures[0]["contrast_ratio"] *
                       measures[1]["contrast_ratio"])
    return {"score": score, "families": measures}


def _spectrum_candidates(field, top=8):
    """Ring-whitened Fourier power; symmetric dual-axis bin intersection."""
    h, w = field.shape
    a = field*np.outer(np.hanning(h), np.hanning(w))
    p = np.abs(np.fft.fftshift(np.fft.fft2(a)))**2
    fy = np.fft.fftshift(np.fft.fftfreq(h))
    fx = np.fft.fftshift(np.fft.fftfreq(w))
    yy, xx = np.meshgrid(fy, fx, indexing="ij")
    rad = np.hypot(xx, yy)
    mask = (rad >= 1/64) & (rad <= 1/5)
    rings = np.minimum((rad*180).astype(int), 36)
    sums = np.bincount(rings[mask], weights=p[mask], minlength=37)
    counts = np.bincount(rings[mask], minlength=37)
    whiten = np.where(mask,
        np.sqrt(p/np.maximum(sums[rings]/np.maximum(counts[rings], 1), 1)),
        0)
    line_angle = (np.degrees(np.arctan2(yy, xx))+90) % 180
    bins = np.floor(line_angle/2.).astype(int) % 90
    hist = np.bincount(bins[mask], weights=whiten[mask], minlength=90)
    pair = np.sqrt(np.maximum(0., hist[:45]*hist[45:]))
    sm = (np.roll(pair, 1)+2*pair+np.roll(pair, -1))/4
    candidates = []
    for idx in np.argsort(sm)[::-1]:
        angle = (int(idx)+.5)*2.
        if all(axis_distance(angle, old) >= 5. for old in candidates):
            candidates.append(angle)
        if len(candidates) >= top:
            break
    return candidates, float(sm.max()/max(np.median(sm), 1e-9))


def propose_axes(image):
    """Result compatible with orient_v2.propose_axes; may abstain."""
    gray = image.convert("L")
    gray.thumbnail((512,512), Image.Resampling.LANCZOS)
    w, h = gray.size
    if min(w,h) < 200:
        return {"method": VERSION, "status": "ABSTAINED",
                "reason": "LOW_RESOLUTION", "unlabelled_axes_deg": None}
    s = min(w,h)
    tile = gray.crop(((w-s)//2,(h-s)//2,(w+s)//2,(h+s)//2))
    bg = np.asarray(tile.filter(ImageFilter.GaussianBlur(radius=12)),
                    np.float32)
    field = np.asarray(tile, np.float32)-bg
    if field.std() < 3.:
        return {"method": VERSION, "status": "ABSTAINED",
                "reason": "LOW_TEXTURE_CONTRAST", "unlabelled_axes_deg": None}
    candidates, pair_strength = _spectrum_candidates(field)
    diagnostic = {"method": VERSION, "status": "ABSTAINED",
                  "unlabelled_axes_deg": None,
                  "fft_pair_strength": round(pair_strength, 3),
                  "fft_candidates_deg": [round(v, 2) for v in candidates]}
    if pair_strength < 1.1:
        return {**diagnostic, "reason": "NO_ORTHOGONAL_SPECTRAL_PEAKS"}
    ranked = []
    for candidate in candidates:
        support = _projection_score(field, candidate)
        if support is not None:
            ranked.append((support["score"],candidate,support))
    ranked.sort(reverse=True)
    diagnostic["candidate_scores"] = [
        {"angle_deg": round(float(c), 2), "score": round(float(score), 4)}
        for score,c,_ in ranked]
    if not ranked:
        return {**diagnostic,
                "reason": "WEAK_INDEPENDENT_CROSS_FAMILY_PROJECTIONS"}
    best, angle, support = ranked[0]
    if best < .14:
        return {**diagnostic, "reason": "WEAK_SPATIAL_ACF_SUPPORT"}
    if (len(ranked)>1 and ranked[1][0]>.91*best and
            axis_distance(angle, ranked[1][1])>6):
        return {**diagnostic, "reason": "MULTIPLE_EQUIVALENT_AXES"}
    if any(f["inlier_ratio"]<.6 or f["cv"]>.1
           for f in support["families"]):
        return {**diagnostic, "reason": "SPATIAL_PERIOD_INSTABILITY"}
    return {**diagnostic, "status": "PROPOSED_NOT_VALIDATED",
            "reason": None,
            "unlabelled_axes_deg": [round(float(angle), 3),
                                   round(float(angle)+90, 3)],
            "spatial_period_evidence": support}
