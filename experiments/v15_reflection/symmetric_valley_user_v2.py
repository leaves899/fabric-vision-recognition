"""VERBATIM user-supplied V2 algorithm; tested but NOT a validated physical yarn detector.

Risk: accepted=True refers only to a strong symmetric optical valley, not true yarn.
Risk: peak/median `confidence` is not a calibrated probability and may overflow.
Do not wire this directly to the main product or V5.
"""
import cv2
import numpy as np


def detect_true_yarn_directions_v2(
    img_bgr, shoulder_dist_list=(2.0, 3.2), symmetry_alpha=2.0
):
  """V2: 基于【法向双肩同高对称算子 + 谷底零梯度门控 + 切向共线游程】的真实纱向检测

  彻底抛弃激进的白点膨胀掩码，正反面通用，自动剔除暗色浮点边缘。

  返回:
      dict: {
          'accepted': bool,            # 是否通过真实纱缝置信度检验 (可拒判纯浮点负例)
          'warp_or_dom_deg': float,    # 显性主纱线方向 (正面通常为经纱, 反面通常为纬纱, 0~180°)
          'ortho_yarn_deg': float,     # 正交另一组纱线方向 (0~180°)
          'pattern_deg': float,        # 宏观编织花纹/斜纹方向 (0~180°)
          'valid_pixel_ratio': float,  # 参与候选评估的有效像素比例
          'confidence': float,         # 方向峰值显著度置信度
          'sym_seam_map': np.ndarray   # 可视化用的对称暗缝响应图
      }
  """
  # 1. 严格中心对称偶数尺寸裁剪 + 圆形各向同性窗口 (保证100%四向90°旋转一致)
  h, w = img_bgr.shape[:2]
  roi_size = (min(h, w, 600) // 2) * 2
  y0, x0 = (h - roi_size) // 2, (w - roi_size) // 2
  roi = img_bgr[y0 : y0 + roi_size, x0 : x0 + roi_size]

  gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY).astype(np.float32)

  # 构建严格旋转对称的圆形掩码 (消除正方形四角对斜线长度的偏置)
  yy, xx = np.mgrid[0:roi_size, 0:roi_size].astype(np.float32)
  center = (roi_size - 1) / 2.0
  radius = roi_size * 0.46
  dist_from_center = np.hypot(xx - center, yy - center)
  circular_mask = dist_from_center <= radius

  # ---------------------------------------------------------
  # 模块 A: 提取宏观编织花纹方向 (参数10)
  # ---------------------------------------------------------
  gx_mac = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=5)
  gy_mac = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=5)
  Jxx = cv2.GaussianBlur(gx_mac * gx_mac, (25, 25), 5.0)
  Jyy = cv2.GaussianBlur(gy_mac * gy_mac, (25, 25), 5.0)
  Jxy = cv2.GaussianBlur(gx_mac * gy_mac, (25, 25), 5.0)
  # 结构张量最大特征值对应梯度方向，+pi/2 为条纹切线方向
  pattern_rad = 0.5 * np.arctan2(
      2.0 * np.mean(Jxy[circular_mask]), np.mean((Jxx - Jyy)[circular_mask])
  ) + (np.pi / 2.0)
  pattern_deg = float(np.degrees(pattern_rad) % 180.0)

  # ---------------------------------------------------------
  # 模块 B: 原始灰度图微尺度 Hessian 暗谷法线与切线计算 (无半波倒转, 零90°偏差)
  # ---------------------------------------------------------
  # 轻微平滑保留 1.5~4px 纱缝，同时提取一阶与二阶导数
  smooth = cv2.GaussianBlur(gray, (5, 5), 1.1)

  Ix = cv2.Sobel(smooth, cv2.CV_32F, 1, 0, ksize=3) / 8.0
  Iy = cv2.Sobel(smooth, cv2.CV_32F, 0, 1, ksize=3) / 8.0
  Ixx = cv2.Sobel(smooth, cv2.CV_32F, 2, 0, ksize=3) / 4.0
  Iyy = cv2.Sobel(smooth, cv2.CV_32F, 0, 2, ksize=3) / 4.0
  Ixy = cv2.Sobel(smooth, cv2.CV_32F, 1, 1, ksize=3) / 4.0

  # 在原始未倒转图像上，暗谷(Dark Valley)的法线方向具有最大的【正】二阶导数 lambda_n > 0
  trace = Ixx + Iyy
  det_term = np.sqrt((Ixx - Iyy) ** 2 + 4.0 * (Ixy**2) + 1e-12)
  lambda_n = 0.5 * (trace + det_term)  # 垂直于暗缝方向的正曲率 (越大说明谷越深锐)
  lambda_t = 0.5 * (trace - det_term)  # 沿着暗缝切线方向的曲率 (理想直线接近0)

  # 法线角度 phi_n (指向最大正曲率方向) 与 纱缝切线角度 theta_t = phi_n + 90°
  phi_n = 0.5 * np.arctan2(2.0 * Ixy, Ixx - Iyy)
  theta_t = (phi_n + 0.5 * np.pi) % np.pi

  nx = np.cos(phi_n).astype(np.float32)
  ny = np.sin(phi_n).astype(np.float32)
  tx = -ny  # 切线单位向量 x
  ty = nx  # 切线单位向量 y

  # ---------------------------------------------------------
  # 模块 C: 法向双肩同高对称算子 (剔除暗色浮点边缘与纯白点光晕)
  # ---------------------------------------------------------
  # 谷底中心一阶法向梯度 g_n (真暗缝在谷底 g_n ≈ 0，而浮点暗边缘在斜坡上 |g_n| 很大)
  g_n = np.abs(Ix * nx + Iy * ny)

  sym_seam_map = np.zeros_like(gray)
  for d in shoulder_dist_list:
    # 沿法线方向在 ±d 处进行双线性插值采样左右双肩灰度 I_+ 和 I_-
    I_plus = cv2.remap(
        smooth, xx + d * nx, yy + d * ny, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT
    )
    I_minus = cv2.remap(
        smooth, xx - d * nx, yy - d * ny, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT
    )

    delta_plus = I_plus - smooth
    delta_minus = I_minus - smooth

    # 条件1: 左右双肩必须同时高于谷底 (min_rise > 0)
    min_rise = np.minimum(delta_plus, delta_minus)
    both_higher = min_rise > 0.0

    # 条件2: 双肩高度对称性 (若一侧是白浮点、一侧是蓝纱，|delta_+ - delta_-| 极大，权重直接归0)
    shoulder_sum = delta_plus + delta_minus + 1e-6
    shoulder_diff = np.abs(delta_plus - delta_minus)
    w_sym = np.clip(1.0 - symmetry_alpha * (shoulder_diff / shoulder_sum), 0.0, 1.0)

    # 条件3: 谷底一阶法向梯度门控 (要求极值点位于中心而非陡坡)
    w_bottom = np.exp(-0.5 * (g_n / (0.35 * shoulder_sum + 1e-4)) ** 2)

    # 综合该尺度的对称暗谷响应
    resp_d = np.where(both_higher, min_rise * w_sym * w_bottom, 0.0)
    sym_seam_map = np.maximum(sym_seam_map, resp_d)

  # 乘以正曲率强度，并抑制各向同性圆坑 (要求法向曲率显著大于切向曲率绝对值)
  tubularity = np.clip(1.0 - np.abs(lambda_t) / (lambda_n + 1e-5), 0.0, 1.0)
  sym_seam_map = sym_seam_map * np.maximum(0.0, lambda_n) * tubularity

  # ---------------------------------------------------------
  # 模块 D: 切向共线游程验证 (斩断浮点周围短促弯曲的残余弧线)
  # ---------------------------------------------------------
  # 沿着局部切线方向 ±2.5px 采样，要求前后像素同样具有高对称暗谷响应且角度共线
  step_t = 2.5
  sym_fwd = cv2.remap(
      sym_seam_map, xx + step_t * tx, yy + step_t * ty, cv2.INTER_LINEAR
  )
  sym_bwd = cv2.remap(
      sym_seam_map, xx - step_t * tx, yy - step_t * ty, cv2.INTER_LINEAR
  )

  # 使用倍角余弦 cos(2*theta) 衡量前后切线方向的共线性 (避免 0°/180° 跳变)
  cos2t = np.cos(2.0 * theta_t).astype(np.float32)
  sin2t = np.sin(2.0 * theta_t).astype(np.float32)
  c_fwd = cv2.remap(cos2t, xx + step_t * tx, yy + step_t * ty, cv2.INTER_LINEAR)
  s_fwd = cv2.remap(sin2t, xx + step_t * tx, yy + step_t * ty, cv2.INTER_LINEAR)
  c_bwd = cv2.remap(cos2t, xx - step_t * tx, yy - step_t * ty, cv2.INTER_LINEAR)
  s_bwd = cv2.remap(sin2t, xx - step_t * tx, yy - step_t * ty, cv2.INTER_LINEAR)

  align_fwd = np.clip(cos2t * c_fwd + sin2t * s_fwd, 0.0, 1.0)
  align_bwd = np.clip(cos2t * c_bwd + sin2t * s_bwd, 0.0, 1.0)

  # 几何平均游程增强：孤立圆弧点直接衰减，连续直线暗缝保留
  coherence_map = (
      (sym_seam_map * (sym_fwd + 1e-6) * (sym_bwd + 1e-6)) ** (1.0 / 3.0)
      * (align_fwd**2)
      * (align_bwd**2)
  )
  coherence_map *= circular_mask

  # ---------------------------------------------------------
  # 模块 E: 负例拒判机制与高精度旋转不变方向直方图
  # ---------------------------------------------------------
  active_mask = circular_mask & (sym_seam_map > 1e-3)
  valid_pixel_ratio = float(np.sum(active_mask) / np.sum(circular_mask))

  # 若全图几乎没有对称暗谷 (例如【仅有白浮点的合成负例】)，直接拒判！
  max_coherence = float(np.max(coherence_map))
  if valid_pixel_ratio < 0.015 or max_coherence < 1e-2:
    return {
        'accepted': False,
        'warp_or_dom_deg': None,
        'ortho_yarn_deg': None,
        'pattern_deg': pattern_deg,
        'valid_pixel_ratio': valid_pixel_ratio,
        'confidence': 0.0,
        'sym_seam_map': coherence_map,
    }

  # 使用中心对齐的 720 bins (步长0.25°) 进行连续环形投票，确保90°旋转严格对称
  num_bins = 720
  deg_map = (np.degrees(theta_t) % 180.0).ravel()
  weights = coherence_map.ravel()

  # 将每个像素角度按线性插值分配到相邻两个 bin，彻底消除离散分箱边界跳变
  bin_float = (deg_map / 180.0) * num_bins
  bin_idx0 = np.floor(bin_float).astype(np.int32) % num_bins
  bin_idx1 = (bin_idx0 + 1) % num_bins
  frac = bin_float - np.floor(bin_float)

  hist = np.zeros(num_bins, dtype=np.float64)
  np.add.at(hist, bin_idx0, weights * (1.0 - frac))
  np.add.at(hist, bin_idx1, weights * frac)

  # 环形高斯平滑直方图
  pad = 36
  kernel = np.exp(-0.5 * (np.arange(-pad, pad + 1) / 8.0) ** 2)
  kernel /= np.sum(kernel)
  hist_padded = np.concatenate([hist[-pad:], hist, hist[:pad]])
  hist_smooth = np.convolve(hist_padded, kernel, mode='valid')

  # 计算峰值显著度置信度 (Peak-to-Median Ratio)
  peak_idx = int(np.argmax(hist_smooth))
  peak_val = hist_smooth[peak_idx]
  med_val = float(np.median(hist_smooth) + 1e-9)
  confidence = float(peak_val / med_val)

  if confidence < 1.8:
    return {
        'accepted': False,
        'warp_or_dom_deg': None,
        'ortho_yarn_deg': None,
        'pattern_deg': pattern_deg,
        'valid_pixel_ratio': valid_pixel_ratio,
        'confidence': confidence,
        'sym_seam_map': coherence_map,
    }

  dom_yarn_deg = float((peak_idx * 180.0 / num_bins) % 180.0)
  ortho_yarn_deg = float((dom_yarn_deg + 90.0) % 180.0)

  return {
      'accepted': True,
      'warp_or_dom_deg': dom_yarn_deg,
      'ortho_yarn_deg': ortho_yarn_deg,
      'pattern_deg': pattern_deg,
      'valid_pixel_ratio': valid_pixel_ratio,
      'confidence': confidence,
      'sym_seam_map': coherence_map,
  }

