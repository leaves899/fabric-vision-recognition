# G1：单张手机照片物理证据竞争实验（2026-10-13）

## 裁决：G1_NOT_EVALUATED

本次提交是可复现的 G1 实验实现，不是 G1 成功。现有 A1/A2/A3 为 PHYSICAL_YARN_REFERENCE（同根真实物理纱线的推断轨迹，可跨遮挡），并非局部可见纱线分割真值；没有独立审核的纱线实体正例/间隙、斜纹负例，不能报告真实单纱识别率。

使用照片：U20261013_01、02、03、05、06；04 缺已审标注。只在原始相机像素上提取证据；2x 裁剪用于人工标注与坐标映射，校验原图和标注图 SHA256。

## 算法约束

1. A1 reference 方向、A2 check_same 与已确认 same_family_intervals 是仅有的校准输入。
2. A3 holdout_same 仅在输出冻结后检查独立**近似几何相位残差**，不是像素级可见纱线真值。
3. check_cross / check_cross_second 不进入推理。第二方向候选来自照片横向梯度，仅是图像候选。
4. 所有竞争假设共用同一个局部形态分析器：A1/A2 格点、半纱距间隙相位、半周期混叠、正负斜纹解释。
5. 局部形态包括相反梯度的成对边缘、中心-侧翼反差、纤维方向梯度；交织点包括 A_OVER_B_CUE、B_OVER_A_CUE、UNKNOWN。形态与 T 形拓扑可被斜纹/染色纹理伪造，均不直接证明纱线身份。
6. 外观评分不是物理身份概率，最高分不自动转 PASS；无独立物理真值时 G1_NOT_EVALUATED。

## 复现

    python -m pip install numpy opencv-python-headless pytest
    python -m pytest -q benchmark/tests/test_p0_g1_probe.py
    python -m benchmark.p0_g1_probe --out experiments/p0-g1

GitHub Actions 在研究分支自动执行五张照片，上传证据包，包括：

- *_hypotheses.jpg：校准纱线格点与间隙相位；
- *_topology.jpg：A/B/UNKNOWN 的光学交点证据；
- *_competition.jpg：五种假设的图像评分；
- 每张 JSON：分数、纱距、A3 几何残差；
- review_patches/*.jpg、review_manifest.csv：待**独立人工**审核，初始全部 UNREVIEWED；
- summary.json：实验状态、样本数及缺少的真值。

## G1_PASS 的必要条件

在原图/独立高分辨率观测中由人工确认局部可见纱线实体、非纱线纹理或未知，记录证据来源与物理布料身份；按**独立布料**划分 DEV/VALIDATION/TEST，先冻结特征和门槛，再在独立 TEST 比较基线的误检、漏检、拒识和判别力。未完成独立真值时为 G1_NOT_EVALUATED；验证失败为 G1_FAILED。不能把相位偏移候选自动写成负例，不能把人工作图连线像素当正例。

## 风险与边界

间隙也可产生双侧边界，斜纹可跨多个候选交点连续，高反光和低原始分辨率会造成形态不足。候选根数与物理根数分开；没有同平面物理标定不输出根/cm。

对应最新特性设计 FR-005/006 与 FR-012～016：实验性算法不进入生产路由，不修改冻结 V4/V5。