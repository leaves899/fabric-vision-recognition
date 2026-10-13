# P0-1 物理纱线 vs 纹理：独立证据实验首轮结果（2026-10-13）

## 来源、结论和实现边界

接收研究报告《织物真实物理纱线识别：三个 P0 核心问题技术研究报告》后，**不重写V4/V5，不另开分支**，在当前第一组 `PHYSICAL_YARN_REFERENCE` 研究路线中优先落地其建议 E1：独立纱线可见正例 / 非纱线纹理负例对照和逐候选证据可审计数据。

新增：
- `benchmark/p0_yarn_evidence.py`：复用现有 A1+A2+人工确认间隔数的候选格点，输出逐候选的边界、局部连续性、位置稳定、周期先验等**图像证据**和`YARN/GAP/TWILL/COLOR/SHADOW/UNKNOWN`竞争解释；**不伪造纤维形态、交织拓扑、多光照**证据，缺失字段均为null。
- `datasets/physical_evidence_labels/local_patches.json`：合法的、**尚无任何独立物理真值条目**的标签容器；配套README定义标注来源、身份/负纹理类别、防止单图误标物理真值等限制。
- `benchmark/tests/test_p0_yarn_evidence.py`：7项契约测试（高光学分也不能宣称纱线、无独立验证不得生成概率/计数、手机单图不能作为独立物理证据、偏移半节距不能自动视作负例、裁剪不镜像、图块/来源测试）。
- `.github/workflows/first-yarn-three-stage.yml`：与旧三步/四步实测共享同一工作流，生成候选三联图、完整summary、自动保留实测证据。

关键定义：
- `PHYSICAL_YARN_REFERENCE`：人工一条两点轨迹=一根**真实物理纱线的推断路径**（可遮挡），**不是**局部可见像素真值；A1+A2校准、A3独立留出，B组仅用于未来第二方向。
- 中央图为当前光学候选，两侧为**未标注**的半纱距偏移对照。两侧可能是纱线/间隙/纹理，不能未核实就当负例。
- `image_evidence_score` 只是高度相关的图像信号的启发式分数；`physical_identity_probability=null`，`count_eligible=false`，`identity_hypothesis=UNKNOWN`；拒识并非正确识别。
- `PHYSICAL_YARN_VISIBLE` 与 `GAP/TWILL_TEXTURE/COLOR_STRIPE/SHADOW/UNCERTAIN` 必须有**独立物理证据**，否则不许录入测试真值；未获取前不能计算 Precision/Recall/AUPRC 或根数误差。

## 真实 GitHub Actions 结果

[实测动作/45项单元测试成功](https://github.com/leaves899/fabric-vision-recognition/actions/runs/38353064393)

[5张真实照片的照片叠加 + P0-1 候选三联图 + 完整JSON Artifact](https://github.com/leaves899/fabric-vision-recognition/actions/runs/38353064393/artifacts/11791692417)

| U样本 | 名义第一组格点（不能当真实根数） | 有局部图像支持的格点（不能当真实根数） | 独立已审核物理身份正负标签 |
|---|---:|---:|---:|
| U20261013_01 | 33 | 17 | 0 |
| U20261013_02 | 38 | 16 | 0 |
| U20261013_03 | 33 | 22 | 0 |
| U20261013_05 | 46 | 4 | 0 |
| U20261013_06 | 84 | 0 | 0 |

在这个阶段“图片格点17/33有支持”不等于“17/33根是真纱线”；**本轮没有任何新的真实物理纱线身份准确率结果**。由于训练/评估需要的独立真值还没有，P0-1真正的分类能力仍是未验证；P0-2概率校准不可实施，P0-3缺可信正反面配对元数据也不能验融合收益。

## 报告评审及下一个实验门槛

外部研究报告正确识别了单图二维投影的不可辨识性，提出优先 P0-1 E1，再 P0-2、P0-3。实际最难点不是添加更多图像分数，而是确保“正/负”标签不与待验证算法同源：**普通手机上的灰暗条带不能靠算法输出作为正例，偏移半纱距也不能自动视作GAP**。具有真实物理核对能力的多角度光照/真正微距/直接布料检查，才能构造可靠的数据基础。

实验下一步应在另一批独立真实布料上采集/审核有争议候选的局部证据，确认其 `PHYSICAL_YARN_VISIBLE` 或 `GAP/TWILL_TEXTURE/COLOR_STRIPE/SHADOW` 等类别；依据 `physical_fabric_id` 严格划分 DEV/CALIBRATION/TEST。**这里不要求重画旧长线**；仅给新独立局部证据赋标签。完成前仍须拒绝输出已验证真实根数，未知经纬身份保持 UNKNOWN，不从2×插值图直接计算根/cm。

## 复现

```bash
python -m unittest benchmark.tests.test_p0_yarn_evidence -v
python -m benchmark.p0_yarn_evidence --out experiments/p0-yarn-evidence
```

本实验代码、标签文件、图像叠加仅在 Draft PR #16 研究分支中；原 `main`、V4/V5 引擎及用户两点标记/图片都未覆盖。
