# 公开织物近景测试照片（8 张）

这批照片来自 Wikimedia Commons，**已经核对来源页面和开放许可**。它们是实际织物摄影图片而不是组织示意图。原图由 `scripts/fetch_public_samples.py` 根据 [sources.json](./sources.json) 下载到 `images/`，`checksums.sha256` 用来复核文件一致性。

| ID | 图片 | 来源所述组织候选 | 测试重点 |
|---|---|---|---|
| P001 | [平纹放大纺织物](./images/plain/01_simple_textile_magnified.jpg) | 平纹 | 两组近似正交方向、明暗纱段 |
| P002 | [平纹细节](./images/plain/02_plain_weaving_detail.jpg) | 平纹 | 纱线排列与候选粗细 |
| P003 | [平纹近景](./images/plain/03_closeup_plain_weave.jpg) | 平纹 | 低分辨率下的方向稳定性 |
| T001 | [牛仔布近景](./images/twill/01_denim_closeup.jpg) | 斜纹 | 纹理方向误判风险 |
| T002 | [格纹布料近景](./images/twill/02_tartan_2x2_closeup.jpg) | 2/2 斜纹（来源明确标注） | 区分彩色条纹、斜纹与经纬纱 |
| T003 | [斜纹毛毯](./images/twill/03_twill_blanket.jpg) | 斜纹 | 不同材质下的泛化能力 |
| T004 | [手机拍摄牛仔近景](./images/twill/04_phone_denim_detail.jpg) | 牛仔布斜纹候选 | 移动端摄影的纹理变化 |
| U001 | [组织未标注布料](./images/unknown/01_fabric_close_up.jpg) | 待确认 | 未知组织/颜色/纹理，不用于有监督真值测试 |

## 与十项目标的对应关系

- **可做初步评价**：经纬两组方向候选（1、2）、排列状态（3、4）、纱线粗细候选（5、6）、组织类型候选（7）、表面纹理及色系（10）。
- **不能做绝对数值验收**：经密（8）与纬密（9）。**这些照片没有实体 5×5 cm 标定框或可核对的长度标尺**，不能用像素数量换算出真实根/cm。
- 未知真实经向/纬向身份；斜纹左右向、组织规格不应仅依据照片呈现方向猜测。T002 由原始图片说明标注为 2/2，其他斜纹不推断 2/1、3/1。
- 来源页面的组织名称是**候选弱标签**，不是经过人工显微复核的交织点真值。正反面配对未知。下载的原图保持原始方位，不自动旋转。

## 授权与数据治理

逐张署名、来源、许可链接记录在 [sources.json](./sources.json)。本项目根目录的 LICENSE **不覆盖**这些第三方照片。其中 CC BY-SA 图片的改作、转发等须遵守相应署名和相同方式共享条款；CC BY 需署名；CC0 无强制署名但保留出处便于追溯。

所有样本只用于公开许可照片上的非正式算法调试与回归测试。正式密度/尺寸测试需单独拍摄：**实体 5 cm × 5 cm 方框与布料同平面、全框可见、纱线清晰、经纬方向人工确认**，并补齐 `cm_per_pixel` 及实际计数真值。

如需重下，在仓库根目录运行：

```bash
python -m pip install Pillow
python scripts/fetch_public_samples.py
```
