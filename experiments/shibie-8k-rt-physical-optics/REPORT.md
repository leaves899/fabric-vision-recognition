# 原生8K物理R/T：首轮研发实测报告

**结论：已实际完成生成、图像打开审阅和冻结算法A/B；物理外观验收未通过，斜纹纬向识别仍失败。保持独立分支，不合并main。**

## 运行与边界

- 源基线：f61004024ed95bc850b639141928f889a9534352；新渲染与A/B成功CI源码：4e0c76fcfc8e7eaecdc2a01963aa5dcc2897c93d。
- 成功CI（五组）：https://github.com/leaves899/fabric-vision-recognition/actions/runs/39529215709 。Artifacts含全部原生8000×6000 R/T、完整物理真值、600×600 PNG、可见归属、逐窗口覆盖、预测冻结文件和时间RSS日志；有效期至2026-11-20。
- 首次失败CI：https://github.com/leaves899/fabric-vision-recognition/actions/runs/39528932881 （真值导出整数类型错误，已修复并保留）；修复后首次成功：https://github.com/leaves899/fabric-vision-recognition/actions/runs/39529030495 。最终成功CI补齐全局唯一ID。
- 75项回归执行成功，其中3项是冻结旧生成器的expectedFailure，不等于旧模型满足物理要求。
- 全部场景0°，无透视旋转；FOV100×75mm，0.0125mm/px，内部50×50mm框。三组开发场景与两组不同材料/种子留出在运行前固定；留出已消耗。
- 推理只使用R/T和公开工位条件；预测在读取真值前写入frozen_predictions_before_GT.json；组织和密度真值不进入推理。V0.6.3源码及旧合成器保留原样。
- 所有结果都是模拟图的局部单截面中心指标，不是实拍正确率，也不是跨遮挡同ID连续性正确率。组织分类的优化模块未实现。
- 原版为自动方向入口，优化版采用已知0°工位方向；方向自动推理不能据此比较。所有原版状态均为LOW_CONFIDENCE，表中为带状态的诊断输出。FAIL/EXCEPTION不计内部候选为有效预测。

## M1旧模型反证与新模型

旧模型同几何/同种子、关闭噪声与额外纹理，仅改变plain/3/1，R平均绝对差21.277，T差0、变化像素0；交叉区T标准差0.496。原始统计、分区直方图与失败裁剪见M1。
新模型使用连续椭圆纱线、纵向浮沉、接触防穿透、表面法线、漫反射/镜面与局部高度阴影；T由纤维弦长、起伏光程、吸收和邻域散射近似生成。两模态共享解析坐标；没有极性翻转和照片纹理粘贴。
同几何plain/3/1的新R平均绝对差41.950、新T为2.685（开发材料）；T差异小由吸收顺序不变性解释，不要求人为增强组织对比。

## M3视觉审阅

详见VISUAL_REVIEW.md。已打开五组R/T全图预览、原生600×600对应裁剪、开发图的中心与可见ID叠图，以及最差检测覆盖图。长浮、上下遮挡与实体位置可解释；但表面仍像光滑编织带，纤维随机性和离散毛羽不足。真实照片来源为实际解包的《高质量照片.rar》，5张；没有同区域实测T，不能声称真实T已标定。

## M4同图A/B

下表为九窗口F1宏平均，匹配使用0.32真实纱距门限内最大一对一；缺失候选计0。优化为预先固定的SHARED_SEVEN，不按样本挑选最佳算法。

| 场景 | 原版经F1 | 优化经F1 | 原版纬F1 | 优化纬F1 | 优化纬拒识窗口 |
|---|---:|---:|---:|---:|---:|
| plain_dev | 0.3312 | 0.9883 | 0.3630 | 0.9650 | 0/9 |
| plain_material_holdout | 0.3437 | 0.9825 | 0.0000 | 0.9579 | 0/9 |
| twill21_dev | 0.3963 | 0.9825 | 0.4000 | 0.5345 | 4/9 |
| twill31_dev | 0.4056 | 0.9825 | 0.0000 | 0.1042 | 8/9 |
| twill31_material_holdout | 0.3741 | 0.9825 | 0.0000 | 0.2083 | 7/9 |

### 密度与运行资源

密度列的优化方法固定为FLOAT_LOCAL；与上表七截线中心F1分开，不能拼装成单一方法总精度。所有场景真值经30、纬25根/cm。

