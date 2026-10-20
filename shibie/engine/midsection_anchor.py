from __future__ import annotations
"""Experimental image-only midsection anchor for a yarn-period family.

Global periodicity and centre phase describe different physical claims.
Estimate a new centre anchor around the queried cross-section, conditioned on
the independently observed full-window R/T polarity and bilateral evidence.
If the centre anchor contradicts the full window, abstain; never use GT to move
a fibre centre. A center cross-section is not a full physical yarn ID.
"""
import cv2
import numpy as np
from .subpixel_physical_phase import (
    _phase_ranking, _phase_distance, _positions, _gray_profile,
    validate_centers_fractional)


def validate_midsection_anchor(Rpatch, Tpatch, family, pitch_candidate):
    base = validate_centers_fractional(Rpatch, Tpatch, family, pitch_candidate)
    if base.get("status") != "PASS":
        return {"status": "LOW_CONFIDENCE", "reason": "BASE_PHASE_UNVERIFIED",
                "base": base}
    p = float(base["pitch_px"])
    along = 0 if family == "warp" else 1
    n = int(Rpatch.shape[along])
    # Mid-band spans several warp/weft intersections, not one lucky image row.
    half = min(n//4, max(48, int(round(2.2*p))))
    indices = np.arange(max(0,n//2-half), min(n,n//2+half))
    rg = cv2.cvtColor(Rpatch,cv2.COLOR_BGR2GRAY)
    tg = cv2.cvtColor(Tpatch,cv2.COLOR_BGR2GRAY)
    rp = np.median(np.take(rg, indices, axis=along), axis=along)
    tp = np.median(np.take(tg, indices, axis=along), axis=along)
    choices = _phase_ranking(rp,tp,p)
    if not choices:
        return {"status": "LOW_CONFIDENCE", "reason": "MIDSECTION_EDGE_NOT_MEASURABLE",
                "base": base}
    phase = float(base["phase_px"])
    # Independent local evidence may shift a phase, but may not freely flip a
    # yarn into an adjacent pore / reverse R/T polarities.
    plausible = [q for q in choices
                 if q["R_polarity"]==base["R_center_polarity"]
                 and q["T_polarity"]==base["T_center_polarity"]
                 and _phase_distance(q["phase_px"],phase,p)<=.26*p]
    if not plausible:
        return {"status": "LOW_CONFIDENCE", "reason": "MIDSECTION_POLARITY_OR_PHASE_CONFLICT",
                "base": base}
    best = max(plausible,key=lambda q:q["score"])
    drift = _phase_distance(best["phase_px"],phase,p)
    distant = [q for q in choices
               if abs(_phase_distance(q["phase_px"],best["phase_px"],p)-p/2.) < .15*p]
    antagonist = max(distant,key=lambda q:q["score"]) if distant else None
    margin = best["score"]-(antagonist["score"] if antagonist else 0.)
    positions = _positions(Rpatch.shape[1-along],best["phase_px"],p)
    status = "PASS"
    reason = "MIDSECTION_ANCHORED_WITH_FIXED_POLARITY"
    if (best["RT_support"] < .24 or margin < .06
        or best["width_fraction"] < .50 or best["width_fraction"]*p < 12.
        or len(positions) < 5):
        status,reason="LOW_CONFIDENCE","MIDSECTION_ENTITY_EVIDENCE_INSUFFICIENT"
    return {"status":status,"reason":reason,"pitch_px":p,
            "phase_px":round(best["phase_px"],4),
            "center_positions_px":np.round(positions,3).tolist(),
            "relative_phase_margin":round(float(margin),4),
            "midsection_phase_displacement_px":round(float(drift),4),
            "midsection_band_px":int(len(indices)),
            "R_center_polarity":best["R_polarity"],
            "T_center_polarity":best["T_polarity"],
            "base_phase_px":base["phase_px"],
            "base_pitch_px":base["pitch_px"],
            "limitations":["MIDLINE_PROXY_ONLY","NOT_FULL_YARN_ENTITY_VALIDATION"]}
