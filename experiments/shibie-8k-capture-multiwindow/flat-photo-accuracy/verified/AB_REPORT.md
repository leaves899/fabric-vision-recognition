# 真实照片颜色参考合成的平铺8K双图：原版V0.6.3 vs 优化算法

**两组均使用上一轮已冻结的原生8000×6000反射/透射照片，无图像旋转；一组平纹、一组3/1斜纹，纱线真实标签只在全部方法推理完成后读取。**
反射外观来自实拍参考U20261013_05.jpg的颜色统计及细粒度噪声；透射为模拟，不能称作实物工位拍照。

统一评分：标定框同一九个520px局部窗口，中心截面上与真实物理纱线的**门限内最大一对一**匹配。
容许差=0.32倍真实纱距。宏平均为九个窗口F1的平均，Micro-F1按所有窗口匹配根数之和计算。
V0.6.3保留原有全图自动方向入口；局部优化法使用工位0°对齐已知方向，因此不应声称自动方向精度提升。

## 同区域纱线中心正确率

| 样本 | 经/纬 | 原版V0.6.3 | 原整数局部 | 浮点局部 | 7截线共同相位 | 逐根局部追踪 |
|---|---|---:|---:|---:|---:|---:|
| plain_photo_flat | 经 | 0.8739 | 0.9645 | 0.9645 | 0.9825 | 0.9645 |
| plain_photo_flat | 纬 | 0.0000 | 0.9466 | 0.9543 | 0.9615 | 0.9543 |
| twill31_photo_flat | 经 | 0.8853 | 0.9645 | 0.9645 | 0.9825 | 0.9645 |
| twill31_photo_flat | 纬 | 0.0000 | 0.9543 | 0.9543 | 0.9650 | 0.9543 |

## 自动经纬密度对照

| 样本 | 方向 | 合成物理真值(根/cm) | 原版输出(根/cm) | 原版相对误差 | 优化浮点候选(根/cm) | 优化候选相对误差 |
|---|---|---:|---:|---:|---:|---:|
| plain_photo_flat | warp | 30.00 | 30.521 | 1.737% | 30.075 | 0.25% |
| plain_photo_flat | weft | 25.00 | 24.483 | 2.068% | 25.118 | 0.472% |
| twill31_photo_flat | warp | 30.00 | 30.489 | 1.63% | 30.075 | 0.25% |
| twill31_photo_flat | weft | 25.00 | 24.444 | 2.224% | 25.118 | 0.472% |

## 原版全图门禁/能力区分

- **plain_photo_flat**：V0.6.3状态`PASS`；原版全图耗时16.923秒；优化各局部候选总耗时3.31秒。
  - 原版自动方向：{'warp_direction_deg': 89.484, 'weft_direction_deg': 0.39}
  - 原版组织诊断（未做规范归类准确率验证）：{"status": "SEPARATE_RESULTS", "direction": null, "angle_deg": null, "direction_status": "FAIL", "angle_status": "FAIL", "direction_reasons": ["TWILL_BAND_HOUGH_SEGMENTS_INSUFFICIENT"], "angle_reasons": ["TWILL_BAND_HOUGH_SEGMENTS_INSUFFICIENT"], "reasons": ["TWILL_BAND_HOUGH_SEGMENTS_INSUFFICIENT"], "diagonal_segment_count": 0, "evidence": [], "band_evidence": [{"image_line_angle_deg": 105.0, "direction_field_coverage": 0.0603, "component_count": 15, "mean_response": 4.9112}], "twill_period_px": null, "interlacing_topology": {"status": "NOT_USED_BY_TWILL", "reasons": []}, "weave_type": null, "weave_status": "NOT_AVAILABLE", "weave_reasons": ["WEAVE_TWILL_SEGMENTS_INSUFFICIENT"], "method": "REFLECTION_GABOR_ORIENTATION__LOCAL_DIRECTION_FIELD__BAND_HOUGH_GEOMETRY"}
- **twill31_photo_flat**：V0.6.3状态`PASS`；原版全图耗时23.052秒；优化各局部候选总耗时5.02秒。
  - 原版自动方向：{'warp_direction_deg': 89.488, 'weft_direction_deg': 0.39}
  - 原版组织诊断（未做规范归类准确率验证）：{"status": "SEPARATE_RESULTS", "direction": null, "angle_deg": null, "direction_status": "FAIL", "angle_status": "FAIL", "direction_reasons": ["TWILL_COHERENT_DIAGONAL_BAND_NOT_FOUND"], "angle_reasons": ["TWILL_COHERENT_DIAGONAL_BAND_NOT_FOUND"], "reasons": ["TWILL_COHERENT_DIAGONAL_BAND_NOT_FOUND"], "diagonal_segment_count": 0, "selected_segment_count": 0, "evidence": [], "band_evidence": [], "twill_period_px": null, "interlacing_topology": {"status": "NOT_USED_BY_TWILL", "reasons": []}, "weave_type": null, "weave_status": "NOT_AVAILABLE", "weave_reasons": ["WEAVE_TWILL_BAND_NOT_FOUND"], "method": "REFLECTION_GABOR_ORIENTATION__LOCAL_DIRECTION_FIELD__BAND_HOUGH_GEOMETRY"}

## 质量控制与结论边界

- 所有覆盖图都使用真实算法计算出来的中心线，并与物理真值画在**同一个中央窗口**；全图9窗口统计同时保留在JSON中。
- 若原版输出FAIL，应视作拒识，不以内部未通过门禁的候选作为业务正确结果。
- 九个窗口来自同一张图，不是九张独立实拍照片；本报告只有两组**合成场景**。
- 原版自动经纬角、组织类型及优化版的纱线中心不能简单加权为系统整体10项正确率。
- 若某方法无候选，其F1记为0而非跳过；只有算法真实输出可被评分。
- 实体追踪身份在遮挡后的正确与否，需要额外使用严格物理ID轨迹评分；本报告的中心线F1不代表同根追踪可靠性。
- 图像真实纱线外观尚不充分，真实相机8000×6000双光工位的泛化精度**未知**。
