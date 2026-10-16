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
