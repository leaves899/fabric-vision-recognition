# V6：人工真实纱段约束的候选线位置与纱距修正

## 已发现的缺陷

用户在 T001、T004、T005 中发现：V5 方向角接近真实方向，但生成的候选中心线落在相邻纱线的间隙（见 Issue #7）。由于人工方向已经作为 V5 输入，旧版只看角度的评价会漏掉这一类根本性错误。

冻结 V4/V5 均未修改。修正只在实验工具中以独立 JSON 输出。

## 两种方案的真实实验对比

**方案 A：仅按第一条真实纱线平移候选网格。** T001 第一条从 18.77 px → 0.22 px，但是原来的第二条人工线从 25.64 px **恶化**至 36.60 px，因此不能上线为全面修复。

**方案 B：用两条不同的真实同向纱线同时校正相位和候选间距。** 第二条在 V6 中明确是“校准输入”，不再是独立验证数据。

| 图像 | V4 第一校准线距候选 | V4 第二校准线距候选 | V6 第一校准线距候选 | V6 第二校准线距候选 | 运行范围 |
|---|---:|---:|---:|---:|---|
| T001 | 18.77px | 25.64px | 0.13px | 0.61px | 完整原图 |
| T004 | 17.46px | 6.29px | 0.19px | 3.75px | 原始像素局部 ROI |
| T007 | 14.59px | 10.48px | 0.28px | 0.28px | 原始像素局部 ROI |
| P001 | 5.66px | 5.50px | 0.23px | 2.04px | 完整原图 |

T001 原始候选间距和两条校准线的间隔并不完全对应，V6 同时调整间距。**上表是同一训练/校准样本上被两端约束后的拟合残差，绝不是独立纱线检测准确率。** 图片上的中间纱线可能仍有漏检、重复、缝隙偏移。V4 的轨迹数仍是候选数。

## 使用

在仓库根目录安装依赖并从 V5 批量识别缓存结果起步：

```bash
python -m pip install -r demo/v5/requirements.txt
python -m pip install Pillow numpy

# 原图较小的样本
python -m benchmark.run_annotated_v5 --ids T001 --max-images 1
python -m benchmark.phase_offset_diagnostic --id T001 --result-dir experiments/v5-manual-round1/T001

# 高分辨率照片只在保留原始像素尺度的局部区域上测试，不能冒充整幅图
python -m benchmark.run_annotated_v5_roi --id T004 --out experiments/v5-hires-v6/T004
python -m benchmark.phase_offset_diagnostic --id T004 --result-dir experiments/v5-hires-v6/T004
```

每张样本输出：

- `position_overlay.jpg` — 修复前原始候选。
- `phase_anchored_candidate.jpg` — 单条锚点平移的实验候选；若拒判则不输出。
- `phase_and_pitch_anchored_candidate.jpg` — 两条同向纱线拟合相位与间距的 A 组候选；只在置信门通过时生成。
- `v6_candidate_tracks.json` — 带原图 SHA、ROI 原点、冻结 V4 hash、A/B 状态和坐标的可机器读取候选输出。
- `phase_diagnostic.json` — 拟合前后位置诊断、退出与拒判原因、独立第三根核查（若已提供）。

本地人工标注界面（无需重新填写已保存的两点）：

```bash
python -m benchmark.manual_annotation serve
```

浏览器： http://127.0.0.1:8765/tools/yarn_annotator/

V6 标注选项：
1. **A 第一根校准纱线**（原 V5 reference）。
2. **A 第二根校准纱线**（原 check_same，现在会参与距离和间距拟合）。
3. **A 第三根独立验收纱线**（holdout_same；不能参与训练/校准）。
4. **B 第一根正交纱线**（check_cross）。
5. **B 第二根正交纱线**（check_cross_second）。B 也需要两根纱线才能进行同样的间距与相位拟合。缺任一条时 B 维持未校正、未确认，不能假装识别成功。

## 必须保留的限制

- 第三根同向纱线没有加入校准。**目前 4 张已审核图片尚无第三根的独立位置真值**，因此真正的中心线定位准确率仍是 NOT_EVALUATED。
- 自动选取已有 V4 候选线对应的索引可能存在周期混叠/漏线，报告中的 `physical_interval_count_verified=false` 意味着没有人工核实两根校准纱线间究竟隔了几根真实纱线。若该计数错误，拟合后即使两条校准线对齐，其他行也可能错误。
- 经/纬真实身份仍未确认；未提供正交组双锚点就不能宣称 B 已修复。
- T005 原始标注仍是 DRAFT，且用户报告其落缝，必须先人工确认标注才能参与受控实验；不能自动篡改 DRAFT。
- 不根据表面斜纹、颜色条纹或 FFT 峰值直接假设物理纱线中心；不自动将候选线数转化为经密/纬密。没有同平面 5 cm × 5 cm 框和实测真值时，不验证根/cm。
- 因为 T004/T007 进行了 ROI 裁剪，局部结果不能推广到整幅相片。

## 何时认为修复真正成功？

先对 T001、T004、T005 和至少两张此前未参与该方案设计的牛仔布增加第三根独立真实纱线，评估未参与拟合的**位置误差占实际纱距的比例**，并逐根审核误检、漏检及是否绘入缝隙。若独立检查失败，应拒判或换方法，而不是按每张布料写专用偏移常数。Issue #7 在此之前保持开放。

代码分别位于 `benchmark/yarn_phase_anchor.py`、`benchmark/yarn_pitch_calibration.py`、`benchmark/phase_offset_diagnostic.py`。所有 CI 仍检查 V4/V5 冻结基线。
