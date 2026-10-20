# Fabric Measurement Engine 技术路线冻结说明（V0.6）

本项目后续 Density 主链不得用其他技术替换以下节点：

1. 图片质量 Gate
   - Laplacian
   - Tenengrad
   - 灰度直方图
2. 有效织物 ROI
   - PoC 当前中心 ROI 默认
   - 人工 ROI 框选待前端补齐
3. 几何 + 光照归一化
   - Homography / Perspective Correction：有 Camera Profile/标定参数后启用
   - Local Normalization：已实现
4. Structure Tensor
   - 建立局部方向场
   - 得到 A/B 两组主要纱线方向
5. Steerable Filter Bank
   - 沿 A/B 两方向分别增强
6. Ridge Detection + Centerline Linking
   - 形成 A/B 两组纱线中心线
7. 中心线清洗
   - Continuity Check
   - Outlier Rejection
8. 经纬方向映射
   - 经向提示只做 A/B 身份映射
9. 双路径密度
   - Centerline Count
   - Median Center Spacing
   - mm_per_px_x / mm_per_px_y
10. Confidence
   - PASS
   - LOW_CONFIDENCE
   - FAIL

## 开发约束

- 允许调整：参数、阈值、尺度、链接策略、清洗规则、工程性能实现。
- 不允许替换：Structure Tensor、Steerable Filter Bank、Ridge Detection + Centerline Linking、双路径密度这些主链节点。
- FFT / Autocorrelation / Projection 等技术不得替代主链输出。若后续用于调试，只能作为 Evidence/诊断，不参与正式密度结果。
- 当主链结果不可靠时，必须 LOW_CONFIDENCE / FAIL，不能切换到另一套算法偷偷给结果。
