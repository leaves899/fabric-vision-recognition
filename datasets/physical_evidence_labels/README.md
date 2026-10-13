# P0-1：真实纱线可见证据与非纱线纹理独立标注

**当前标签数：0。** 这里是独立物理真值入口，并非要重做既有 `PHYSICAL_YARN_REFERENCE` 的 A1/A2/A3 人工两点标注。原标注意义不变：一条路径对应一根真实物理纱线，允许在交织点被遮挡；它不是连续可见纱段，更不是像素掩膜。

脚本会生成以 `sample_id:A:grid_index` 标识的候选图块三联图：**左/右均为未标注的半纱距偏移对照，不得默认当成 GAP 或 TWILL 负例**。半纱距偏移可能仍穿过纤维或遮挡。中图也只是未验证候选，不是正例。

为了验证 P0-1，应由独立观察证据决定候选是 `PHYSICAL_YARN_VISIBLE`、`GAP`、`TWILL_TEXTURE`、`COLOR_STRIPE`、`SHADOW` 或 `UNCERTAIN`。不能在看不清的普通 RGB 图像上硬贴“真纱线”标签；推荐在同位置使用真正微距/显微镜、侧向多光照或直接物理查看；标记视野、拍摄对应关系及评审者。样本04没有已审核的纱线参考，不允许凭空补标。

当有经过独立审核的数据时，每个 `labels` 项的结构示例如下（**示例不是数据，不要直接填到实际 JSON**）：

```json
{
  "candidate_id": "U20261013_01:A:0",
  "sample_id": "U20261013_01",
  "physical_fabric_id": "请从manifest原值填写",
  "image_sha256": "对应样本已登记的真实sha256",
  "label": "UNCERTAIN",
  "evidence_source": "MICROSCOPE_PHYSICAL_CONFIRMATION",
  "reviewer": "人工审查人编号",
  "independent_review": true
}
```

`evidence_source` 仅可用 `MICROSCOPE_PHYSICAL_CONFIRMATION`、`MULTI_LIGHT_PHYSICAL_CONFIRMATION`、`DIRECT_PHYSICAL_INSPECTION`。照片上目测或算法自动判断属于**弱标注/假设**，不能作为独立物理真值录入该文件。独立验证集应按 `physical_fabric_id` 分割 DEV/CALIBRATION/TEST，不能把同一布的许多候选当成许多独立布料。

当前 E1 输出字段中，`image_evidence_score` 是仅根据图像脊线/边界/沿线支持计算的**启发式光学指标**，不是 `physical_identity_probability`；后者固定为 `null`。系统 `identity_status` 为 `UNCERTAIN_IMAGE_SUPPORTED` 或 `REJECTED_INSUFFICIENT_IMAGE_EVIDENCE`，`count_eligible=false`。即使一条规则印刷条纹得到很高图像证据，也不能标为已识别真实纱线。

复现命令：

```bash
python -m unittest benchmark.tests.test_p0_yarn_evidence -v
python -m benchmark.p0_yarn_evidence --out experiments/p0-yarn-evidence
```

本实验的成功标准不是漂亮的候选图，而是**在另一批独立布料及独立正负真值上，真实纱线漏检率、纹理误检率和拒识覆盖率的可测改善**。若原始普通手机图像不含足以区分的物理信息，应如实记录 `NO_DISCRIMINATIVE_EVIDENCE` 并提出拍摄要求，而不是通过阈值“调成功”。
