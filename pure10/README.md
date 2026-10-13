# Pure10 — 第一性原理的独立纯算法基线（实验阶段）

分支：`experiment/first-principles-ten-parameters-20261013`。不修改 V4、V5、V1.5 或原始照片。

## 原理与边界

输入为真实手机纱线照片；仅用 NumPy / SciPy / OpenCV。**不读取人工参考点参与推理**。先在原生像素上以多个空间块计算分频带 FFT 方向证据（低频斜纹图案降低权重，高频纱线表面细节增加权重），要求两组正交方向均提供证据；再把图像旋转对齐，在多个真实空间子区域比较周期响应，检测候选峰及其表观半高宽。要求两族同时有信号，避免只凭斜纹带得到一个假方向。周期和平行峰仍然只是候选，不等于已经逐根证明为真实纱线。

方向判定方法并不宣称已经解决“斜纹纹理 vs 物理纱线”的根本歧义；对于欠缺支持的方向、纱宽、交织点与组织分类必须拒识。禁止对每块布写单独阈值、学习标注角度、用同张图片上的人工参考线直接覆盖算法结果。人工标注只能由评估脚本事后读取。

### 十项输出契约

每个字段均包含 `status`、`value`、`reason`、`evidence`。方向、排列、半高宽相对等级及色系是条件候选；未确认经/纬身份时，其对应四对字段保持 `UNAVAILABLE`，同时输出无需经纬身份的 `axis_families.a/b`。

1. 经向方向与角度（角色确认后才可标记）
2. 纬向方向与角度（同上）
3. 经纱排列状态（候选中心距变异系数）
4. 纬纱排列状态（同上）
5. 经纱表观粗细候选等级（峰半高宽与周期之比，不等同 Ne/tex）
6. 纬纱表观粗细候选等级（同上）
7. 组织结构候选（按交叉区域局部梯度计算光度占优 1/0/未知矩阵，再以平纹、2/1、3/1、缎纹模板严格拟合；**只属于光度候选，并非物理上下已验证**，不满足置信门槛返回 UNAVAILABLE）
8. 经密：只在提供真实同平面 5 cm 内框四角后输出未确认计数候选
9. 纬密（相同限制）
10. 表面纹理和色系（HSV / 高频特征候选，不以此推断斜纹方向）

**本分支 v0.1 是十项结构化接口 + 保守算法基线，不是十项全通过的交付版本。** 密度属于 `CANDIDATE`，直至独立真实数纱验证。无人工经纬角色时，不凭相机方向猜测经/纬。

### 运行

```bash
python -m pip install -r pure10/requirements.txt
python -m pure10.engine datasets/user_contributed/2026-10-13-six-fabric-images/zoom_unmarked/U20261013_01_center_2x.jpg --output pure10-out/single.json --evidence pure10-out/single.png
# 操作者已独立确认第一组为经向时
python -m pure10.engine path/to/photo.jpg --warp-family a --output pure10-out/recognized.json
# 真实 5cm × 5cm 实体框内侧坐标：TL,TR,BR,BL。不可用 2x 缩放臆造标尺。
python -m pure10.engine path/to/full_frame_photo.jpg --warp-family a --corners-json true_frame_corners.json --output pure10-out/physical_candidate.json
# 对 GitHub 最新六块独立布及人工标记运行不泄漏评估
python -m pure10.evaluate_six --output pure10-out/report.json --overlays pure10-out/overlays
python -m unittest discover -s pure10 -p 'test_*.py' -v
```

### 标注语义（2026-10-13 修正）

- `reference`、`check_same`、`holdout_same`：同一方向族的**三根不同物理纱线**；每条两点之间是同一根物理纱线的路径方向参考，即使被交织遮挡。
- `check_cross`、`check_cross_second`：交叉方向的**两根不同物理纱线**。
- 并非每根相邻：必须用 `same_family_intervals` 与 `cross_family_intervals` 作跨线计数换算。
- 人工点在未标记 2× 放大图原生坐标中，不能与原图像素混用；放大不增加有效空间分辨率。
- 每个 fabric_id 最多记一块样布；完整原图与放大图是同一块布，绝不能当成两个独立验证样本。

### 可复核测试

GitHub Actions 工作流 `pure10.yml` 会直接检出本分支最新原始照片与标注，对 6 张 zoom JPG 全部运行候选分析、90°/180° 旋转协变性检查，遇到缺失标注仍保留该布的候选结果但不宣称有准确率，最终上传 `report.json` 和各布证据图。评估指标包含独立参考方向角误差、每根真实纱线的平均像素间距相对误差；保留逐布误差，禁止只报总平均。当前没有六布的组织类别/实际纱宽/真实密度独立真值，因此这些项目**不能声称验收通过**。

目标终态仍然是文档中的十项能力。当前“真实线可辨性、组织矩阵与不同织物通用性”没有被认为已经解决。

### 实验阶段记录

- 2026-10-13 / v0.1：以最高 ACF 周期选择方向，5 张人工标注布样的方向误差中位数 35.106°，同族纱距相对误差中位数 108.57%；**失败**，其假方向被斜纹/表面纹理带偏。CI 证据：https://github.com/leaves899/fabric-vision-recognition/actions/runs/38340983269。
- v0.2：加入跨频率谱带的双正交方向约束；复核使用了同一批图片的结果并确定了谱带权重，因此这批图片从此属于**算法研发集**，并非全新布料盲测。每次改动必须输出逐布误差，不得宣称跨布料正式准确率。下一批独立布料及实测数纱真值是验收前提。
