from __future__ import annotations

from .config import EngineConfig, DEFAULT_CONFIG


def confidence_for_direction(
    density: dict,
    centerline: dict,
    config: EngineConfig = DEFAULT_CONFIG,
    periodicity: dict | None = None,
    scale_consistency: dict | None = None,
) -> dict:
    reasons = []
    fatal = []
    diff = float(density["path_diff_pct"])
    cv = float(centerline["spacing_cv"])
    coverage = float(centerline["mean_coverage"])
    n = int(centerline["valid_centerline_count"])

    # V0.6.3：Gate 3 分“预警”和“真正不可发布”。
    # 公开真实图上轻中度双路径差异/间距波动先 LOW_CONFIDENCE，不再直接把数值全部吞掉。
    if diff > config.density_agree_fail_pct:
        reasons.append("DUAL_PATH_DENSITY_SEVERE_CONFLICT"); fatal.append("DUAL_PATH_DENSITY_SEVERE_CONFLICT")
    elif diff > config.density_agree_low_pct:
        reasons.append("DUAL_PATH_DENSITY_CONFLICT")
    elif diff > config.density_agree_pass_pct:
        reasons.append("DUAL_PATH_DENSITY_LOW_AGREEMENT")

    if cv > config.spacing_cv_fail:
        reasons.append("CENTER_SPACING_SEVERELY_UNSTABLE"); fatal.append("CENTER_SPACING_SEVERELY_UNSTABLE")
    elif cv > config.spacing_cv_low:
        reasons.append("CENTER_SPACING_UNSTABLE")
    elif cv > config.spacing_cv_pass:
        reasons.append("CENTER_SPACING_MODERATE_VARIATION")

    if coverage < config.ridge_min_coverage:
        reasons.append("CENTERLINE_CONTINUITY_FAIL"); fatal.append("CENTERLINE_CONTINUITY_FAIL")
    elif coverage < config.ridge_good_coverage:
        reasons.append("CENTERLINE_CONTINUITY_LOW")
    if n < config.good_valid_centerlines:
        reasons.append("CENTERLINE_COUNT_LOW")

    # 周期图只作独立核验；缺少可靠周期峰并不否定中心线测量。
    if periodicity and periodicity.get("agreement") == "AVAILABLE":
        periodicity_diff = float(periodicity.get("spacing_difference_pct", 0.0))
        periodicity_peak = float(periodicity.get("autocorrelation_peak", 0.0))
        if (
            periodicity_diff > config.periodicity_disagreement_low_pct
            and periodicity_peak >= config.periodicity_min_peak_for_conflict
        ):
            reasons.append("PERIODICITY_CENTERLINE_DISAGREEMENT")

    # 多尺度响应在相近中心线质量下给出不同密度，保留主测量值但明确其不稳定性。
    if scale_consistency and scale_consistency.get("status") == "AVAILABLE":
        if bool(scale_consistency.get("disagreement")):
            reasons.append("STEERABLE_SCALE_DENSITY_DISAGREEMENT")

    status = "FAIL" if fatal else ("LOW_CONFIDENCE" if reasons else "PASS")
    return {"status": status, "reasons": reasons}


def overall_confidence(gate2_status: str, orientation: dict, mapping: dict, warp_conf: dict, weft_conf: dict) -> dict:
    reasons = []
    gap = float(orientation["angle_gap_deg"])
    if not (70.0 <= gap <= 110.0):
        reasons.append("A_B_DIRECTION_NOT_NEAR_ORTHOGONAL")
    if mapping.get("mapping_ambiguous"):
        reasons.append("WARP_WEFT_MAPPING_AMBIGUOUS")
    reasons.extend([f"WARP_{x}" for x in warp_conf["reasons"]])
    reasons.extend([f"WEFT_{x}" for x in weft_conf["reasons"]])

    if gate2_status == "FAIL" or warp_conf["status"] == "FAIL" or weft_conf["status"] == "FAIL":
        status = "FAIL"
    elif gate2_status == "LOW_CONFIDENCE" or warp_conf["status"] == "LOW_CONFIDENCE" or weft_conf["status"] == "LOW_CONFIDENCE" or reasons:
        status = "LOW_CONFIDENCE"
    else:
        status = "PASS"
    return {"status": status, "reasons": sorted(set(reasons))}
