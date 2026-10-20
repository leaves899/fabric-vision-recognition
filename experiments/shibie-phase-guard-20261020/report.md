# 已知真实纱线身份的合成数据：光学相位纱距保护

六张开发诊断图片+三张预先冻结的合成留出图片。真值从不输入推理。
光学相位仅在与原版无相位筛选结果纱距差异≤15%的候选间产生排序贡献。
真实图像未预先确定亮暗极性；不能把合成暗纱线作为自动规则。

| 场景 | 数据划分 | baseline F1 (两方向均值) | 旧dark F1 | guarded-dark F1 | guarded-bright F1 |
|---|---|---:|---:|---:|---:|
| plain_neutral | development | 1.0000 | 1.0000 | 1.0000 | 0.0000 |
| plain_rotated | development | 0.5000 | 1.0000 | 1.0000 | 0.0000 |
| twill_2_1 | development | 0.5000 | 1.0000 | 1.0000 | 0.0000 |
| twill_3_1_decoy | development | 1.0000 | 1.0000 | 1.0000 | 0.0000 |
| satin_5_2 | development | 0.0000 | 1.0000 | 1.0000 | 0.0000 |
| plain_soft_low_contrast | development | 0.9909 | 0.9909 | 0.9909 | 0.0000 |
| holdout_plain_33deg | holdout | 0.5000 | 1.0000 | 1.0000 | 0.0000 |
| holdout_twill_3_1_soft | holdout | 1.0000 | 1.0000 | 1.0000 | 0.0000 |
| holdout_satin_5_2 | holdout | 0.5000 | 1.0000 | 1.0000 | 0.0000 |

- development/guarded_dark：平均中心线F1=0.9985
- development/guarded_bright：平均中心线F1=0.0000
- holdout/guarded_dark：平均中心线F1=1.0000
- holdout/guarded_bright：平均中心线F1=0.0000

注意：一对一匹配仅按投影线位置，不保证跨遮挡完整轨迹。此分数仅对特定程序化生成分布有效。
