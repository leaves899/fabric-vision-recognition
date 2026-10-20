from __future__ import annotations

import cv2
import numpy as np

from .config import DEFAULT_CONFIG
from .gate2 import gate2
from .normalization import normalize_transmission
from .orientation import structure_tensor_directions, map_warp_weft, angular_distance
from .steerable import steerable_filter_bank, assess_scale_consistency
from .ridge import ridge_detection_and_centerline_linking
from .centerline import clean_centerlines
from .density import dual_path_density
from .confidence import confidence_for_direction, overall_confidence
from .periodicity import estimate_normal_periodicity, compare_periodicity_to_centerlines
from .texture import classify_surface_texture
from .width import measure_apparent_widths, map_centerlines_to_reflection
from .yarn_advisory import advise_yarn_counts
from .twill import analyze_twill
from .gate3 import summarize_gate3
from .evidence import generate_evidence


def decode_image(data: bytes) -> np.ndarray:
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("IMAGE_DECODE_FAILED")
    return img


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _threshold_score(value: float, good: float, low: float, fail: float, lower_is_better: bool = True) -> float:
    """把不同量纲的质量指标映射到 0~1，避免某个大数值指标支配候选方向评分。"""
    value = float(value)
    good, low, fail = float(good), float(low), float(fail)
    if lower_is_better:
        if value <= good:
            return 1.0
        if value <= low:
            return 1.0 - 0.35 * (value - good) / max(low - good, 1e-9)
        if value <= fail:
            return 0.65 - 0.65 * (value - low) / max(fail - low, 1e-9)
        return 0.0
    if value >= good:
        return 1.0
    if value >= low:
        return 0.65 + 0.35 * (value - low) / max(good - low, 1e-9)
    if value > 0:
        return 0.65 * value / max(low, 1e-9)
    return 0.0


def _direction_quality_components(run: dict) -> dict:
    """单方向质量拆解。

    这些分数只用于 Structure Tensor 候选方向的下游反验，不改变最终密度公式。
    """
    c = run["centerline"]
    d = run["density"]
    n = float(c["valid_centerline_count"])
    coverage = float(c["mean_coverage"])
    cv = float(c["spacing_cv"])
    diff = float(d["path_diff_pct"])

    ridge_count_score = _clip01(n / max(float(DEFAULT_CONFIG.good_valid_centerlines), 1.0))
    coverage_score = _threshold_score(
        coverage,
        DEFAULT_CONFIG.ridge_good_coverage,
        DEFAULT_CONFIG.ridge_min_coverage,
        0.0,
        lower_is_better=False,
    )
    spacing_score = _threshold_score(
        cv,
        DEFAULT_CONFIG.spacing_cv_pass,
        DEFAULT_CONFIG.spacing_cv_low,
        DEFAULT_CONFIG.spacing_cv_fail,
        lower_is_better=True,
    )
    dual_path_score = _threshold_score(
        diff,
        DEFAULT_CONFIG.density_agree_pass_pct,
        DEFAULT_CONFIG.density_agree_low_pct,
        DEFAULT_CONFIG.density_agree_fail_pct,
        lower_is_better=True,
    )

    return {
        "ridge_count": ridge_count_score,
        "coverage": coverage_score,
        "spacing_stability": spacing_score,
        "dual_path_agreement": dual_path_score,
    }


def _direction_quality(run: dict) -> float:
    c = _direction_quality_components(run)
    # 用于同一方向内挑选 Steerable 的尺度/极性，避免只看单一指标。
    return (
        0.28 * c["ridge_count"]
        + 0.28 * c["coverage"]
        + 0.22 * c["spacing_stability"]
        + 0.22 * c["dual_path_agreement"]
    )


def _periodicity_agreement(run: dict) -> float:
    """自相关间距与中心线间距的一致性因子，用于尺度候选裁决。

    周期核验只回答「这张图的重复周期是多大」，不提供密度值本身；
    因此它只能参与候选之间谁优先，不能反过来改写被选中候选的密度。
    """
    if not DEFAULT_CONFIG.steerable_periodicity_tiebreak:
        return 1.0
    per = run.get("periodicity") or {}
    per_px = per.get("spacing_px")
    peak = per.get("autocorrelation_peak")
    cl_px = (run.get("centerline") or {}).get("median_center_spacing_px")
    try:
        per_px = float(per_px)
        cl_px = float(cl_px)
    except (TypeError, ValueError):
        return 1.0
    if per_px <= 0.0 or cl_px <= 0.0:
        return 1.0
    if peak is not None and float(peak) < float(DEFAULT_CONFIG.steerable_periodicity_tiebreak_min_peak):
        return 1.0
    agree = min(cl_px, per_px) / max(cl_px, per_px)
    floor = float(DEFAULT_CONFIG.steerable_periodicity_tiebreak_floor)
    return floor + (1.0 - floor) * agree


