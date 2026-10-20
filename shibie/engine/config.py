from dataclasses import dataclass


@dataclass(frozen=True)
class EngineConfig:
    # PoC 范围。所有阈值均为验证期参数，最终应由真实 Golden Dataset 冻结。
    min_image_side: int = 420
    max_mm_per_px: float = 0.015

    # Gate 2
    gate2_blur_warn_laplacian: float = 10.0
    gate2_blur_fail_laplacian: float = 3.0
    gate2_detail_warn_tenengrad: float = 30.0
    gate2_detail_fail_tenengrad: float = 10.0
    gate2_exposure_warn_ratio: float = 0.30
    gate2_exposure_fail_ratio: float = 0.60

    roi_ratio: float = 0.90
    orientation_max_side: int = 1600
    density_max_side: int = 2200

    # Structure Tensor：不再一次锁死 A/B，输出多个方向候选，随后仍由同一路线下游验证。
    tensor_sigma: float = 2.0
    tensor_energy_quantile: float = 0.52
    tensor_min_coherence: float = 0.12
    orientation_candidate_count: int = 8
    orientation_peak_min_distance_deg: int = 9
    orientation_pair_gap_min_deg: float = 70.0
    orientation_pair_gap_max_deg: float = 110.0
    orientation_pair_eval_limit: int = 12
    orientation_orth_score_sigma_deg: float = 9.0

    # 候选方向对多指标评分。总和=1.0；只用于方向选择，不改变最终密度公式。
    pair_weight_orthogonality: float = 0.18
    pair_weight_ridge_count: float = 0.18
    pair_weight_centerline_coverage: float = 0.20
    pair_weight_spacing_stability: float = 0.18
    pair_weight_dual_path: float = 0.18
    pair_weight_tensor_strength: float = 0.05
    pair_weight_balance: float = 0.03

    # Steerable Filter Bank：多尺度 + 小角度方向银行；仍然是同一 Steerable 路线。
    steerable_sigmas: tuple[float, ...] = (2.3, 3.6, 4.3, 5.0, 6.0)
    steerable_offsets_deg: tuple[float, ...] = (-4.0, 0.0, 4.0)
    # 多尺度候选仅在中心线质量接近时才彼此核验。发生分歧时只降低可信度，
    # 不以候选中的较低密度覆盖主路线的测量值。
    steerable_quality_close_margin: float = 0.06
    steerable_density_disagreement_low_pct: float = 20.0
    # 尺度候选裁决：V0.6.3-P1 起把「周期核验间距」作为候选排序的参考项。
    # 只用于在已有候选之间选一个，不直接改写密度值，也不替换 Ridge/Centerline 主链；
    # 关闭该开关即回到 V0.6 的「纯中心线质量排序」行为。
    steerable_periodicity_tiebreak: bool = True
    # 一致性因子 = floor + (1-floor) * min(间距)/max(间距)。
    # floor=0.5 表示完全不一致时仍保留一半权重（只降权，不淘汰候选）。
    steerable_periodicity_tiebreak_floor: float = 0.5
    # 自相关峰低于该值时视为「参考不可用」，不参与裁决。
    steerable_periodicity_tiebreak_min_peak: float = 0.18

    # Ridge Detection + Centerline Linking
    density_min_per_cm: float = 15.0
    density_max_per_cm: float = 100.0
    ridge_row_step: int = 3
    ridge_band_half_height: int = 2
    ridge_min_coverage: float = 0.24
    ridge_good_coverage: float = 0.50
    ridge_max_gap_rows: int = 8
    ridge_max_residual_px: float = 6.0
    ridge_prediction_points: int = 4
    # 抑制同一根纱线边缘/细纹产生的过近重复峰；仍受物理密度范围约束。
    ridge_peak_distance_ratio: float = 0.70
    ridge_seed_merge_ratio: float = 0.50
    # Ridge 种子须有独立归一化灰度剖面支持。仅在候选数量充足时抑制明显弱于同图中位水平的轨迹。
    ridge_track_profile_contrast_floor: float = 0.12
    ridge_track_profile_contrast_relative_floor: float = 0.55
    ridge_track_filter_min_extra: int = 2
    centerline_dedupe_ratio: float = 0.50
    # 相邻候选线间距低于整体中位间距 65% 时，按证据强度压制疑似同纱双线。
    # 该规则只删除已有候选线，不补造/重定位中心线。
    centerline_min_relative_gap: float = 0.65
    ridge_global_smoothing_sigma: float = 1.8
    ridge_strip_smoothing_sigma: float = 1.0
    min_valid_centerlines: int = 5
    good_valid_centerlines: int = 8

    # 双路径密度 / Confidence
    density_agree_pass_pct: float = 8.0
    density_agree_low_pct: float = 18.0
    density_agree_fail_pct: float = 35.0
    spacing_cv_pass: float = 0.20
    spacing_cv_low: float = 0.38
    spacing_cv_fail: float = 0.65
    # 独立灰度周期与中心线中位间距的偏差。仅用于可信度预警，不能改写密度值。
    periodicity_disagreement_low_pct: float = 30.0
    periodicity_min_peak_for_conflict: float = 0.18

    # 表观宽度：只读取透射图中心线，在反射图上沿法向测边缘。
    width_registration_max_side: int = 1200
    width_registration_min_response: float = 0.10
    width_registration_min_improvement: float = 0.02
    width_samples_per_centerline: int = 10
    width_profile_step_px: float = 0.5
    width_min_search_half_px: float = 4.0
    width_max_search_half_px: float = 80.0
    width_min_sample_px: float = 2.0
    # 每侧保留多个局部梯度峰，再由边缘配对和跨 Profile 一致性选取。
    width_edge_candidates_per_side: int = 4
    width_min_spacing_ratio: float = 0.22
    width_tile_half_size_px: int = 32
    width_tile_min_contrast: float = 18.0
    width_tile_good_contrast: float = 55.0
    width_tile_min_laplacian: float = 8.0
    width_tile_good_laplacian: float = 80.0
    width_tile_min_weight: float = 0.25
    width_consistency_weight: float = 0.38
    width_consistency_band_ratio: float = 0.12
    width_consistency_min_band_px: float = 2.0
    width_min_valid_samples: int = 12
    width_min_valid_yarns: int = 3
    width_gate_p10_px: float = 12.0
    width_outlier_mad_scale: float = 3.0

    # Twill / Weave：反射图斜向纹理检测，只读取已确定的经纬方向作几何参考。
    twill_max_side: int = 1400
    twill_canny_low: int = 45
    twill_canny_high: int = 130
    twill_hough_threshold: int = 34
    twill_min_line_length_px: int = 34
    twill_max_line_gap_px: int = 8
    twill_axis_exclusion_deg: float = 12.0
    twill_min_segments: int = 6
    # 同一斜纹候选必须在相邻分析尺度中保持同向，避免把单根纤维纹理误报为斜纹。
    twill_analysis_scales: tuple[float, ...] = (0.75, 1.0)
    twill_scale_angle_tolerance_deg: float = 16.0
    twill_scale_consensus_ratio: float = 0.65
    # 斜纹方向场：反射图多尺度 Gabor + 局部 Structure Tensor，仅用于斜纹后处理。
    twill_gabor_sigmas: tuple[float, ...] = (3.5, 5.5, 8.0)
    twill_gabor_angle_step_deg: int = 5
    twill_gabor_wavelength_px: float = 18.0
    twill_gabor_wavelengths_px: tuple[float, ...] = (12.0, 18.0, 28.0)
    twill_direction_field_sigma: float = 3.0
    twill_direction_field_min_coherence: float = 0.18
    twill_direction_tolerance_deg: float = 13.0
    twill_band_response_quantile: float = 0.78
    twill_band_min_area_ratio: float = 0.0015
    twill_band_min_coverage: float = 0.012
    twill_band_pass_coverage: float = 0.050
    twill_band_close_kernel_px: int = 7
    twill_band_dilate_px: int = 2
    # 至少有若干条 Hough 线段穿过候选带后，才启用候选带内方向支持度。
    twill_band_min_segments: int = 6
    # PASS 不由单个斜向响应决定，还需要法向重复带的显著周期峰。
    twill_period_min_px: int = 8
    # 大于该尺度的相关峰通常来自整块光照/纹理趋势，不能作为斜纹重复证据。
    twill_period_max_px: int = 64
    twill_period_min_peak_ratio: float = 0.18
    # 中心线交织拓扑：仅为斜纹/组织后处理提供证据，不参与密度主路线。
    twill_topology_max_centerlines: int = 9
    twill_topology_min_intersections: int = 16
    twill_topology_probe_ratio: float = 0.32
    # 交织点浮沉对比度低于稳健尺度的一定比例时标记为未知，不强行二值化。
    twill_topology_min_contrast_ratio: float = 0.35
    twill_topology_min_chain_points: int = 4
    twill_topology_min_chain_coverage: float = 0.16
    twill_topology_angle_tolerance_deg: float = 14.0
    # PASS 必须由单一斜向结构主导；较弱的斜线只作为 LOW_CONFIDENCE 候选，
    # 防止平纹/缎纹表面的纤维走向被误报为斜纹。
    twill_pass_dominance: float = 0.80
    twill_low_dominance: float = 0.25
    twill_pass_spread_deg: float = 12.0
    twill_low_spread_deg: float = 22.0


DEFAULT_CONFIG = EngineConfig()
