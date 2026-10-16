# 独立织物图像识别模块 · Weave V5

本目录作为 `fabric-vision-recognition` 的**独立图像识别模块**保存，不修改原有 `demo/v5`、`benchmark`、`pure10` 等研究代码。

## 功能

- `color_plain.py`：基于 **Lab 颜色聚类 + 颜色家族排布 + 半周期相位差** 提取平纹（1/1）候选；颜色类别与周期从输入图像检测，**不使用已知组织真值**。
- `float_segmentation_v3.py`：对高亮纱线浮点做实例分割，每个可见浮点一个实例，使用分水岭排他归属而非固定网格。
- `weave_topology_v4.py`：根据 V3 可见浮点几何估计二维重复晶格和斜纹组织候选，并输出模型矩阵与观测证据。
- `run_photo_weave_v5.py`：支持 1 或 3 个独立 ROI 的总入口；双颜色平纹分支不成立时回退 V3/V4。
- `__main__.py`：支持从仓库根目录以 Python 模块运行。

## 安装及运行

在仓库根目录执行（推荐 Python 3.10+）：

```powershell
python -m pip install -r modules/image_recognition/weave_v5/requirements.txt
python -m modules.image_recognition.weave_v5 --image "C:\\data\\fabric.png" --out "C:\\data\\result_v5" --rois 3
```

也可切换目录并直接运行：

```powershell
cd modules/image_recognition/weave_v5
python run_photo_weave_v5.py --image "C:\\data\\fabric.png" --out "C:\\data\\result_v5" --rois 3
```

在其他 Python 代码中调用：

```python
from modules.image_recognition.weave_v5 import run

result = run("fabric.png", "result_v5", rois=3)
print(result["summary"]["organization_candidate"])
```

输入尺寸两边需至少 **640 像素**，允许 PNG/JPG，ROI 暂为 640×640；3 ROI 分别从左/中/右取样并投票。输出根目录为 `result.json`，子目录包含彩色平纹结构证据图或 V3 分割、V4 拟合及其 CSV/JSON 文件。

## 输出语义

`organization_candidate` 是**组织类别候选**，例如 `plain_1_1`、`3/1` 或 `null`。结果包含：

- `physical_0_1_verified: false`：尚未由两组物理纱线在每个交织处的遮挡关系独立确定真实 0/1；
- `S_Z_direction: unresolved`：当前尚无独立确认的布料正面/经纬身份用于 S/Z 定向；
- `status: unresolved`：当缺少足够结构证据时拒判，不自动猜类别。

**注意**：双颜色行交替与半周期错位是平纹候选的支持证据，不等同于已验证的经纬沉浮组织矩阵。

## 已完成的实物实验（2026-10-16）

- 已确认真值的红/灰 `f_fl_x124_y0` 平纹样本：3 个不同 ROI 均输出 `plain_1_1` 候选，横向重复约 39 px、两组相位差约 18–19 px。
- 之前五张亮浮点照片：彩色平纹分支均未误触发；V4 已保存的几何识别结果对 `photo_01/03/04/05` 为 `3/1` 候选，`photo_02` 仍可能拒判。
- 独立 V5 测试包中有 9 项快速回归通过；**同一布料三个 ROI 不等于三块不同布料的盲测**。

为了不把大体积手机照片复制到 Git 仓库，本目录**只包含可运行源码与轻量测试**，真实照片放在仓库已有数据区或由用户通过 `--image` 传入。本模块可继续作为更通用经纬交织拓扑研发的隔离基线。

## 测试

无需图片数据的基础测试（仓库根目录）：

```powershell
python -m unittest modules.image_recognition.weave_v5.test_standalone_smoke -v
```

包含重复周期、相位差、ROI 划分、候选投票和拒判检查。独立真实照片回归需要之前的测试数据包，可用上述命令提供对应照片重新运行。

## 部署说明

当前为研究版 Python/NumPy/OpenCV/SciPy/Pillow 实现，**未做 RK3576 设备/NPU 性能认证**。V4 在某些织物上的浮点晶格拟合耗时较长，不应在未实测前宣称满足设备实时需求。

## 2026-10-16 V5.1 修复：3/1 被误识别为 2/1

**问题**：旧 V4 几何评分直接使用浮点中心跨行平移 `v` 在周期向量 `u` 上的投影，把**真实组织相位**和**纱线自身倾斜造成的漂移**混在一起，导致带倾角的 3/1 样本误判为 2/1。

**修复**：从已分割的浮点区域测得长轴角度 `theta`，按实测几何分别计算：

```python
raw = dot(u, v) / dot(u, u)
perpendicular = det(u, v) / dot(u, u)
desheared = raw - tan(theta - atan2(u_y, u_x)) * perpendicular
```

`score_models` 中的周期评分现在使用 `desheared`，浮点长度评分仍独立保留。旧 `raw` 和扣除的位移像素量同时写入报告以便审查。倾斜差异超过 60° 时跳过校正，以免数值发散。不加入特定照片或 3/1 的硬编码判断规则。

**实际复测**（两张配准照片；已知真实组织 3/1 仅作为验收标签）：

| 正面 ROI | 旧候选 | 新候选 | 原始相位 | 去倾斜相位 | 状态 |
|---|---|---|---:|---:|---|
| 左 | 2/1 | 3/1 | .2935 | .2426 | 通过候选门槛 |
| 中 | 2/1 | 3/1 | .2966 | .2444 | 通过候选门槛 |
| 右 | 2/1 | 3/1 | .3005 | .2380 | 通过候选门槛 |
| 反面左/中/右 | 拒判 | 仍拒判 | - | - | 保留拒判 |

旧 5 张照片回归：`photo_01/03/04/05` 仍通过 3/1 候选，`photo_02` 仍因晶格覆盖不足拒判。红灰已确认平纹样本仍识别为 `plain_1_1`。有合成 2/1、3/1、2/2 不同旋转与仿射偏移的独立测试。上述尚不是跨真实不同组织的盲测准确率，更不代表反面 0/1 物理浮沉已被自动恢复。

运行回归单测：

```powershell
python -m unittest modules.image_recognition.weave_v5.test_phase_deshear -v
```

诊断报告新增三个字段：`raw_phase_advance`、`desheared_phase_advance`、`float_axis_shear_removed_px`。修复前后的分类差异来自从照片实例测量到的几何角度，**不依赖 `photo_05` 或配准照片的真实组织标签**。