def _run_direction(normalized: np.ndarray, direction_deg: float, mm_x_working: float, mm_y_working: float) -> dict:
    steer = steerable_filter_bank(normalized, direction_deg, DEFAULT_CONFIG)
    attempts = []
    last_error = None
    response_items = list(steer["responses"].items())
    for response_key, response in response_items:
        meta = steer.get("response_meta", {}).get(response_key, {})
        polarity = meta.get("polarity", response_key)
        sigma_used = float(meta.get("sigma", 0.0))
        try:
            ridge = ridge_detection_and_centerline_linking(
                response, direction_deg, mm_x_working, mm_y_working, DEFAULT_CONFIG,
                validation_image=normalized,
            )
            periodicity_raw = estimate_normal_periodicity(
                ridge["aligned_validation"],
                ridge["min_spacing_px_from_physical_range"],
                ridge["max_spacing_px_from_physical_range"],
                DEFAULT_CONFIG,
            )
            clean = clean_centerlines(
                ridge["raw_tracks"], ridge["sampled_rows"], ridge["min_spacing_px_from_physical_range"],
                DEFAULT_CONFIG,
            )
            density = dual_path_density(clean, int(ridge["aligned_response"].shape[1]), float(ridge["working_mm_per_px_normal"]), DEFAULT_CONFIG)
            periodicity = compare_periodicity_to_centerlines(
                periodicity_raw,
                clean["median_center_spacing_px"],
            )
            base_conf = confidence_for_direction(density, clean, DEFAULT_CONFIG)
            conf = confidence_for_direction(density, clean, DEFAULT_CONFIG, periodicity)
            run = {
                "density": density,
                "confidence": conf,
                "centerline": {
                    "valid_centerline_count": clean["valid_centerline_count"],
                    "median_center_spacing_px": round(clean["median_center_spacing_px"], 4),
                    "spacing_cv": round(clean["spacing_cv"], 4),
                    "mean_coverage": round(clean["mean_coverage"], 4),
                    "mean_profile_contrast": round(clean["mean_profile_contrast"], 4),
                    "outlier_gap_count": clean["outlier_gap_count"],
                },
                "ridge": {
                    "raw_track_count": len(ridge["raw_tracks"]),
                    "sampled_rows": ridge["sampled_rows"],
                    "rotation_deg": ridge["rotation_deg"],
                    "x_link_tolerance_px": round(ridge["x_link_tolerance_px"], 3),
                    "track_profile_rejected_count": ridge["track_profile_rejected_count"],
                    "track_profile_contrast_floor": round(ridge["track_profile_contrast_floor"], 4),
                },
                "periodicity": periodicity,
                # 周期核验不参与 confidence 判定；但其间距作为尺度候选裁决的参考项，
                # 见 _periodicity_agreement（只排序，不改写被选中候选的密度）。
                "_base_confidence_status": base_conf["status"],
                "steerable": {
                    "sigmas": steer["sigmas"],
                    "offsets_deg": steer["offsets_deg"],
                    "line_direction_deg": steer["line_direction_deg"],
                    "selected_polarity": polarity,
                    "selected_sigma": sigma_used,
                    "response_key": response_key,
                },
                # Width 阶段只读取这份已通过 Ridge/Cleaning 的中心线证据，不能改写密度主链。
                "_width_seed": {
                    "centerlines": clean["centerlines"],
                    "rotation_deg": ridge["rotation_deg"],
                    "aligned_crop_offset": ridge["aligned_crop_offset"],
                    "normalized_shape": tuple(int(v) for v in normalized.shape[:2]),
                    "line_direction_deg": float(direction_deg),
                    "median_center_spacing_px": float(clean["median_center_spacing_px"]),
                },
            }
            components = _direction_quality_components(run)
            run["quality_components"] = {k: round(float(v), 5) for k, v in components.items()}
            # 当质量接近时仅轻微偏向较大尺度，抑制毛羽/纤维级微纹理。
            base_quality = _direction_quality(run) + min(sigma_used, 6.0) * 0.008
            agreement = _periodicity_agreement(run)
            run["periodicity_agreement"] = round(float(agreement), 5)
            run["candidate_quality_base"] = round(float(base_quality), 5)
            # 尺度质量 × 周期一致性：只改变候选之间的排序，不改写密度主路线的计算方式。
            run["candidate_quality"] = round(float(base_quality) * float(agreement), 5)
            attempts.append(run)
        except ValueError as exc:
            last_error = str(exc)
    if not attempts:
        raise ValueError(last_error or "DIRECTION_RUN_FAILED")
    # 两级裁决：先用原始中心线质量确定领先者，只在「质量接近」的候选之间
    # 让周期一致性做最终裁决，避免参考项推翻一个本来就明显更优的候选。
    attempts.sort(key=lambda r: (r["_base_confidence_status"] != "FAIL", r["candidate_quality_base"]), reverse=True)
    lead = attempts[0]
    grace = float(getattr(DEFAULT_CONFIG, "steerable_quality_close_margin", 0.0))
    close_set = []
    for item in attempts:
        if item["_base_confidence_status"] == "FAIL":
            break
        if float(lead["candidate_quality_base"]) - float(item["candidate_quality_base"]) > grace:
            break
        close_set.append(item)
    if not close_set:
        close_set = [lead]
    close_set.sort(key=lambda r: r["candidate_quality"], reverse=True)
    selected = close_set[0]
    selected["selection_rule"] = (
        "PERIODICITY_TIEBREAK_WITHIN_CLOSE_MARGIN"
        if DEFAULT_CONFIG.steerable_periodicity_tiebreak
        else "CENTERLINE_QUALITY_ONLY"
    )
    selected["close_margin_candidate_count"] = len(close_set)
    scale_consistency = assess_scale_consistency(attempts, selected, DEFAULT_CONFIG)
    selected["confidence"] = confidence_for_direction(
        selected["density"], selected["centerline"], DEFAULT_CONFIG,
        selected["periodicity"], scale_consistency,
    )
    # 记录同方向内各尺度的实际测量结果，作为多尺度选择的可追溯证据。
    selected["steerable"]["scale_candidates"] = [
        {
            "response_key": item["steerable"]["response_key"],
            "sigma": item["steerable"]["selected_sigma"],
            "polarity": item["steerable"]["selected_polarity"],
            "density_per_cm": round(float(item["density"]["density_per_cm"]), 4),
            "candidate_quality": item["candidate_quality"],
            "candidate_quality_base": item.get("candidate_quality_base"),
            "periodicity_agreement": item.get("periodicity_agreement"),
            "periodicity_spacing_px": (item.get("periodicity") or {}).get("spacing_px"),
            "base_status": item["_base_confidence_status"],
            "valid_centerline_count": item["centerline"]["valid_centerline_count"],
            "spacing_cv": item["centerline"]["spacing_cv"],
            "mean_coverage": item["centerline"]["mean_coverage"],
            "path_diff_pct": round(float(item["density"]["path_diff_pct"]), 4),
        }
        for item in attempts
    ]
    selected["steerable"]["scale_consistency"] = scale_consistency
    return selected


