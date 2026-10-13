# 织物图像识别 / Fabric Vision Recognition

> **项目状态：V5 Web Demo 基线已导入；Fabric Measurement Engine V1.5 仍为待验证技术方案。**
>
> 建议仓库属性：**Private**。项目包含真实算法源码、样图、训练掩膜与项目特性资料，请勿未经许可公开。

## 项目目标

围绕普通手机织物照片与后续标准化采集，完成既定**十项识别/辅助确认参数**：

1. 经向方向与角度
2. 纬向方向与角度
3. 经纱排列状态
4. 纬纱排列状态
5. 经纱粗细候选等级
6. 纬纱粗细候选等级
7. 组织结构候选（平纹、2/1 与 3/1 左右斜、破斜纹、缎纹、变化组织及待确认）
8. 经密（根/cm）
9. 纬密（根/cm）
10. 表面纹理与色系

**独立系统配套字段**：经纬密度比＝经密÷纬密。花度是人工录入项；Ne/tex 可以作为未来参考建议，但不替代十项参数。

## 当前版本

- **V4 冻结算法**：`demo/v5/v4_frozen/frozen/reoptimize_v4_quadgrid.py`，不在一般功能 PR 中修改。
- **V5 可运行 Demo**：`demo/v5/`，人工在同一根真实纱线上点击两点取向，必要时确认同平面的 **5×5 cm 实体框**四角；V4 产生双族候选线。方向角、经纬身份、物理计数必须按各自来源管理。
- **V1.5 建议方案**：`docs/references/Fabric_Measurement_Engine_建设落地建议_V1.5.md`。标准反射/透射双图、Camera Profile、FFT/投影与计量门禁目前**不是已验证上线能力**。

### 启动 V5

```bash
cd demo/v5
python -m venv .venv
# 激活虚拟环境后
python -m pip install -r requirements.txt
python -m uvicorn server:app --host 127.0.0.1 --port 8008
```

浏览器打开 `http://127.0.0.1:8008`。Windows 可在 `demo/v5/` 内双击 `启动Demo.bat`。项目开发推荐 Python 3.12，具体以实际机器测试为准。

```bash
cd demo/v5
python -m pytest -q tests
```

该命令仅验证已有测试覆盖的功能；**自动测试通过不等于独立面料上的真实经纬识别准确率已通过验收。**

## 本地 Git 纱线标注（研究分支新增）

[本地标注工具使用说明](tools/yarn_annotator/README.md) · Windows 仓库根目录双击 `启动本地标注.bat`，打开 `http://127.0.0.1:8765/tools/yarn_annotator/`。

页面现在包含两种**彼此隔离**的人工标注：既有 `PHYSICAL_YARN_REFERENCE`（同一根真实纱线的推断延伸轨迹），以及新加的局部图像证据框选、短线、同根/不同根关系。局部判读会在本地写入 `datasets/physical_evidence_labels/manual_image_reviews/<sample_id>.json`，可用 `git add / commit / push` 上传，不会覆盖旧 A1/A2/A3。后者不是独立物理实物真值。

**目前此工具更新仅位于 `research/physical-yarn-trajectory-3stage-20261013` 分支（PR #16），尚未合并 main。** 请先切换到该分支再 `git pull`；详见工具 README 中的 PowerShell 完整命令。

## 目录

```text
demo/v5/                  已有 V5 Demo，包含冻结 V4、样图与测试
docs/requirements/        十项业务目标及状态语义
docs/architecture/        V4/V5 与 V1.5 技术衔接设计
docs/references/          原始技术/特性文档，仅供追溯
docs/versions/            版本基线与发布约定
.github/workflows/         自动化测试
```

## 版本控制

- `main`：经验证可回溯的集成基线；重大修改先开分支与 Pull Request。
- `feature/*`：新功能；`experiment/*`：计量候选与对比试验；`fix/*`：缺陷修复。
- 保留冻结 V4 源码 SHA-256：`dde5d84193a3f3d02bb55ad72a8c2b9f2a640034563ed936736ad46808b8dad1`。
- 初始 Git 标签建议为 `demo-v5.0.0-baseline`；**标签仅表示源码基线，不代表十项准确率已验收**。

详见 `docs/versions/VERSIONING.md` 和 `docs/architecture/INTEGRATION_ROADMAP.md`。

## 重要限制

V4/V5 输出的红/绿候选线是候选轨迹，**不等于已确认的真实物理纱线**。未确认的中心线数量不能作为正式经密/纬密。传统 FFT、Gabor、结构张量等方向检测可能被斜纹带误导。V5 的人工真实纱线两点参考不得被未经验证的自动取向替代。

## 公开织物照片测试集（66 张）

已新增 [datasets/public_samples/](datasets/public_samples/) 公开织物实物样本，其中牛仔布专项目录共（21），平纹及其他纤维（19）、旧斜纹及花呢（12）、人字纹（3）、缎纹（4）、复杂纹理（6）、待确认（1）。包括手机近景、普通摄影、真实织物扫描及少量馆藏照片；馆藏照片不可当作纱线逐根计数基准。 本轮额外收集了 3 位摄影者的牛仔布近景和 3 份 Poly Haven 不同布样的处理色彩图；后者只归辅助集，不纳入手机图像识别准确率。

- [浏览全部原始照片](datasets/public_samples/images/) · [逐张来源与许可](datasets/public_samples/sources.json) · [牛仔专用子集](datasets/denim_only/README.md) · [测试范围与真值边界](datasets/public_samples/README.md) · [同步状态](datasets/public_samples/sync_status.json)
- 新增的部分照片含毫米/厘米参考刻度；但**没有任何一张具备项目标准的 5×5 cm 同平面实体标定框**，不能据此宣称经纬密度验收完成。
- 所有第三方照片版权依照其原始来源许可，仓库其他文件的 LICENSE 不自动适用于这些照片。
