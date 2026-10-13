# E6.3b 原生手机照片遮挡观测审计（实验进行中）

## 目的

E6.3 的二分最大匹配非唯一性是真实数学反例，不能直接解释为物理身份结论。本阶段**不再优化连线权重**，逐个检查连接缺口里是否存在可供后续证伪的、原生相机采样的光学观测量。

## 已实现

- `benchmark/p0_native_occlusion_audit.py`：对于每一条候选前向连接，在两个标注可见段端点之间，沿连接轴线采样9个归一化位置；每个位置取跨轴向的17点灰度横截面，宽度仅按 A 组校准纱距缩放，不写死原生像素间距。
- 输出横截面亮度动态范围、总变差、最大梯度位置；记录无有效相机采样区域为 `null`，不以 0 冒充反证。**这些量不构成完整的实体边界检测算法**。
- `benchmark/p0_physical_connection_identifiability.py`：基于 E6.3 全量结构竞争来源的候选前向连接，统一写出每个样本 `*_native_gap_observations_UNKNOWN.json`。进入这一步时没有读取用户的 `r0004→r0005` / `r0004→r0011` 正负审核，因此两个候选以相同规则处理。
- `benchmark/tests/test_p0_native_occlusion_audit.py`：均匀照片、人工亮度边界、越界缺失、候选顺序置换、非法相机输入五类回归；PR 工作流加入自动运行与实际原相机照片回放。

## 研究解释边界

跨轴向亮度边界可能来自纱线、阴影、反光、色带、织物纹理；目前不能认为它们是独立可观察的真实纱线边界。跨两个可见段的中心线也不是直接可观察的真实实体。光学审计输出统一保留 `physical_identity=UNKNOWN`、`observed_over_under=null`、`fiber_continuity_verified=false`。

新增的两类证据尚不能比较 `r0004→r0005` 与 `r0004→r0011` 哪一条是同一根物理纱线，更不能据此计算识别准确率。后续如需自证物理身份，应在原相机图像下完成“遮挡者连续边界—被遮挡者边界终止—另一侧恢复”**联立竞争假说检验**，并用其他布料与独立实物观测证伪；如果某一证据不可分辨，应明确拒判。

## 测试和复现

```bash
python -m unittest benchmark.tests.test_p0_native_occlusion_audit -v
python -m benchmark.p0_physical_connection_identifiability
```

工作流：`.github/workflows/first-yarn-three-stage.yml`。新增测试是否在 GitHub Actions 全部通过，以相应 run 实际结果为准；本报告不预先声称真实照片已经证明正确同根。不得将 PR #16 合并为可投入生产的自动纱线识别算法。