def _pair_blend(a: float, b: float) -> float:
    """两方向都必须好：70%看平均水平，30%看短板。"""
    a, b = float(a), float(b)
    return 0.70 * ((a + b) * 0.5) + 0.30 * min(a, b)


def _orthogonality_score(gap_deg: float) -> float:
    # 高斯式正交评分：90°=1，约 ±10°开始明显降权，但不改变 70~110°候选边界。
    sigma = max(float(DEFAULT_CONFIG.orientation_orth_score_sigma_deg), 1e-6)
    return float(np.exp(-0.5 * ((float(gap_deg) - 90.0) / sigma) ** 2))


def _pair_score(a_strength: float, b_strength: float, gap: float, ra: dict, rb: dict) -> tuple[float, dict]:
    ca = _direction_quality_components(ra)
    cb = _direction_quality_components(rb)

    tensor_score = _clip01(np.sqrt(max(float(a_strength), 0.0) * max(float(b_strength), 0.0)))
    orth_score = _orthogonality_score(gap)
    ridge_score = _pair_blend(ca["ridge_count"], cb["ridge_count"])
    coverage_score = _pair_blend(ca["coverage"], cb["coverage"])
    spacing_score = _pair_blend(ca["spacing_stability"], cb["spacing_stability"])
    dual_score = _pair_blend(ca["dual_path_agreement"], cb["dual_path_agreement"])
    balance_score = _clip01(1.0 - abs(float(ra["candidate_quality"]) - float(rb["candidate_quality"])))

    score = (
        DEFAULT_CONFIG.pair_weight_orthogonality * orth_score
        + DEFAULT_CONFIG.pair_weight_ridge_count * ridge_score
        + DEFAULT_CONFIG.pair_weight_centerline_coverage * coverage_score
        + DEFAULT_CONFIG.pair_weight_spacing_stability * spacing_score
        + DEFAULT_CONFIG.pair_weight_dual_path * dual_score
        + DEFAULT_CONFIG.pair_weight_tensor_strength * tensor_score
        + DEFAULT_CONFIG.pair_weight_balance * balance_score
    )
    components = {
        "orthogonality": orth_score,
        "ridge_count": ridge_score,
        "centerline_coverage": coverage_score,
        "spacing_stability": spacing_score,
        "count_spacing_agreement": dual_score,
        "tensor_strength": tensor_score,
        "pair_balance": balance_score,
    }
    return float(score), components


