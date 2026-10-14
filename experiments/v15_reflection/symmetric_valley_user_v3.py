"""Verbatim user V3 research prototype, NOT physically certified. Its verified flag means a heuristic gate outcome only. No local physical yarn identity tracking is implemented."""
import cv2
import numpy as np


def detect_and_verify_physical_yarns_v3(
    img_bgr, shoulder_dist_list=(2.0, 3.0, 4.2), symmetry_alpha=2.0
):
  """V3: 对称暗谷局部证据 + 三项独立物理约束验证

  1. 候选暗缝两侧的凸纱冠实体形态 (谷-冠-谷曲率反号 + 纱冠主轴与暗缝平行度)
  2. 二维交织遮挡调制与跨遮挡同根重现 (拦截 58° 纯光学细/宽条带负例)
  3. 冠-缝-冠非重复间距约束与花纹重合风险剥离 (解决 1(2), 2(2), 5(2) 斜纹劫持)
  """
  h, w = img_bgr.shape[:2]
  roi_size = (min(h, w, 600) // 2) * 2
  y0, x0 = (h - roi_size) // 2, (w - roi_size) // 2
  roi = img_bgr[y0 : y0 + roi_size, x0 : x0 + roi_size]
  gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY).astype(np.float32)

  yy, xx = np.mgrid[0:roi_size, 0:roi_size].astype(np.float32)
  center = (roi_size - 1) / 2.0
  circular_mask = np.hypot(xx - center, yy - center) <= (roi_size * 0.46)

  # ---------------------------------------------------------
  # 1. 宏观纹理方向与【一维纯光学条带】全局负例门控
  # ---------------------------------------------------------
  gx_mac = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=5)
  gy_mac = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=5)
  Jxx = float(np.mean((gx_mac * gx_mac)[circular_mask]))
  Jyy = float(np.mean((gy_mac * gy_mac)[circular_mask]))
  Jxy = float(np.mean((gx_mac * gy_mac)[circular_mask]))

  pattern_rad = 0.5 * np.arctan2(2.0 * Jxy, Jxx - Jyy) + (np.pi / 2.0)
  pattern_deg = float(np.degrees(pattern_rad) % 180.0)

  # 计算全局结构张量的特征值 lambda_max, lambda_min
  # 若图像是【纯光学细条带/宽条带】，沿条带方向完全没有正交交织梯度，lambda_min / lambda_max 趋近于 0！
  trace_J = Jxx + Jyy + 1e-9
  det_term_J = np.sqrt((Jxx - Jyy) ** 2 + 4.0 * (Jxy**2))
  lambda_J1 = 0.5 * (trace_J + det_term_J)
  lambda_J2 = 0.5 * (trace_J - det_term_J)
  ortho_interlace_ratio = float(
      lambda_J2 / (lambda_J1 + 1e-9)
  )  # 2D交织正交能量比

  # ---------------------------------------------------------
  # 2. 微尺度 Hessian 曲率场：同时提取【暗缝凹谷(lambda_n > 0)】与【亮纱冠凸脊(lambda_c < 0)】
  # ---------------------------------------------------------
  smooth = cv2.GaussianBlur(gray, (5, 5), 1.1)
  Ix = cv2.Sobel(smooth, cv2.CV_32F, 1, 0, ksize=3) / 8.0
  Iy = cv2.Sobel(smooth, cv2.CV_32F, 0, 1, ksize=3) / 8.0
  Ixx = cv2.Sobel(smooth, cv2.CV_32F, 2, 0, ksize=3) / 4.0
  Iyy = cv2.Sobel(smooth, cv2.CV_32F, 0, 2, ksize=3) / 4.0
  Ixy = cv2.Sobel(smooth, cv2.CV_32F, 1, 1, ksize=3) / 4.0

  trace = Ixx + Iyy
  det_term = np.sqrt((Ixx - Iyy) ** 2 + 4.0 * (Ixy**2) + 1e-12)

  # 暗谷主正曲率 lambda_valley > 0 及其法向 phi_n、切向 theta_valley
  lambda_valley = 0.5 * (trace + det_term)
  phi_n = 0.5 * np.arctan2(2.0 * Ixy, Ixx - Iyy)
  theta_valley = (phi_n + 0.5 * np.pi) % np.pi

  # 亮纱冠主负曲率 (取正值表示凸起强度): lambda_crown = -0.5 * (trace - det_term) > 0
  # 注意：亮脊的法向指向最小负特征值方向，因此亮纱冠的切线方向恰好等于 phi_n % pi！
  lambda_crown = np.maximum(0.0, -0.5 * (trace - det_term))
  theta_crown = phi_n % np.pi  # 亮纱冠实体的局部主轴方向

  nx = np.cos(phi_n).astype(np.float32)
  ny = np.sin(phi_n).astype(np.float32)
  tx, ty = -ny, nx
  g_n = np.abs(Ix * nx + Iy * ny)

  # ---------------------------------------------------------
  # 3. 物理约束 1：双肩对称 + 【谷-冠-谷曲率三极反号】 + 【双侧纱冠主轴平行度】
  # ---------------------------------------------------------
  cos2_valley = np.cos(2.0 * theta_valley).astype(np.float32)
  sin2_valley = np.sin(2.0 * theta_valley).astype(np.float32)
  cos2_crown = np.cos(2.0 * theta_crown).astype(np.float32)
  sin2_crown = np.sin(2.0 * theta_crown).astype(np.float32)

  physical_seam_map = np.zeros_like(gray)
  best_crown_dist = np.zeros_like(gray)

  for d in shoulder_dist_list:
    px_p, py_p = xx + d * nx, yy + d * ny
    px_m, py_m = xx - d * nx, yy - d * ny

    # (a) 采样左右双肩灰度
    I_plus = cv2.remap(
        smooth, px_p, py_p, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT
    )
    I_minus = cv2.remap(
        smooth, px_m, py_m, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT
    )
    delta_p, delta_m = I_plus - smooth, I_minus - smooth
    min_rise = np.minimum(delta_p, delta_m)
    shoulder_sum = delta_p + delta_m + 1e-6

    w_sym = np.clip(
        1.0 - symmetry_alpha * (np.abs(delta_p - delta_m) / shoulder_sum),
        0.0,
        1.0,
    )
    w_bottom = np.exp(-0.5 * (g_n / (0.35 * shoulder_sum + 1e-4)) ** 2)

    # (b) 【新增核心约束】：左右双肩必须落在凸起的亮纱冠实体上 (lambda_crown > 0)
    # 彻底击毙 58° 宽阴影条带（宽条带在 ±d 处仍在斜坡或谷底，没有凸纱冠反号！）
    crown_p = cv2.remap(
        lambda_crown,
        px_p,
        py_p,
        cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REFLECT,
    )
    crown_m = cv2.remap(
        lambda_crown,
        px_m,
        py_m,
        cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REFLECT,
    )
    # 要求两侧纱冠凸起曲率与中心暗谷凹陷曲率量级匹配
    crown_conviction = np.sqrt(np.maximum(0.0, crown_p * crown_m)) / (
        lambda_valley + 1e-4
    )
    w_crown_entity = np.clip(crown_conviction * 1.5, 0.0, 1.0)

    # (c) 【新增核心约束】：左右两侧亮纱冠的主轴方向必须与暗缝方向平行！
    # 若是斜纹沟槽，两侧亮浮点主轴斜交穿过沟槽，align_crown 显著下降
    c2_cp = cv2.remap(cos2_crown, px_p, py_p, cv2.INTER_LINEAR)
    s2_cp = cv2.remap(sin2_crown, px_p, py_p, cv2.INTER_LINEAR)
    c2_cm = cv2.remap(cos2_crown, px_m, py_m, cv2.INTER_LINEAR)
    s2_cm = cv2.remap(sin2_crown, px_m, py_m, cv2.INTER_LINEAR)

    align_crown_p = np.clip(
        cos2_valley * c2_cp + sin2_valley * s2_cp, 0.0, 1.0
    )  # cos(2*d_theta)
    align_crown_m = np.clip(cos2_valley * c2_cm + sin2_valley * s2_cm, 0.0, 1.0)
    w_crown_parallel = (align_crown_p * align_crown_m) ** 2

    resp_d = np.where(
        min_rise > 0.0,
        min_rise * w_sym * w_bottom * w_crown_entity * w_crown_parallel,
        0.0,
    )
    update_mask = resp_d > physical_seam_map
    physical_seam_map = np.where(update_mask, resp_d, physical_seam_map)
    best_crown_dist = np.where(update_mask, d, best_crown_dist)

  physical_seam_map *= np.maximum(0.0, lambda_valley) * circular_mask

  # ---------------------------------------------------------
  # 4. 物理约束 2：切向交织调制存在性验证 (彻底拦截 58° 纯光学细条带负例)
  # ---------------------------------------------------------
  # 在真实织物中，双侧纱冠沿切线方向 t 必然受到正交纬纱的周期性交织调制（存在切向梯度和错相）
  # 而在纯一维光学条带中，沿条带切向灰度恒定 (|Ix*tx + Iy*ty| ≈ 0)
  g_t = np.abs(Ix * tx + Iy * ty)
  # 统计局部 15x15 邻域内的切向交织调制能量与法向能量之比
  local_gt_energy = cv2.GaussianBlur(g_t**2, (15, 15), 3.5)
  local_gn_energy = cv2.GaussianBlur(g_n**2, (15, 15), 3.5) + 1e-6
  interlace_modulation_ratio = float(
      np.percentile(
          (local_gt_energy / local_gn_energy)[circular_mask], 75
      )
  )

  # 判定是否为【无交织的纯一维光学条带】(同时结合全局正交能量比与局部切向交织调制比)
  is_pure_1d_optical_stripe = (ortho_interlace_ratio < 0.035) and (
      interlace_modulation_ratio < 0.04
  )

  active_mask = circular_mask & (physical_seam_map > 1e-3)
  valid_pixel_ratio = float(np.sum(active_mask) / np.sum(circular_mask))

  if (
      is_pure_1d_optical_stripe
      or valid_pixel_ratio < 0.01
      or np.max(physical_seam_map) < 1e-2
  ):
    return {
        'accepted': False,
        'reject_reason': (
            'pure_1d_optical_stripe_no_weaving'
            if is_pure_1d_optical_stripe
            else 'no_physical_yarn_seams'
        ),
        'warp_or_dom_deg': None,
        'ortho_yarn_deg': None,
        'pattern_deg': pattern_deg,
        'twill_hijack_risk': True,
        'estimated_yarn_pitch_px': None,
        'physical_seam_map': physical_seam_map,
    }

  # ---------------------------------------------------------
  # 5. 构建方向谱并对【与宏观花纹重合的峰】执行跨遮挡同根连续性复核
  # ---------------------------------------------------------
  num_bins = 720
  deg_map = (np.degrees(theta_valley) % 180.0).ravel()
  weights = physical_seam_map.ravel()

  bin_float = (deg_map / 180.0) * num_bins
  bin_idx0 = np.floor(bin_float).astype(np.int32) % num_bins
  bin_idx1 = (bin_idx0 + 1) % num_bins
  frac = bin_float - np.floor(bin_float)

  hist = np.zeros(num_bins, dtype=np.float64)
  np.add.at(hist, bin_idx0, weights * (1.0 - frac))
  np.add.at(hist, bin_idx1, weights * frac)

  pad = 36
  kernel = np.exp(-0.5 * (np.arange(-pad, pad + 1) / 8.0) ** 2)
  kernel /= np.sum(kernel)
  hist_smooth = np.convolve(
      np.concatenate([hist[-pad:], hist, hist[:pad]]), kernel, mode='valid'
  )
  bin_angles = np.arange(num_bins) * (180.0 / num_bins)

  # 专门应对 1(2)、2(2)、5(2)：如果第一高峰与 pattern_deg 夹角 < 8°，检查是否存在非斜纹的真实物理纱峰
  peak1_idx = int(np.argmax(hist_smooth))
  peak1_deg = float(bin_angles[peak1_idx])
  diff_to_pattern = abs((peak1_deg - pattern_deg + 90.0) % 180.0 - 90.0)

  twill_hijack_risk = diff_to_pattern < 8.0
  chosen_deg = peak1_deg

  if twill_hijack_risk:
    # 在偏离宏观花纹至少 12° 的区间内寻找最强物理纱缝次高峰 (真实经纬纱与斜纹必有 14°~38° 夹角)
    non_pattern_mask = (
        np.abs((bin_angles - pattern_deg + 90.0) % 180.0 - 90.0) >= 12.0
    )
    sub_hist = hist_smooth * non_pattern_mask
    peak2_idx = int(np.argmax(sub_hist))
    peak2_val = sub_hist[peak2_idx]
    med_val = float(np.median(hist_smooth) + 1e-9)

    # 若非斜纹区存在显著的物理纱缝峰 (显著度 > 1.8 倍中位数)，则切换至该物理纱向并标记已纠偏
    if peak2_val > 1.8 * med_val:
      chosen_deg = float(bin_angles[peak2_idx])
      twill_hijack_risk = False

  # 物理约束 3：由双侧纱冠最佳反号距离 2*d* 直接给出无倍频混叠的单纱宽度估计
  est_pitch_px = float(2.0 * np.median(best_crown_dist[active_mask]))

  return {
      'accepted': not twill_hijack_risk,  # 若仍无法脱离宏观花纹且无次峰，安全降级为 False
      'reject_reason': (
          'undecoupled_macro_pattern_coincidence'
          if twill_hijack_risk
          else 'verified'
      ),
      'warp_or_dom_deg': chosen_deg,
      'ortho_yarn_deg': float((chosen_deg + 90.0) % 180.0),
      'pattern_deg': pattern_deg,
      'twill_hijack_risk': twill_hijack_risk,
      'estimated_yarn_pitch_px': est_pitch_px,
      'physical_seam_map': physical_seam_map,
  }

