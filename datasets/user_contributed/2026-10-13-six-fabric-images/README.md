# 手机织物六图：真实局部纱段 vs 斜纹纹理（视觉草稿）

这里保存 2026-10-13 用户提供的六张织物手机照片的**机器可读视觉预标注**。样图不是明确确认的物理纱线 Ground Truth。

## 当前落库状态（请勿误读）

- [visual_drafts.json](visual_drafts.json)：已经由实际上传图片的视觉检查生成，6 张、15 个局部浅色浮纱候选框以及 3 张蓝色照片的斜纹纹理排除区域。
- **原始 6 张 JPG 和审查叠加图尚未通过 GitHub 连接传到仓库**，当前分支不是完整影像数据集。聊天附件与 GitHub 分属不同存储，GitHub 文件 API 不支持传递本地 `/mnt/data` 路径。
- 通过聊天中提供的完整 ZIP 获取 `images/`、`annotations/`、`review/`、`manifest.csv`。把 ZIP 内最外层的 `2026-10-13-six-fabric-images` 文件夹解压到仓库 `datasets/user_contributed/` 下，保留这个 GitHub 原有的 `visual_drafts.json`。

### Windows PowerShell（仓库根目录）

```powershell
Expand-Archive -LiteralPath "six_fabric_visual_annotation_bundle.zip" -DestinationPath "datasets/user_contributed/" -Force
python scripts/verify_six_fabric_samples.py --require-images
git add datasets/user_contributed/2026-10-13-six-fabric-images/
git commit -m "data: add six user-provided fabric originals and visual review"
git push
```

不要把图片无授权地同步到公共仓库。本仓库当前为私有仓库，但将来如修改可见性，必须单独确认图片授权。

## 视觉审查准则

- 图 01–03：只勾选 **局部可见浅色纱段候选框**，每一框只代表短区域，不输出穿越交织遮挡的物理纱线 ID；深色孔隙周期不能直接当中心线。
- 图 04–06：**斜向表面明暗条带为组织形成的纹理，不是单根物理纱线轨迹**；留作算法困难负样本，不能让二维 FFT、结构张量、投影峰值等自动角度无人工复核就当作纱向真值。
- 原图 01–03 与 04–06 可暂按外观分组，但未经用户确认不能断言同一块布、正反面对应或对应拍摄位置。
- 无已知同平面 5cm×5cm 标定框；物理密度（根/cm）、物理经纬身份、组织 3/1 与 2/1 左右斜类别均留空。
- `VISUAL_DRAFT_NOT_PHYSICAL_GT` 不应在准确率统计脚本中视为 `CONFIRMED`，禁止在任何验证集直接变相伪造真值。

**标注坐标系：原始文件，左上角为 (0,0)，x 向右、y 向下；所有 box 用 [x1,y1,x2,y2] 表示。**
