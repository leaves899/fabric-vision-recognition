# 牛仔面料专用照片子集

本目录只索引 `datasets/public_samples/images/` 中的**真实牛仔布照片**，用于 V5 基于人工两点参考方向的真实纱线定位、织纹判别与十项参数的研发验证。**不包括**其他平纹面料、丝绸、灯芯绒、织锦、花呢、格子布和复杂装饰照片。

## 样本选择

`selection.json` 为机器可读的清单：

- `CORE_CLEAN`：**12 张**经实际缩略图检查的干净牛仔布照片候选；新纳入 D017（三星手机）和 D018（iPhone 12）。这是视觉筛选，不是逐根纱线已验证真值。
- `CROP_REQUIRED`：**5 张**，新增 D016（边缘有相框）需要先裁剪并逐像素核验 ROI；未裁剪不得直接进入纯织物训练集。
- `AUXILIARY` / `AUXILIARY_PROCESSED_TEXTURE`：**7 张**，其中 D019–D021 是 Poly Haven 对 3 个独立材质资产制作的 diffuse/albedo（漫反射色彩）贴图，不能与手机照片视为同一种数据分布。
- `EXCLUDED_COMPLEX`：**2 张**（D005 口袋、D010 缝线占比高且分辨率低），按“不收太繁复照片”的标准剔除正式测试。
- `THUMBNAIL_VISUAL_SCREENED`：已经基于缩略图进行缝线/口袋/织物主体预筛，**不代表物理纱线标注完成**。要形成经纬方向真值，需基于原图坐标选取同一根清晰真实纱线上相隔 ≥20 像素的两个点，人工确认经/纬身份后再生成 V5 所需 JSON。
- `collection_group`：来源相同或可能属于相同面料摄影系列的图片按组处理；尤其 `NIJAKI-WORN-DENIM-SERIES` 需整体分配至同一 DEV/VALIDATION/TEST，避免泄露。

## 不能伪造的标注

- 图片缺少项目规定的同平面 5 cm × 5 cm 实体框。不能计算可用于正式验收的经密或纬密根/cm。
- 组织类型只能是来源/视觉候选，不能由蓝白纱线或斜纹方向推断确定的 2/1、3/1 左右斜。
- 未独立确认的纱线方向、经纬身份和纱线根数使用 `null` / `NOT_EVALUATED`；绝不能把整条斜纹带当真实单根纱线。
- 旋转变换后的图像需要独立更新人工参考点；原图坐标的方向不能无条件沿用。
- 核心图片不应混入裤缝、纽扣、口袋、商标、饰片；若一张图片只有部分可用，必须用明确 ROI 排除复杂区域。

## 后续标准化人工预标注（每张核心图）

1. 仅在 `CORE_CLEAN` 集合中开展原始照片的主测试；`CROP_REQUIRED` 必须先根据 `exif_oriented_crop_proposal_xyxy` 对原图逐像素核验再作为补充样本。`EXCLUDED_COMPLEX` 不用于训练或测试。
2. 图中点击真实可见纱线上的两个参考点，导出原图无向纱线轴角及该族身份确认状态。
3. 组织仅填候选弱标签；真实经纬身份未知则不确定。
4. 记下 V4/V5 检测出的候选轨迹与人工参考线的重叠差异，按**同一块布料**划分数据集。
5. 仅当实物 5 cm 标定框与布同平面、人工测得真实经纬密后，才对 8、9 项进行计量评估。

源图、许可及作者保留在 [sources.json](../public_samples/sources.json)，同仓库原始图由 [同步状态](../public_samples/sync_status.json) 判断是否下载完成。

## 最新摄影样本

D011–D015 均来自 Wikimedia Commons 上注明摄影者和再使用许可的照片。视觉缩略图检查后，D011/D012/D013 暂入 `CORE_CLEAN`，D014（过暗）、D015（布边折叠）归入 `AUXILIARY`。D011 是 Wikimedia 官方3840px衍生文件而非原始91MB巨幅影像。完整图片及原始URL以 [sources.json](../public_samples/sources.json) 为准，机器可读筛选名单为 [selection.json](selection.json)。

## 独立来源优先批次 D016–D021（2026-10-12）

| ID | 取景或处理来源 | 筛选等级 | 独立性证据 |
|---|---|---|---|
| D016 | Theerawat Sangprakarn；非手机织物摄影 | 待裁剪 | 独立摄影作者，但照片外圈有装框 |
| D017 | Montoya2002；Samsung SM-N975F | 核心候选 | 独立摄影者、独立拍摄时间；具体物理布样身份无证据 |
| D018 | Maurizio Baldi；iPhone 12 | 核心候选 | 独立摄影者、独立拍摄时间；织纹清晰、933×1096 |
| D019 | Poly Haven fabric_03；colormass | 处理纹理辅助 | 与 fabric_04/05 是不同 **asset ID**，但同处理提供方 |
| D020 | Poly Haven fabric_04；colormass | 处理纹理辅助 | **不同材质资产**，并非已验证不同织厂 |
| D021 | Poly Haven fabric_05；colormass | 处理纹理辅助 | **不同材质资产**，而非第 5 张摄影原片 |

**评估隔离要求**：基于 `collection_group` 分组并额外遵守 `source_domain_group=POLYHAVEN_COLORMASS_2025`；所有该处理来源的样本应归入同一 split，避免评估受同源摄影和标准化算法风格泄露。新来源并不能证明物理布料一定不同于已有样本，这一事实须在获得布料样本 ID 前保持未知。

- 原图库与来源：[sources.json](../public_samples/sources.json)
- 视觉筛选及机器消费：[selection.json](selection.json)
- 全部缩略图：[review_previews](../public_samples/review_previews/)
