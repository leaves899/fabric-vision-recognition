# 六张手机织物照片：在无标记 2× 放大图上人工标注

本目录已进入 `main`：6 张原始 JPG、6 张中心裁剪后放大 2 倍的无标记 JPG 和哈希/裁剪来源记录。**现在直接在放大后的 JPG 上用现有 GitHub 仓库人工标注器点击并保存**，不是在原图上作点位，不使用助手原先的猜测或标记。

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

人工规则：只有两点确实位于同一根真实可见纱线时，才确认 `reference`；绝不能把 3/1 斜纹的明暗斜条带等价于真实单根纱线。第二根用于间距校准，第三根独立验收，无法识别就保存 `DRAFT`，不猜测。经纬身份没物理依据时保留 `UNKNOWN`；这组照片没有同平面 5cm 标尺，不能填写根/cm 真值。

标注结束后按 Ctrl+C 停止本地服务，执行：

```powershell
python -m benchmark.manual_annotation audit
git add -- "datasets/annotations/drafts/U20261013_*.json"
git diff --cached --name-only
git commit -m "data: operator labels on six unmarked 2x fabric crops"
git push -u origin annotation/six-fabric-20261013
```

随后把分支或提交 SHA 发给我，我再对这组**真正人工确认的放大图点位**运行 V5 回归与基于独立纱段的检验；不提前生成任何 AI 标注。

## 留意旧数据

之前旧版原图标注格式的 `U20261013_XX.json` 若留在本机，不可直接复用坐标；应先单独备份后重标放大图。服务端会校验新登记图像路径、哈希、大小并拒绝旧坐标。你本机之前保存的 `T001.json`、`D002.json`、`experiments/` 与本批次无关，**不要删除或顺带提交**。