def _choose_direction_pair(normalized: np.ndarray, orient: dict, mm_x_working: float, mm_y_working: float, warp_axis_hint: str):
    candidates = [(float(c["angle_deg"]), float(c.get("strength", 0.0))) for c in orient.get("direction_candidates", [])]
    if len(candidates) < 2:
        candidates = [(float(orient["direction_a_deg"]), 1.0), (float(orient["direction_b_deg"]), 0.8)]

    # Stage A：只用 Structure Tensor 强度 + 正交程度做廉价预筛；不在这里决定最终经纬方向。
    pairs = []
    for i in range(len(candidates)):
        for j in range(i + 1, len(candidates)):
            a, sa = candidates[i]
            b, sb = candidates[j]
            gap = angular_distance(a, b)
            if DEFAULT_CONFIG.orientation_pair_gap_min_deg <= gap <= DEFAULT_CONFIG.orientation_pair_gap_max_deg:
                tensor_prior = _clip01(np.sqrt(max(sa, 0.0) * max(sb, 0.0)))
                orth_prior = _orthogonality_score(gap)
                prior = 0.55 * tensor_prior + 0.45 * orth_prior
                pairs.append((prior, a, sa, b, sb, gap))
    pairs.sort(reverse=True, key=lambda x: x[0])
    pairs = pairs[: DEFAULT_CONFIG.orientation_pair_eval_limit]
    if not pairs:
        raise ValueError("SECOND_DIRECTION_NOT_FOUND")

    # Stage B：同一个方向只跑一次 Steerable→Ridge→Centerline，供多个候选 pair 复用。
    run_cache: dict[float, dict] = {}
    run_errors: dict[float, str] = {}

    def get_run(angle: float) -> dict:
        key = round(float(angle) % 180.0, 4)
        if key in run_cache:
            return run_cache[key]
        if key in run_errors:
            raise ValueError(run_errors[key])
        try:
            run_cache[key] = _run_direction(normalized, float(angle), mm_x_working, mm_y_working)
            return run_cache[key]
        except ValueError as exc:
            run_errors[key] = str(exc)
            raise

    evaluated = []
    errors = []
    for prior, a, sa, b, sb, gap in pairs:
        try:
            ra = get_run(a)
            rb = get_run(b)
            score, comps = _pair_score(sa, sb, gap, ra, rb)
            publishable = ra["_base_confidence_status"] != "FAIL" and rb["_base_confidence_status"] != "FAIL"
            evaluated.append({
                "score": score,
                "publishable": publishable,
                "a": a, "b": b, "gap": gap,
                "a_strength": sa, "b_strength": sb,
                "prior": prior,
                "ra": ra, "rb": rb,
                "components": comps,
            })
        except ValueError as exc:
            errors.append(str(exc))

    if not evaluated:
        raise ValueError(errors[0] if errors else "NO_ORIENTATION_PAIR_SURVIVED_DOWNSTREAM")

    # 优先选择两方向均可发布的 pair；若所有 pair 均失败，仍保留最佳 pair 让 Gate 3 给出真实 FAIL 原因。
    evaluated.sort(key=lambda x: (x["publishable"], x["score"]), reverse=True)
    best = evaluated[0]
    second_score = evaluated[1]["score"] if len(evaluated) > 1 and evaluated[1]["publishable"] == best["publishable"] else None

    a, b, gap = best["a"], best["b"], best["gap"]
    ra, rb = best["ra"], best["rb"]
    mapping = map_warp_weft(a, b, warp_axis_hint)
    if abs(mapping["warp_direction_deg"] - a) < 1e-6:
        warp, weft = ra, rb
    else:
        warp, weft = rb, ra

    leaderboard = []
    for item in evaluated[:5]:
        leaderboard.append({
            "direction_a_deg": round(float(item["a"]), 3),
            "direction_b_deg": round(float(item["b"]), 3),
            "angle_gap_deg": round(float(item["gap"]), 3),
            "pair_score": round(float(item["score"]), 5),
            "publishable": bool(item["publishable"]),
            "score_components": {k: round(float(v), 5) for k, v in item["components"].items()},
        })

    chosen_orient = dict(orient)
    chosen_orient.update({
        "direction_a_deg": round(a, 3),
        "direction_b_deg": round(b, 3),
        "angle_gap_deg": round(gap, 3),
        "pair_selection": "STRUCTURE_TENSOR_TOPN__MULTIMETRIC_DOWNSTREAM_SCORING",
        "pair_quality": round(float(best["score"]), 5),
        "pair_prior_score": round(float(best["prior"]), 5),
        "pair_selection_margin": round(float(best["score"] - second_score), 5) if second_score is not None else None,
        "pair_score_components": {k: round(float(v), 5) for k, v in best["components"].items()},
        "pair_candidates_evaluated": int(len(evaluated)),
        "direction_runs_cached": int(len(run_cache)),
        "pair_leaderboard": leaderboard,
    })
    return chosen_orient, mapping, warp, weft

