# 真实反射/透射双图：采集条件针对性参数消融

本实验仅使用仓库已存在的真正 R/T 双图，同位置假设基于原文件名和既有配对记录，未取得 Camera Profile。
反射和透射图像尺寸：1280×1280 / 1280×1280。
图像不符合 8000×6000 原生分辨率条件，因此仅是 PoC 失败机制排查，不属于正式采集工位的精度验证。
0.0125mm/px 仅是目标工位名义值，本图没有独立标尺标定，不输出正式根/cm。
红线为推理得到的 warp 候选中心线，青色为 weft 候选中心线；图覆盖在真实透射图上，而非绘制在没有验证配准的反射图上。
ACF 峰仅作为辅助周期，不是单根物理纱线真值。任何看似增加线数的变化仍需视觉检查。

| 参数 | warp中心线 | 纬向中心线 | warp中心间距px | 纬向中心间距px | warp ACFpx | 纬向ACFpx | 状态 |
|---|---:|---:|---:|---:|---:|---:|---|
| default_v063 | 33 | 9 | 27.855 | 109.1606 | 28.0 | None | LOW_CONFIDENCE |
| min_density_10 | 33 | 9 | 27.855 | 109.1606 | 28.0 | 49.0 | LOW_CONFIDENCE |
| acf_strict | 33 | 16 | 27.855 | 52.9786 | 28.0 | 49.0 | LOW_CONFIDENCE |
| ridges_local | 34 | 9 | 27.7928 | 102.2991 | 28.0 | 49.0 | LOW_CONFIDENCE |
| acf_plus_ridges | 21 | 23 | 41.7612 | 40.9401 | 41.0 | 51.0 | LOW_CONFIDENCE |

## 检视入口
在 GitHub Actions 的图像 artifact 中查看 `original_transmission.png`、`original_reflection.png` 和 `overlays/*.png`，对比每条线是否为实体纱线。
目前不存在通过认证的 50MP 原始 R/T Golden Dataset，禁止以本试验的线数与 PASS 状态宣称量产准确率。
仅当留出布料的中心线/截线真值检查没有回归时，才可以冻结和合入新参数。
