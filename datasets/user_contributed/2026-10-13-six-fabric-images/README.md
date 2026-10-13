# 六张手机织物照片：在无标记 2× 放大图上人工标注

本目录已进入 `main`：6 张原始 JPG、6 张中心裁剪后放大 2 倍的无标记 JPG 和哈希/裁剪来源记录。**现在直接在放大后的 JPG 上用现有 GitHub 仓库人工标注器点击并保存**，不是在原图上作点位，不使用助手原先的猜测或标记。

## 人工标注语义（2026-10-13 经用户纠正）

**本批次 U20261013_01—06 的标注对象是“真实物理纱线的推断连接轨迹”（`PHYSICAL_YARN_REFERENCE`），并不是“照片中直接可见的一小段纱段”（`VISIBLE_YARN_SEGMENT`），也不是任意的斜纹纹理方向。**

A 组三条标记各代表不同的真实物理纱线；B组两条代表另一方向的两根不同真实物理纱线。不同标记未必相邻，请用已确认的 `same_family_intervals` / `cross_family_intervals` 表达两条参考间的真实纱距数量。A1+A2用于校准，第三根 `holdout_same` 只用于独立检验。

每组两点表达：操作员判断这两点沿着**同一根真实纱线的物理连续走向**，其中可能有交织遮挡。直线是人工几何近似，不承诺线段上每个像素都属于该纱线，也不是精确中心线的像素级 Ground Truth。两点同时提供方向先验及粗略轨迹位置，但其位置不可直接用于学习像素亮暗模板或定义“可见纱线正样本”；需要另行取得无遮挡可见纱段的小区域正例和纹理/缝隙负例。

本分支为已有的五份人工标注新增 `annotation_target=PHYSICAL_YARN_REFERENCE`、`path_may_cross_occlusion=true`、`visible_pixel_gt_confirmed=false` 和 `centerline_pixel_gt_confirmed=false`；不改变原两点、根数间隔、坐标或图像哈希。尚未确认的 U20261013_04 不伪造标注。

`reference_confirmed=true` 的含义是操作员确认**真实物理纱线连接关系**，而不是这条连接线上的每一个像素都直接可见。经纬身份仍可能为 `UNKNOWN`。人工纱距间隔可以用于研究校准，不能单独证明算法已识别出所有真实纱线。

## 哪张图片用于什么

- `zoom_unmarked/U20261013_01_center_2x.jpg` 到 `_06_center_2x.jpg`：**人工选点、标注 JSON、后续 V5 回归测试的实际输入图**，其像素坐标就是标注坐标。
- `images/U20261013_01.jpg` 到 `_06.jpg`：保留用户上传的完整原始照片，永不覆盖；作为来源证据，**不再在原始照片上点击**。
- `image_provenance.json`：记录逐图的原图 SHA-256、无标记放大图 SHA-256、`crop_original_xyxy` 和 `enlargement_scale=2`，用于测试复核与坐标换算。
- `datasets/manifest.csv` 每张布仍只有 **一个** `U20261013_XX` 样本，`image_path` 指向其放大图。原图/放大图不是两块独立面料，不得拆开计入验证样本数量。
- 放大只是裁剪后的图像插值，**没有产生新的物理纱线细节，也不增加真实密度测量能力**。

坐标换算用于未来跨原图对照：

```text
原图 x = crop_original_xyxy[0] + 放大图 x / 2
原图 y = crop_original_xyxy[1] + 放大图 y / 2
```

保存的 `datasets/annotations/drafts/U20261013_XX.json` 内有 `image_path`（放大图）、`image_sha256`（放大图哈希）、`coordinate_space=ZOOM_2X_NATIVE_PIXELS` 和原图/裁剪来源信息。请勿将放大图点位直接送给原图算法；`benchmark.run_annotated_v5` 会加载清单登记的 **放大图** 及其原生点位进行测试。

## 人工标注（本地 Windows PowerShell）

确认本地 `main` 已同步（无需重新解压/上传照片）：

```powershell
git switch main
git pull --ff-only origin main
python scripts/verify_six_fabric_samples.py
python -m benchmark.dataset --check-images
```

为避免人工标注和程序改动直接污染 main，创建一次专用分支（后续继续使用即可）：

```powershell
git switch -c annotation/six-fabric-20261013
python -m pip install Pillow numpy
python -m benchmark.manual_annotation serve
```

浏览器访问：**http://127.0.0.1:8765/tools/yarn_annotator/**

优先列表中选 `U20261013_01` 至 `U20261013_06`，确认大图展示的是文件名包含 `_center_2x.jpg` 的图。照片下方应出现“2× 中心放大图原生像素坐标”。可以打开“查看归档原始照片”仅用于对照。

人工规则：仅当判断两点属于同一根真实物理纱线的连续连接轨迹时，才确认 `reference`；即使两点之间存在遮挡也可标注，但必须独立于 3/1 斜纹的明暗条带推断。第二根用于间距校准，第三根独立验收，无法识别就保存 `DRAFT`，不猜测。经纬身份没物理依据时保留 `UNKNOWN`；这组照片没有同平面 5cm 标尺，不能填写根/cm 真值。

标注结束后按 Ctrl+C 停止本地服务，执行：

```powershell
python -m benchmark.manual_annotation audit
git add -- "datasets/annotations/drafts/U20261013_*.json"
git diff --cached --name-only
git commit -m "data: operator labels on six unmarked 2x fabric crops"
git push -u origin annotation/six-fabric-20261013
```

随后把分支或提交 SHA 发给我，我再对这组**已确认真实纱线连接轨迹的放大图点位**运行方向/几何一致性测试；可见纱段像素验收需要单独的可见性标注，不提前生成任何 AI 标注。

## 留意旧数据

之前旧版原图标注格式的 `U20261013_XX.json` 若留在本机，不可直接复用坐标；应先单独备份后重标放大图。服务端会校验新登记图像路径、哈希、大小并拒绝旧坐标。你本机之前保存的 `T001.json`、`D002.json`、`experiments/` 与本批次无关，**不要删除或顺带提交**。
