# Fabric Measurement PoC V0.6.3

## 当前定位
牛仔布经纬密度比视觉识别可行性验证 PoC。

## 标准输入
- 正面图（必需）
- 透视图（必需）
- mm/px X
- mm/px Y
- 经向提示

## 核心技术路线
Gate 2 → ROI/归一化 → Structure Tensor → Steerable Filter Bank → Ridge Detection → Centerline Linking/Cleaning → Warp/Weft Mapping → Centerline Count + Median Center Spacing → Confidence。

## 启动
安装 requirements.txt 后运行：

```bash
python app.py
```

也可使用项目中的 `启动网页.bat`。
