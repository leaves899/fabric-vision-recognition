from __future__ import annotations
"""Independent safety audit of conflicting yarn-centre hypotheses.

Agreement is not proof of a physical yarn. This audit NEVER chooses the
integer or fractional candidate, shifts a line, or uses ground truth.
A large discrepancy relative to *observed core width* means both proposals
cannot simultaneously be advertised as unambiguous.
"""
import numpy as np


def audit_center_hypotheses(integer_result, fractional_result):
    if integer_result.get("status") != "PASS":
        return {"status": "UNDETERMINED", "reason": "INTEGER_PROPOSAL_UNVERIFIED"}
    if fractional_result.get("status") != "PASS":
        return {"status": "UNDETERMINED", "reason": "FRACTIONAL_PROPOSAL_UNVERIFIED"}
    old = np.asarray(integer_result.get("center_positions_px",[]),float)
    new = np.asarray(fractional_result.get("center_positions_px",[]),float)
    pitch = float(fractional_result.get("pitch_px") or 0)
    width = float(fractional_result.get("apparent_core_width_px") or 0)
    if len(old) < 5 or len(new) < 5 or pitch <= 0 or width <= 0:
        return {"status": "UNDETERMINED", "reason": "INSUFFICIENT_ENTITY_GEOMETRY"}
    # One-to-nearest is only a DIFFERENCE statistic, not a correctness or
    # identity match. A proper physical yarn evaluator has additional duties.
    gaps = np.min(np.abs(new[:,None]-old[None,:]),axis=1)
    q90 = float(np.percentile(gaps,90))
    # A candidate's axis should be stable to within a quarter of its *observed*
    # core width, allowing at least 0.15 of one local yarn spacing for imaging
    # jitter. This is a conservative warning boundary, not a fitted truth rule.
    permissible = max(.25*width, .15*pitch)
    conflicting = bool(q90 > permissible or abs(len(old)-len(new)) > 1)
    return {
        "status": "LOW_CONFIDENCE" if conflicting else "CANDIDATE_ONLY",
        "reason": "INTEGER_FRACTIONAL_CENTRE_CONFLICT" if conflicting
                  else "MULTIPLE_METHOD_AGREEMENT_IS_NOT_ENTITY_PROOF",
        "nearest_displacement_q90_px": round(q90,4),
        "nearest_displacement_q90_fraction_pitch": round(q90/pitch,4),
        "measured_apparent_core_width_px": round(width,4),
        "allowed_displacement_px": round(permissible,4),
        "old_center_count": int(len(old)),
        "fractional_center_count": int(len(new)),
        "scope": "PHYSICAL_CENTRE_PUBLICATION_VETO_ONLY"
    }