def run_measurement(
    front_image_bytes: bytes,
    transmission_image_bytes: bytes,
    mm_per_px: float | None = None,
    mm_per_px_x: float | None = None,
    mm_per_px_y: float | None = None,
    warp_axis_hint: str = "vertical",
    evidence_output_dir: str | None = None,
    sample_id: str = "sample",
) -> dict:
    if mm_per_px_x is None:
        mm_per_px_x = mm_per_px
    if mm_per_px_y is None:
        mm_per_px_y = mm_per_px

    front = decode_image(front_image_bytes)
    if not transmission_image_bytes:
        raise ValueError("TRANSMISSION_IMAGE_REQUIRED")
    transmission = decode_image(transmission_image_bytes)

    g2 = gate2(front, transmission, mm_per_px_x, mm_per_px_y, DEFAULT_CONFIG)
    if g2["status"] == "FAIL":
        return {
            "engine_version": "0.6.3",
            "algorithm_profile": "DENIM_ROUTE_V0.6.3_REAL_ROBUST",
            "input_mode": "STANDARD_REFLECTION_TRANSMISSION",
            "status": "FAIL",
            "failure_reasons": g2["reasons"],
            "gate2": g2,
        }

    normalized, norm_meta = normalize_transmission(transmission, DEFAULT_CONFIG)
    scale = float(norm_meta["resize_scale"])
    mm_x_working = float(mm_per_px_x) / scale
    mm_y_working = float(mm_per_px_y) / scale

    try:
        orient0 = structure_tensor_directions(normalized, DEFAULT_CONFIG)
        orient, mapping, warp, weft = _choose_direction_pair(normalized, orient0, mm_x_working, mm_y_working, warp_axis_hint)
    except ValueError as exc:
        return {
            "engine_version": "0.6.3",
            "algorithm_profile": "DENIM_ROUTE_V0.6.3_REAL_ROBUST",
            "input_mode": "STANDARD_REFLECTION_TRANSMISSION",
            "status": "FAIL",
            "failure_reasons": [str(exc)],
            "gate2": g2,
            "normalization": norm_meta,
        }

    overall = overall_confidence(g2["status"], orient, mapping, warp["confidence"], weft["confidence"])
    warp_density = float(warp["density"]["density_per_cm"])
    weft_density = float(weft["density"]["density_per_cm"])
    ratio = warp_density / max(weft_density, 1e-9)

    texture = classify_surface_texture(front)
    twill = analyze_twill(
        front,
        float(warp["_width_seed"]["line_direction_deg"]),
        float(weft["_width_seed"]["line_direction_deg"]),
        DEFAULT_CONFIG,
        transmission=transmission,
        warp_seed=warp["_width_seed"],
        weft_seed=weft["_width_seed"],
        normalization=norm_meta,
    )
    # 宽度是独立验证模块。任何意外的测宽异常都不能回溯影响已完成的密度主链。
    try:
        width = measure_apparent_widths(
            front, transmission, warp["_width_seed"], weft["_width_seed"], norm_meta,
            float(mm_per_px_x), float(mm_per_px_y), DEFAULT_CONFIG,
        )
    except (ValueError, cv2.error, KeyError, TypeError) as exc:
        width = {
            "status": "FAIL",
            "reasons": [f"WIDTH_MEASUREMENT_ERROR:{exc}"],
            "registration": None,
            "warp": None,
            "weft": None,
            "evidence": [],
        }
    publish = overall["status"] != "FAIL"
    yarn_advisory = advise_yarn_counts(warp_density, weft_density, width)
    gate3 = summarize_gate3(g2, overall, width, twill, yarn_advisory)
    centerline_evidence = {"warp": [], "weft": []}
    if isinstance(width.get("registration"), dict) and width["registration"].get("status") == "PASS":
        matrix = np.asarray(width["registration"]["matrix_transmission_to_reflection"], dtype=np.float32)
        for key, seed in (("warp", warp), ("weft", weft)):
            lines = map_centerlines_to_reflection(seed["_width_seed"], norm_meta, matrix)
            centerline_evidence[key] = [np.asarray(line, dtype=np.float32).round(3).tolist() for line in lines]
    result = {
        "engine_version": "0.6.3",
        "algorithm_profile": "DENIM_ROUTE_V0.6.3_REAL_ROBUST",
        "input_mode": "STANDARD_REFLECTION_TRANSMISSION",
        "status": overall["status"],
        "failure_reasons": overall["reasons"],
        "warp_density_per_cm": round(warp_density, 3) if publish else None,
        "weft_density_per_cm": round(weft_density, 3) if publish else None,
        "warp_weft_ratio": round(ratio, 6) if publish else None,
        "surface_texture": texture["label"],
        "surface_texture_confidence": texture["confidence"],
        "twill": twill,
        "apparent_width": width,
        "yarn_advisory": yarn_advisory,
        "gate3": gate3,
        "gate2": g2,
        "normalization": norm_meta,
        "orientation": {**orient, **mapping},
        "centerline_evidence": centerline_evidence,
        "density_debug": {
            "warp": {k: v for k, v in warp.items() if k != "_width_seed"},
            "weft": {k: v for k, v in weft.items() if k != "_width_seed"},
        },
        "input_calibration": {
            "mm_per_px_x": float(mm_per_px_x),
            "mm_per_px_y": float(mm_per_px_y),
            "working_mm_per_px_x": mm_x_working,
            "working_mm_per_px_y": mm_y_working,
        },
        "route": [
            "Gate2", "ROI", "Geometry+LocalNormalization", "StructureTensorCandidates",
            "MultiScaleSteerableFilterBank", "RidgeDetection+PredictiveCenterlineLinking",
            "CenterlineCleaning", "WarpWeftMapping", "CenterlineCount+MedianCenterSpacing", "Confidence",
            "ReflectionTransmissionRegistration", "NormalProfileMultiEdgePair", "PitchConstrainedProfileConsistency", "WidthP10P50P90",
            "ReflectionTwillCannyHoughGeometry",
            "YarnCountAdvisoryReferenceOnly",
        ],
    }
    if evidence_output_dir is not None:
        evidence = generate_evidence(front, result, evidence_output_dir, sample_id)
        result["evidence"] = evidence
        result["gate3"] = summarize_gate3(g2, overall, width, twill, yarn_advisory, evidence)
    return result
