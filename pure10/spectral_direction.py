"""Cross-scale Fourier evidence for TWO orthogonal physical-yarn axes.

Low-frequency twill/color repeats must not dominate the decision. No labels or
training parameters are read. Scores are hypotheses, not probabilities.
"""
from __future__ import annotations
import cv2
import numpy as np
from scipy.ndimage import gaussian_filter1d

BANDS = ((.012, .028), (.028, .050), (.050, .080),
         (.080, .120), (.120, .200))
# Fixed physical rationale: suppress slowly varying macro-twill/illumination;
# give visible fiber/edge-scale structure more votes. Camera-scale sensitive!
WEIGHTS = (0., .3, .3, 1.5, 2.)


def estimate_axes(bgr, square_side=600):
    """Return direction modulo 90, two-family joint score and audit evidence.

    Angles refer to image pixel coordinates with y down. A 90-degree image
    rotation swaps fiber families without altering the modulo-90 solution.
    Three disjoint vertical positions provide local repeatability evidence.
    """
    h, w = bgr.shape[:2]
    n = min(square_side, h, w)
    if n < 160:
        raise ValueError("Image too small for cross-scale spectrum")
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    centers = ((h//2, w//2),
               (max(n//2,h//3),w//2),
               (min(h-n//2,2*h//3),w//2))
    frequencies = np.fft.fftshift(np.fft.fftfreq(n))
    fy, fx = frequencies[:, None], frequencies[None, :]
    radii = np.sqrt(fx*fx+fy*fy)
    # Fourier wavevector is normal to the observed line.
    tangents = np.mod(np.degrees(np.arctan2(fy,fx))+90, 180)
    projected_angles = np.broadcast_to(tangents, radii.shape)
    band_masks = [(radii >= lo) & (radii < hi) for lo,hi in BANDS]
    window = np.outer(np.hanning(n), np.hanning(n))
    regional_hist = []
    for cy,cx in centers:
        patch = gray[cy-n//2:cy-n//2+n,cx-n//2:cx-n//2+n].copy()
        if patch.shape != (n,n):
            continue
        patch -= patch.mean()
        patch *= window
        energy = np.abs(np.fft.fftshift(np.fft.fft2(patch)))**2
        histograms = []
        for mask in band_masks:
            hist,_=np.histogram(projected_angles[mask],
                                bins=np.arange(181),weights=energy[mask])
            hist = gaussian_filter1d(hist, 2.5, mode="wrap")
            histograms.append(hist/max(float(hist.max()),1e-8))
        regional_hist.append(np.asarray(histograms))
    if not regional_hist:
        raise ValueError("No valid FFT region")
    bands = np.median(regional_hist, axis=0)
    angular_energy = np.average(bands, axis=0, weights=WEIGHTS)
    pair = np.sqrt(angular_energy[:90]*angular_energy[90:])
    chosen = int(np.argmax(pair))
    best = float(pair[chosen])
    rivals = [float(pair[j]) for j in range(90)
              if min(abs(j-chosen),90-abs(j-chosen)) >= 8]
    margin = best-max(rivals) if rivals else best
    return {"theta_mod_90_deg":chosen,
            "joint_score":round(best,6),
            "ambiguity_margin":round(float(margin),6),
            "family_a_energy":round(float(angular_energy[chosen]),6),
            "family_b_energy":round(float(angular_energy[chosen+90]),6),
            "independent_patches":len(regional_hist),
            "radial_frequency_bands_cyc_per_px":[list(v) for v in BANDS],
            "weights":list(WEIGHTS),
            "not_a_probability":True,
            "strong_single_fiber_evidence":False}
