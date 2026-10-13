# 第一组真实物理纱线识别：标注语义更正与三步实测协议（2026-10-13）

基线：main `e1b219384224e1d77c79aa108bef3fb51a39ea56`；分支 `research/physical-yarn-trajectory-3stage-20261013`。

## 标注究竟是什么（用户最终更正）

**已审核的 U20261013_01、02、03、05、06 的人工线表示同一根真实物理纱线的连接/延伸轨迹**，不局限于相机能够直接看见的短纱段：真实纱线在交织处可能被遮挡，操作者据周围结构推断其连续走向。

- `annotation_target = PHYSICAL_YARN_TRAJECTORY`，`path_may_cross_occlusion = true`。
- 每条轨迹由操作者点击两点，用作真实纱线的**方向先验、近似物理位置及相邻不同真实纱线的间隔关系**。
- **不保证**这两点之间的每个像素都属于直接可见纱线；`visible_pixel_gt_confirmed=false` 且 `centerline_pixel_gt_confirmed=false`。这不是 `VISIBLE_YARN_SEGMENT` 正样本，也不是逐像素中心线标注。
- 同组不同的 `reference`、`check_same`、`holdout_same` 代表操作者认定的**不同根真实纱线**；B组为 `check_cross`、`check_cross_second`。仍然不能自动判定经/纬物理身份，保留 `UNKNOWN`。
- `same_family_intervals` / `cross_family_intervals` 是操作者确认的两根不同真实纱线之间间距格数，可以用于粗略物理间距几何校核，但不是算法的自动根数；画线位置为估算，不可充当单纱像素级真值。
- 所有 U20261013 坐标是**无标记中心裁剪 2× 放大图的原生像素**，与原照片的映射仅为 `original = crop_original_xyxy[:2] + zoom / 2`；**放大并不增加实际可观察的纱线信息**。

## 目标与边界

不需要恢复完整跨遮挡单纱网络，先实现第一组的物理方向、可见局部证据和粗略间距/不同纱线归属；最终要逐项证明候选线不只是斜纹、缝隙或周期纹理，不能把规则候选网格当成物理纱线。

### 步骤 A：真实纱线走向

采用 `reference` 的两点计算0–180°轴向角，分别用 `check_same`、`holdout_same` 检查其他真实物理纱线的方向一致性。这里方向来自人工判断，不是自动定向成功率。近正交B组仅供后续对照。

### 步骤 B：在原图像素里独立找局部可见证据

`benchmark.direction_only_first_yarn.score_profile` 采用定向多尺度差分高斯脊线滤波，横跨图像五个空间窗，寻找重复出现的局部图像峰。人工参考线的**方向**决定滤波角度，其**近似位置**仅用来选ROI，绝不用于决定明暗正负极性、中心相位或候选纱线条数。模态是原始色彩/亮度，不用另一根人工轨迹调参。

这只生成 `IMAGE_TEXTURE_RIDGE_CANDIDATES_REQUIRE_YARN_CONFIRMATION`。即使照片中颜色纹理和物理纱线不一致，也不能直接称输出结果“真实纱线”。

### 步骤 C：真实纱线几何核验（并非像素准确率）

`benchmark.first_yarn_three_stage` 独立得出候选后，再对照未参与拟合的 `check_same` 与 `holdout_same` 人工**真实物理纱线连接轨迹**的方向、粗略位置以及人工确认的间隔数：

- 检查候选峰是否接近这几条**推断轨迹**，距离标准按候选间距归一化。
- 检查参考与第二根标注之间自动候选间隔数和人工纱距格数是否吻合，诊断 `p/2`、`2p` 等混叠。
- 同时保留选择通道、滤波尺度、候选个数及完整检测叠加图。
- 这里的对照只是“与操作者推断物理路径的**几何一致性**”，**不是**可见纱段像素 IoU，也不是逐根识别正确率。实验会始终输出 `ABSTAIN_NOT_ENOUGH_VISIBLE_YARN_PIXEL_GT`，直到有独立确认的局部直接可见纱线和非纱线负例。

## 验证要求与本轮缺失的信息

- **已有**：五份真实物理纱线连接轨迹标注，人工确认的同组间隔数，六张放大原图及哈希，第一方向近正交关系。
- **仍缺**：用于直接检验纱线身份的局部可见纱线 positive patch、明暗斜纹/纱缝 negative patch、单纱中心偏移像素容差定义、同平面5 cm 标定框。
- 若想证明“识别到**真实单纱**”，必须先找到一组不用于参数拟合的局部可见纱段正例及纹理负例。不能仅因多条图像候选与人工方向同向或根数接近就宣称成功。

## 复现

```bash
git fetch origin
git switch research/physical-yarn-trajectory-3stage-20261013
python -m pip install -r demo/v5/requirements.txt Pillow
python -m benchmark.manual_annotation audit
python -m unittest benchmark.tests.test_manual_annotation benchmark.tests.test_user_zoom_annotation benchmark.tests.test_first_yarn_three_stage -v
python -m benchmark.first_yarn_three_stage --out experiments/first-yarn-3stage
```

结果：`experiments/first-yarn-3stage/summary.json`、每张对应 `U20261013_XX.jpg` 双联可视化。实验没有修改冻结V4/V5，不覆盖main，不填造根/cm。

首次运行与后续回放的数字以 GitHub Actions Artifact 为准。
