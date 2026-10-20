# 透射双图的无标注明暗极性拓扑诊断

使用同一输入图的暗区和亮区二值拓扑，寻找是否出现二维贯通的纱线网络。
此指标不含真值纱线坐标、不含组织标签，先单独测试，不允许自动修改正式模型。
对每一张合成图生成正常强度和反相强度两种模式，冻结场景参数。

| 场景 | 子集 | 已知合成极性 | 自动判断 | 暗网得分 | 亮网得分 |
|---|---|---|---|---:|---:|
| plain_neutral | development | dark | bright | 0.000 | 0.997 |
| plain_neutral | development | bright | dark | 0.997 | 0.000 |
| plain_rotated | development | dark | bright | 0.000 | 0.999 |
| plain_rotated | development | bright | dark | 0.999 | 0.000 |
| twill_2_1 | development | dark | bright | 0.000 | 0.998 |
| twill_2_1 | development | bright | dark | 0.998 | 0.000 |
| twill_3_1_decoy | development | dark | bright | 0.005 | 0.978 |
| twill_3_1_decoy | development | bright | dark | 0.978 | 0.005 |
| satin_5_2 | development | dark | bright | 0.000 | 0.997 |
| satin_5_2 | development | bright | dark | 0.997 | 0.000 |
| plain_soft_low_contrast | development | dark | bright | 0.007 | 0.917 |
| plain_soft_low_contrast | development | bright | dark | 0.917 | 0.007 |
| holdout_plain_33deg | holdout | dark | bright | 0.001 | 0.994 |
| holdout_plain_33deg | holdout | bright | dark | 0.994 | 0.001 |
| holdout_twill_3_1_soft | holdout | dark | bright | 0.018 | 0.897 |
| holdout_twill_3_1_soft | holdout | bright | dark | 0.897 | 0.018 |
| holdout_satin_5_2 | holdout | dark | bright | 0.003 | 0.985 |
| holdout_satin_5_2 | holdout | bright | dark | 0.985 | 0.003 |
| REAL_RT_1280 | real_unlabeled | 未知 | dark | 0.500 | 0.029 |

- development: 识别正确=0/12，弃权=0

- holdout: 识别正确=0/6，弃权=0

真实RT样本没有单根纱线实体标签，不宣称真实极性识别正确；如果出现弃权则应维持原版。
如果这项独立证据在合成的明暗反相留出集都不可靠，就不应把自动极性接入主程序。
