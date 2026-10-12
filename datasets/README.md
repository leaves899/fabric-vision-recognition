# Step 0 — 数据集与人工真值（普通手机照片兼容模式）

本目录当前只有**空模板**，没有杜撰样布、人工密度、组织或经纬方向真值；不要将已有 V4/V5 候选轨迹当人工真值。

## 1. 采集与标注口径

- 每张普通手机照片独立记录 `fabric_id + position_id + face`。正反面允许不配准，也不要求透射图。
- `face` 为 `FRONT`/`BACK`；`capture_mode` 为 `PHONE_REFLECTION` 或 `PHONE_UNKNOWN_LIGHTING`；`calibration_type` 可为 `NONE` 或 `FRAME_5CM`。
- 有实体框时，只有核验**与布料同平面、内侧 5 cm × 5 cm** 的四角后，才能把 `frame_confirmed` 设为 `YES`。本表中的标记不能代替 V5 输出 JSON 的实际标定证据。
- 每个 `fabric_id` 必须全部放在同一个 `split`（`DEV` / `VALIDATION` / `TEST`），包括不同部位、正反面和旋转图；禁止泄露。
- 方向角 `warp_axis_deg` 和 `weft_axis_deg` 为各自拍摄照片中的无向图像轴角，范围 `[0,180)`，原点左上、x 向右、y 向下。**反面照片旋转后不能直接沿用正面角度。**
- 纱线身份必须人工确认；密度单位为**根/cm**。人工计数时记录截线长度和方法于 `notes`，并使用独立来源审查。组织/纱宽可先留空。
- `review_status` 为 `NOT_EVALUATED` / `DRAFT` / `CONFIRMED`。只有 `CONFIRMED` 且写明 `gt_source` 的真值参与指标评估，未确认项仍留空。

## 2. CSV 字段

`manifest.csv`：

| 字段 | 含义 |
|---|---|
| fabric_id / position_id / face | 唯一图片位置与拍摄面标识 |
| split | 按布料划分开发/验证/测试集 |
| capture_mode | 普通手机照片拍摄模式 |
| image_path | 仓库根目录相对路径，原始照片 |
| result_json_path | 可空；保存的 V5 `/api/analyze` 响应 `result` 或裸 JSON，**不自动构造参考点** |
| calibration_type / frame_confirmed | 有无已确认 5 cm 实体内框 |
| notes | 人工备注 |

`ground_truth.csv`：同一个三字段键、审核状态、来源、两方向角、两项实际经纬密度、组织和备注。可先填写图像目录与标签状态，后补确认真值。

## 3. 执行命令（仓库根目录）

```bash
python -m benchmark.dataset --check-images
python -m unittest discover -s benchmark/tests -v
python -m benchmark.runner --out experiments/step0-baseline
```

前两条检测数据完整性和单元测试；最后一条将 V5 JSON 候选对齐到人工真值，并生成 `benchmark.csv`、`benchmark_summary.json` 与 `benchmark_summary.md`。没有确认的人工真值时返回 `NOT_EVALUATED` 并用退出码 `3` 表示**尚未形成可评估结果**，这不是算法失败也不能声称已通过验收。

`runner` 不调用 V4，不会自动生成“同一根纱上的人工两点”，也不会把纹理方向转换为经纬真实方向。方向缺少人工经纬身份则拒评；密度还要求 V5 结果真实确认的标定框。输出为**候选误差**，并不意味着逐根纱线已证实。

建议逐步采集 30–50 块开发样布、另留约 20 块独立验证样布（V1.5 研发建议），不必等齐才搭框架。真实样布及客户图片未经许可不要上传到公开仓库。

## 4. 公开照片的增量入库（研发弱标签，不是人工 Ground Truth）

本项目中的 Wikimedia 来源照片与真实手机正反面照片应区别管理。公开图片不保证拍摄面、真实经纬身份、同一块布料配对、5 cm 实体框和物理长度。不要因为来源标题写着“平纹/斜纹”，就填写 `ground_truth.csv` 的 `weave_type`，更不能据此生成经纬密度。

当前数据契约增加了：`face=UNKNOWN`、`capture_mode=PUBLIC_UNKNOWN`。来源页面的候选组织只写在 `manifest.csv.notes` 中，用于**分组分析及主动挑选失败样本**，不作为 GT。

在仓库根目录运行：

```bash
python -m benchmark.public_intake              # 预览，默认不改文件
python -m benchmark.public_intake --write      # 仅登记磁盘上已下载的照片，保留已有人工作业
python -m benchmark.dataset --check-images    # 逐路径验证文件存在、表头与划分
python -m benchmark.runner --out experiments/public-dev
```

未下载的来源记录会出现在 `pending_image_download`；它们**不**进入 `manifest.csv`。重复执行 `--write` 应当幂等，不覆盖已有人工标注或样本划分。新增照片应先核验图片来源、许可和实物真实性，再执行导入与提交。不可将公开来源的弱标签当作分类准确率真值；若没有人工参考 P1/P2 与 V5 结果 JSON，则 Benchmark 只能正确地报告 `NOT_EVALUATED`。

详见 `docs/benchmarks/PUBLIC_PHOTO_INTAKE.md`。
