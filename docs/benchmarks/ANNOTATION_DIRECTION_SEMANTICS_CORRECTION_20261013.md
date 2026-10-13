# 2026-10-13 人工标注语义纠正：连接方向 ≠ 可见物理纱段

## 用户澄清（本次已确认）

用户在查看首次物理纱线研发结果后指出：「我标注的不是可见纱段，而是实际上的纱线连接方向」。

此前 `datasets/annotations/drafts/U20261013_01/02/03/05/06.json` 中的 `reference`、`check_same`、`holdout_same`、`check_cross` 和 `check_cross_second`，**不得被当成原图中可观察到的纱线脊线/中心线像素真值**。

原始人工坐标及哈希保留不改。原字段 `reference_confirmed=true`、`review_state=OPERATOR_REVIEWED` 表示人工确认的连接方向意图，不再据此推定纱线实际像素位置已确认。经纬身份仍未知。

## 立即失效的结论（PR #15 历史首轮报告）

在虚拟连接线位置提取亮度/颜色/图像脊线响应，再计算与这条线的距离、或计算半间距偏移位置的对比，是建立在错误的“可见纱段”标签假设上。这些指标的数值仍可审计，但**不允许引用为任何物理纱线定位成功/失败、根数准确率或物理纱线图像特征的证据**。

旧代码 `benchmark.first_yarn_evidence` 对 U20261013 批次现在返回 `INVALIDATED_DIRECTION_ONLY_ANNOTATION`，保留此前受影响实验的历史记录但不纳入验收。

PR #14 的第二方向评估中，角度与人工推断方向的一致性仍可作为参考，不能宣称同一根真实纱线定位；其利用人工间隔数计算的像素 pitch，独立物理计数与标注语义尚需核实。

## 现在仍允许进行的工作

1. 使用两点的**角度**作为用户提供的纱线方向先验，不使用两点的**位置**来拟合单根纱线中心、亮/暗极性、相位或纱线间距。
2. 图像算法独立提出短纱段或线状结构候选，并给出局部颜色、边界、纹理连续性等可核验像素证据。
3. 输出 `CANDIDATE` 与拒识状态；不从线条数量直接报告根/cm，不声称逐根纱线身份已确认。
4. 跨布料评价需要新增**独立可见纱段小区域正例**、**纱线间隙或斜纹负例**，同时保留不同布料测试集与拍摄旋转测试。
5. 如果用户日后明确标记真实可见纱段，应使用新标签字段和单独审查流程，不能静默复用旧 `reference` 轨迹坐标。

新增 `benchmark.direction_only_first_yarn` 只以图像+方向角寻找多截面持续存在的图像脊线。候选线可能是纱线、阴影、间隙或组织纹理，没有用户可见纱线正例之前**不能计算物理识别准确率**。

## 复现

```bash
python -m benchmark.manual_annotation audit
python -m unittest benchmark.tests.test_first_yarn_evidence benchmark.tests.test_direction_only_first_yarn -v
python -m benchmark.first_yarn_evidence --out experiments/first-yarn-invalidated
python -m benchmark.direction_only_first_yarn --out experiments/first-yarn-direction-only
```

冻结 V4/V5 保持不变，`main` 与原始标注不受本研究分支的改动影响。