| 场景 | 原版经/纬根每cm | 浮点优化经/纬 | 原版经/纬相对误差 | 渲染秒 / MiB | A/B峰值MiB |
|---|---|---|---|---|---:|
| plain_dev | 30.556/6.266 | 30.075/25.118 | 1.853%/74.936% | 76.00 / 1125.5 | 1741.0 |
| plain_material_holdout | 8.536/24.444 | 30.075/25.118 | 71.547%/2.224% | 99.62 / 1086.2 | 1671.1 |
| twill21_dev | 8.576/6.251 | 30.075/25.118 | 71.413%/74.996% | 51.81 / 943.1 | 1772.5 |
| twill31_dev | 8.577/24.48 | 30.075/25.118 | 71.41%/2.08% | 76.18 / 1050.6 | 1709.2 |
| twill31_material_holdout | 8.577/24.093 | 30.075/25.078 | 71.41%/3.628% | 63.11 / 1001.1 | 1664.2 |

优化经密误差0.25%；纬密误差0.312%～0.472%。密度接近不等于中心存在、物理ID或组织结构正确。逐方法precision/recall、预测数、实际数、误检、漏检、最差窗口、绝对/相对密度误差与0.20/0.25/0.32/0.40门限敏感性完整保存在各comparison.json及SUMMARY.json。九窗口累计根数重复抽样同图，不能当作独立全图纱线总数。

### 失败排查

3/1开发场景纬向8/9拒识。保存的原因主要为LONGITUDINAL_PHASE_INCONSISTENT以及PHASE_COMPETITION_OR_EDGE_AMBIGUOUS；最差窗口F1为0。未放宽门禁或调整合成光照以提高F1。
另外实际运行只读模态消融：同一图像提议纱距下，3/1纬向RT通过1/9，重复T诊断通过8/9，重复R通过1/9。这支持反射长浮显露模式与当前联合相位假设冲突；不证明T可以单独确认真实实体。复制T不是独立双证据，也没有被作为新生产算法。完整结果见twill31_phase_ablation.json。

## M5决定与后续入口

当前只可作为更可解释的物理模拟基线；照片真实感、真实R/T标定与斜纹纬向实体识别尚未达标。维持独立分支，暂不提出合并。
Runner渲染峰值943～1126MiB；整个A/B进程1664～1773MiB。包含解码、多个比较方法及评分真值，不能直接视为生产推理RSS；没有RK3576真机、NPU或含前端的4GB联合运行证据，尚不能确认设备内存余量。
下一步先补离散纤维/毛羽、非椭圆束截面和实测透射对照；算法侧单独验证按模态质量选证据与长浮遮挡下的相位拒识，保持门禁与竞争假设。新的留出必须重新固定种子/材料后运行。

## 复现命令

```bash
cd shibie && python -m unittest discover -s tests -v
# repository root:
python shibie/audit_legacy_rt_optics.py --out /tmp/legacy-audit
python shibie/synthetic_rt_heightfield_8k.py --out /tmp/twill31 --weave twill_3_1 --seed 38121
python shibie/audit_heightfield_rt.py --images /tmp/twill31 --reference datasets/user_contributed/2026-10-13-six-fabric-images/images/U20261013_05.jpg
# Actual visual inspection of generated originals must be recorded separately.
python shibie/compare_physical_rt_8k.py --case twill31_dev --images /tmp/twill31 --out /tmp/AB
python shibie/diagnose_physical_rt_refusals.py --images /tmp/twill31 --out /tmp/phase-ablation.json
```

完整五场景参数和CLI见SCENES_FROZEN.json与.github/workflows/shibie-8k-rt-physical-optics.yml。
## 最终完整性复核

FINAL_VALIDATION.json逐组核对：原生尺寸、图像哈希与冻结预测一致、0°、50mm框、全部评价窗口位于框内、全图492个纱线ID跨两组全局唯一、中心坐标误差小于0.002px，记录宽度样本P10大于12px。几何完整性通过不等于照片真实感通过。

DESKTOP_RUNNER_REPEATABILITY.json记录全部五组、十张原图的桌面重复渲染与最终CI逐字节哈希完全一致。桌面独立重复运行实际日志见local_execution.log。阶段提交和未完成事项见M5_DECISION.md。

传输复核发现M1首批四张PNG上传被输出长度截断；最终提交用分块传输修复，并以Git内容哈希核对。数值审计JSON和旧源代码未受该图片传输问题影响。
