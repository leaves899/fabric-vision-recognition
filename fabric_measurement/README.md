# 织物图像识别工作台

按用户提供的《牛仔布视觉识别技术可行性报告》实现可运行的本地图像分析系统，版本 `report-system-1.1`。系统已完成上传到结果保存的完整流程；当前真实照片仍存在方向偏差、中心线缺失和组织交点不足，不能用于未经复核的物理计量。

## 启动与操作

在仓库根目录双击 `启动图像识别系统.bat`，浏览器打开 `http://127.0.0.1:8018`。首次缺少依赖时，启动脚本在本仓库 `.venv-measurement` 安装所需依赖；已有兼容 Python 时直接启动。

也可以手动运行：

```powershell
python -m pip install -r fabric_measurement/requirements.txt
python -m uvicorn fabric_measurement.server:app --host 127.0.0.1 --port 8018
```

1. 在“此前提供的照片”选择归档样本，或上传一张反射图。标准路线可再上传同一位置、同一面的透射图；反面反射图不能当作透射图。
2. 在照片上拖动选取清晰、平整区域，或输入 X/Y/宽/高。原生 ROI 每边 128–1200 px，不为凑尺寸放大或缩小照片。默认单图中心 640 px；归档双图使用已有 1080 px 校正 ROI。
3. 若知道经向，可填最终分析坐标中的角度；只作 A/B 身份映射。0°向右，90°向下，角度按 180° 等价。不知道时留空，不会自动给两族命名经/纬。
4. 若有最终 ROI 的像素物理尺度，输入 `mm_per_px` 并确认与织物同平面。只有输入数值、没有勾选确认时，物理换算仅保留在 JSON 的候选字段。
5. 按“开始图像识别”，查看综合质量、原因和逐项指标。可切换各证据图，打开逐条轨迹查看器，下载 JSON 或整套 ZIP。历史记录在重启后保留。

选择新照片会清除上一张的尺度、身份、透视设置及可见结果，避免误用。历史结果始终显示其输入文件名。

## 与报告的对应关系

| 步骤 | 代码 | 已实现内容 |
|---|---|---|
| 1–3 | `geometry.py` | Laplacian、Tenengrad、直方图、ROI、单应性校正、ECC 配准与 9 个局部相关检查 |
| 4–5 | `centerlines.py`、`primitives.py` | 多尺度 Structure Tensor、独立方向峰、可旋转高斯导数滤波、局部光照归一化 |
| 6–7 | 同上 | 法向强度极值、Ridge、距离/方向连接、间断与跨度清洗、亮暗与角度竞争 |
| 8 | `centerlines.py` | 经向提示仅用于两族身份映射，不生成方向、间距或中心线 |
| 9–10 | `measurements.py`、`primitives.py` | 有观测支持的截线计数、中位中心间距、物理换算及经纬比候选 |
| 11 | `measurements.py` | 法向灰度剖面、双侧梯度边缘、Pitch 约束、MAD 剔除、P10/P50/P90 |
| 12 | `structure.py` | 多尺度 Gabor、Canny/Hough、张量支持、线段长度加权角度与离散度 |
| 13 | `structure.py` | 有观测支持的交点、浮沉矩阵、浮长、1/1、2/1、3/1 模板与未知单元 |
| 14 | `pipeline.py` | Gate 3、核心低可信原因、辅助警告、可解码证据及哈希索引 |
| 纱支参考 | `structure.py`、`service.py` | 有来源的经验规则匹配，`tex = 590.5 / Ne`，始终 `reference_only` |
| 应用层 | `server.py`、`web/` | FastAPI、中文界面、验证与限尺寸、持久结果、下载和样本目录 |

`PROVENANCE.json` 记录复用的相邻项目 `report_reproduction` 与中心线基础函数的原始哈希。源码已复制到本模块并使用相对导入；运行时不依赖相邻项目，也不导入冻结 V4、FCN 权重或旧实验目录。原项目文件未改动。

本实现参数来自此前独立复现和本次明确的工程选择，报告没有提供原始代码和完整阈值，不能宣称复现 W088/W114/W054 的数字。Camera Profile 目前记录元数据，不自动补造未提供的相机光学标定。

## 重要输出定义

