# 合成物理机织布：纱线一对一标注与光学中心相位诊断

合成的R/T图及物理纱线中心线源自同一套几何实体。标签只在推理后读取，不交给算法。
全程保留已知纱线的持久ID，跨遮挡为同一根纱线。
物理匹配采用中央视野法向投影、一对一匹配、误差<=0.32个纱距，角误差>10°直接F1=0。
合成器设定真实背光下纱线较间隙暗；新光学相位配置需独立验证现实设备的明暗规律，正式配置默认OFF。
6个开发诊断场景 + 3个先冻结种子的合成留出场景。

| 场景 | 数据划分 | 组织标签（仅验收） | baseline Warp/Weft F1 | ACF F1 | 光学相位 F1 |
|---|---|---|---|---|---|
| plain_neutral | development | plain | 1.000/1.000 | 1.000/1.000 | 1.000/1.000 |
| plain_rotated | development | plain | 1.000/0.000 | 1.000/0.000 | 1.000/1.000 |
| twill_2_1 | development | twill_2_1 | 1.000/0.000 | 1.000/0.000 | 1.000/1.000 |
| twill_3_1_decoy | development | twill_3_1 | 1.000/1.000 | 1.000/1.000 | 1.000/1.000 |
| satin_5_2 | development | satin_5_2 | 0.000/0.000 | 0.000/0.000 | 1.000/1.000 |
| plain_soft_low_contrast | development | plain | 0.982/1.000 | 0.982/1.000 | 0.982/1.000 |
| holdout_plain_33deg | holdout | plain | 1.000/0.000 | 1.000/0.000 | 1.000/1.000 |
| holdout_twill_3_1_soft | holdout | twill_3_1 | 1.000/1.000 | 1.000/1.000 | 1.000/1.000 |
| holdout_satin_5_2 | holdout | satin_5_2 | 0.000/1.000 | 0.000/1.000 | 1.000/1.000 |

- development_synthetic / v063_default: 平均两轴中心线F1=0.6652
- development_synthetic / acf_candidate: 平均两轴中心线F1=0.6652
- development_synthetic / calibrated_dark_phase: 平均两轴中心线F1=0.9985
- held_out_synthetic / v063_default: 平均两轴中心线F1=0.6667
- held_out_synthetic / acf_candidate: 平均两轴中心线F1=0.6667
- held_out_synthetic / calibrated_dark_phase: 平均两轴中心线F1=1.0000

该项光学证据只改变候选尺度与极性排序，不使用真实物理纱线位置，也不合成中心线。
半周期位置错位即使计数、间距正确，也被本指标判为识别失败。
真实织物、相机光学、8000×6000原生R/T图与P1/P2/P3实体框验收尚未完成；勿把合成F1当现实精度。
