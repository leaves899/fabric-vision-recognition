# 本地 Git 标注工具（Windows）

本工具只在自己的电脑 `127.0.0.1:8765` 运行，保存实际 JSON 文件到本地 Git 仓库。**页面不会自动提交、推送或更改远端代码。**

## 第一次运行

在 PowerShell 中进入你已有的 Git 仓库根目录（示例路径请改成你本地的实际目录）：

```powershell
cd E:\Internship_2026\fabric-vision-recognition
git status --short
git fetch origin
git switch --track origin/research/physical-yarn-trajectory-3stage-20261013
git pull --ff-only
py -3 -m pip install Pillow
```

如果 `git switch --track` 提示本地分支已存在，改用：

```powershell
git switch research/physical-yarn-trajectory-3stage-20261013
git pull --ff-only
```

**重要：** 当前新标注工具位于上面的研究分支/PR #16，暂未合并 `main`；如果仍停留在旧 `main`，直接 `git pull origin main` 不会得到新页面。切换分支前先 `git status`，若已有未提交的人工标注，请先提交或暂存，避免丢失。

## 打开页面

Windows：在仓库根目录双击 `启动本地标注.bat`，它会启动本地 Python 服务并打开浏览器。

或者手工执行：

```powershell
py -3 -m benchmark.manual_annotation serve --port 8765 --open
```

若 Windows 没有 `py` 命令，可改用 `python -m benchmark.manual_annotation serve --port 8765 --open`。

网址：`http://127.0.0.1:8765/tools/yarn_annotator/`。不要用资源管理器 `file://` 双击 `index.html`，否则无法自动保存文件。

## 如何标注

页面顶部有两种模式：

1. **已有纱线参考线**：保留 A1=`reference`、A2=`check_same`、A3=`holdout_same`、B组真实物理纱线的两点延伸参考。允许中间遮挡；原坐标不能自动转为像素可见 GT。仅在确实要修正它们时点击相应保存。
2. **新增局部证据标注**：选择样本和类别，在照片上**按住鼠标拖动**框选局部可见纱线候选、斜纹带、间隙、色带、阴影、遮挡或不确定区域；`可见短线` 工具依次点击两个端点，仅标局部可见结构；`两区域关系` 工具依次点击两个**已画好的区域**，标成同根、不同根、未知。点击 **保存局部证据 JSON 到本地 Git 仓库**。保存反馈会显示实际相对路径。

本地审核标签不能单独证明物理纱线身份：不确定时选 `UNCERTAIN`；同根/不同根关系也是人工基于手机照片的判断。不会生成 `physical_identity_probability` 或称作独立物理标签。原 `datasets/physical_evidence_labels/local_patches.json` 留给未来外部物理证据，不在页面中修改。

局部标注自动写入：

```text
datasets/physical_evidence_labels/manual_image_reviews/U20261013_03.json
```

与原有 `datasets/annotations/drafts/U20261013_03.json` 完全隔离。U样本使用 **2×放大图的原生像素坐标**，保存时校验原图 SHA-256 和坐标范围；即使浏览器缩放到200%，标注仍保持正确坐标。

## 保存后上传到 GitHub

关闭或保留浏览器，在**另一个** PowerShell 终端、同一仓库根目录执行：

```powershell
git status --short
git add -- datasets/physical_evidence_labels/manual_image_reviews/
# 如果本次确实修改了原有 A1/A2/A3 的两点参考，再单独执行下一行
# git add -- datasets/annotations/drafts/
git diff --cached --stat
git commit -m "data: annotate local physical yarn evidence"
git push origin research/physical-yarn-trajectory-3stage-20261013
```

如果 `git commit` 提示 `nothing to commit`，检查是否点击了**保存局部证据 JSON**按钮、是否处于正确目录。**不建议 `git add -A`**，避免上传无关临时文件或未审核样图。

其他模型/协作者更新本分支后，下一次标注前可以先执行：

```powershell
git status --short
git pull --ff-only origin research/physical-yarn-trajectory-3stage-20261013
```

若本地仍有未提交修改，先提交自己的 JSON；如遇 `push rejected (fetch first)`，先尝试 `git pull --rebase origin research/physical-yarn-trajectory-3stage-20261013`，若发生同一 JSON 冲突不要 `git push --force`，应逐项合并人工标注后再推送。

## 本地校验

```powershell
py -3 -m benchmark.manual_annotation audit
py -3 -m unittest benchmark.tests.test_local_image_review -v
node --check tools/yarn_annotator/app.js
node --check tools/yarn_annotator/local_review.js
```

**注意**：标注状态 `OPERATOR_REVIEWED` 仅表示你审核过自己的手机图像标注，不表示有独立显微/实物验证真值。新建局部标注 JSON 被 Git 正常跟踪后，GitHub PR #16 会随你的 push 自动更新。