- `families[].tracks` 是候选路径，保留全部检测与剔除原因；`retained_tracks` 是片段数，不等于真实纱线根数。
- 图中实线连接相邻采样；虚线表示跨缺失采样的推断。也不表示实线的每一个像素都通过人工可见纱线核验。
- 计数法使用 `(N-1)/(末中心-首中心)` 排除边界不完整间距；间距法使用 `1/median(spacing)`。两者共享中心线，具有相关误差。
- 已确认尺度换算为 `条/px × 10/mm_per_px` 得到候选根/cm；未确认尺度时正式字段为 `null`，另有 `candidate_*` 字段明确区分。
- 宽度是两侧梯度边缘间的图像表观宽度，不是纤维直径或实验室纱支。返回有效剖面数量与逐剖面边缘坐标。
- 斜纹 `right_rising` 表示图像中的 `/`，`left_rising` 表示 `\`；实物左右斜还依赖经向摆放、正反面和镜像状态。角度为图像向右零轴，UI 同时显示锐角与原轴角。
- 组织只输出有条件的模板候选，矩阵未知格为 `-1`，不会填成某种组织；尚未证明候选行列是完整且连续的物理根序。
- `Gate 3 PASS` 只指内部质量条件通过，`Evidence PASS` 只指证据成功生成和解码。`physical_accuracy` 始终保持 `NOT_EVALUATED`，不以内部一致性替代独立实物真值。

## 透视与尺度

高级输入示例格式如下。坐标必须由真实图片给出，四角按左上、右上、右下、左下；双图分别指定。设置透视时页面原图 ROI 不传入，可在 JSON 中指定校正后的 `roi`。

```json
{
  "front_corners": [[20,20],[600,30],[610,610],[15,600]],
  "back_corners": [[22,18],[602,32],[608,608],[17,602]],
  "target_size": [640,640],
  "roi": [64,64,512,512]
}
```

`mm_per_px` 必须对应校正后的图像网格；ROI 裁剪只平移坐标，不改变尺度。系统拒绝反向角点次序、超出图片的点、非法 ROI 和过大的目标图像。任意拉伸得到的像素不能自动视为具有统一物理尺度。

## Ne/tex 规则

报告未公开经验分档表，默认没有有效规则。用户可提供包含 `width_mm`、`density_per_cm`、`Ne` 三个递增正值区间及 `source` 来源的 JSON 数组；可选 `identity` 为 `warp_candidate` 或 `weft_candidate`。仅有一个规则匹配时输出参考区间，重叠匹配时拒绝。区间换算 `tex` 时按倒序端点计算。不自动使用报告三个示例拟合经验表。

## API 与命令行

- `POST /api/analyze`：multipart 字段 `reflection`、可选 `transmission`、`options` JSON。完整契约见 `/docs` 的接口及 `service.AnalysisOptions`。
- `GET /api/samples`：8 个预置案例；图片只从登记的固定清单读取并检查哈希。
- `GET /api/runs` / `/api/runs/{id}`：完成的本机结果。
- `GET /api/runs/{id}/download`：证据 ZIP。

上传支持 JPEG/PNG/WEBP/BMP/TIFF，每文件至多 20 MB、3200 万像素、最长边 10000 px。EXIF 转正后的坐标用于 ROI；配对尺寸不符时先提供分别的几何校正。计算在后台工作线程中执行，同一服务按顺序分析。仅绑定 `127.0.0.1`。

```powershell
python -m fabric_measurement --reflection path/to/reflection.png --transmission path/to/transmission.png --options path/to/options.json --output experiments/new-run
```

输出目录必须尚不存在，每次保存 `result.json`、`run_summary.json`、`review.html`、原/配准 ROI、方向场、中心线、宽度、斜纹和浮沉矩阵。单图不生成假的透射图片。Web 结果位于本模块的 `runs/`，不自动提交到 Git。

## 实际验证

```powershell
python -m pytest fabric_measurement/tests -q
python -X utf8 -m fabric_measurement.batch --output experiments/report-system-new --publish-history
```

本次 61 项自动检查通过，含 0/90/180/270° 合成方向与间距、单斜纹负对照、宽度解析值、配准、组织模板、尺寸/标定输入、API 错误处理、持久结果及 ZIP。它们验证实现和状态约束，不等于真实布料识别精度。

真实测试包含 7 张单图、1 组双图，共 9 张此前照片。全部执行完成并复读校验 14 步、JSON、PNG 哈希与解码；8 个 Gate 3 均为低可信，组织候选均为空。可比较的操作员双方向与本次输出偏差约 9.6°–29.2°；第 6 张手机照片未形成双方向。双图配准通过，中心线与间距仍不稳定，浮沉矩阵仅 3 个已知交点。

详见 `../experiments/report-system-20261017-final/results.md` 和 `index.html`。原始照片、人工标注与冻结 V4/V5 未修改。
