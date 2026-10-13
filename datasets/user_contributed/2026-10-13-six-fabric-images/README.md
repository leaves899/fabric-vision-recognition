# 六张手机织物照片：原图 + 无标记 2× 放大图

这组照片 **只接受仓库原有的人工作业工具** `tools/yarn_annotator/` 产生的标注。之前由助手生成的 15 个候选纱段框、组织猜测和斜纹标记 **已撤回，不作为标签或 Ground Truth**。

## 交付与现状

- `images/U20261013_01.jpg` 至 `_06.jpg`：原始相机照片，字节不改。
- `zoom_unmarked/U20261013_01_center_2x.jpg` 至 `_06_center_2x.jpg`：只取原图中心区域做 2 倍像素放大，无线条、文字、点位、掩膜或推断。
- `image_provenance.json`：图片原始 SHA-256、放大图 SHA-256、中心裁剪区域及倍率，不是人工纱线标注。
- **目前 GitHub 草稿 PR #12 仅包含导入脚本和本说明，尚未上传这 12 张 JPG 二进制文件**。必须运行本地导入+git push 才能让 GitHub 存在照片。

## 第 1 阶段：上传未经标记的原图与放大图

1. 从 ChatGPT 下载 **six_fabric_originals_and_unmarked_zoom.zip**，默认放在 Windows Downloads。
2. 在本地 Git 仓库根目录，切到 `data/20261013-six-fabric-visual-drafts` 分支（有未提交工作时不要自动清理）。
3. 运行：

```powershell
$zip = Get-ChildItem "$HOME\Downloads" -Filter "six_fabric_originals_and_unmarked_zoom*.zip" -File |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $zip) { throw "请先下载新版无标记 ZIP" }
python scripts/import_six_fabric_for_manual_annotation.py --zip "$($zip.FullName)"
python scripts/verify_six_fabric_samples.py
python -m benchmark.dataset --check-images
```

导入器只解包白名单文件，严格核对 6 张原始 SHA-256 和 6 张放大图 SHA-256，增量登记 `datasets/manifest.csv`、`datasets/ground_truth.csv` 的空白记录；重复运行不覆盖已有人工标注。对原图进行人工标注，不直接在放大副本上点击以免混淆坐标。

通过后提交（不要误加本地已有的 `T001.json` 或 `experiments/`）：

```powershell
git add -- datasets/user_contributed/2026-10-13-six-fabric-images/images/
git add -- datasets/user_contributed/2026-10-13-six-fabric-images/zoom_unmarked/
git add -- datasets/user_contributed/2026-10-13-six-fabric-images/image_provenance.json
git add -- datasets/manifest.csv datasets/ground_truth.csv
git diff --cached --stat
git commit -m "data: add six original photos and clean 2x zooms"
git push origin data/20261013-six-fabric-visual-drafts
```

## 第 2 阶段：使用 GitHub 仓库已有的人工标注工具

在仓库根目录运行：

```powershell
python -m pip install Pillow numpy
python -m benchmark.manual_annotation serve
```

浏览器打开 **http://127.0.0.1:8765/tools/yarn_annotator/**，选择 `U20261013_01` 至 `_06`。如果参考点没有证据证明位于**同一根真实纱线**，就保持 `DRAFT`，不要勾选 `OPERATOR_REVIEWED`。斜向织纹、颜色线段和周期暗点不得自动转化为物理纱线编号。

- 放大图只作旁边的视觉核对，真正的点击坐标须落在 **原始 JPG** 上。
- `reference_family` 默认 `UNKNOWN`，经纬身份无外部证据不得擅自填写。
- 没有同平面 5cm×5cm 实体框，`ground_truth.csv` 内的密度与计量真值都必须留空。
- 原始图正反面是否成对未核实，不在采集元数据中擅自配对。
- 只有操作者确认并点击保存，才会产生 `datasets/annotations/drafts/U20261013_XX.json`。

## 第 3 阶段：人工标注完成后再上传 JSON

```powershell
python -m benchmark.manual_annotation audit
git add -- "datasets/annotations/drafts/U20261013_*.json"
git diff --cached --stat
git commit -m "data: add operator-confirmed six fabric annotations"
git push origin data/20261013-six-fabric-visual-drafts
```

PR #12 保持草稿，直到源图已上传且标注确由人工完成。**不应把开发者、助手或程序的草稿点位伪装成人工确认真值。**

## 数据隔离

真实布料同一性、经纬物理身份、组织规格、经/纬密度等未确认。`PHONE_UNKNOWN_LIGHTING` 记录表示用户上传的手机照片，不等同 Wikimedia 公开照片。图片版权归原提供者；若仓库未来公开，请先确认可共享授权。
