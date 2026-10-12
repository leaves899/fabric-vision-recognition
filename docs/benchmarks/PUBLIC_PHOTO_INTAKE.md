# Step 0.1 — 已收集公开织物照片的增量登记

## 已核实的仓库状态（2026-10-12 快照）

- `datasets/public_samples/sources.json`：**27 条**来源元数据，其中 8 张图片已经实际存在于 `datasets/public_samples/images/`；其余 19 条目前只有来源记录（提交时再重新检查）。
- 实际入库：`P001`–`P003` 共 3 张平纹来源候选；`T001`–`T004` 共 4 张斜纹来源候选；`U001` 共 1 张未知组织来源图片。
- `manifest.csv`：上述 8 张照片登记为 `DEV` 视觉研发数据。公开图片的正反面身份不可确认，记 `face=UNKNOWN`；拍摄模式记 `PUBLIC_UNKNOWN`。
- `ground_truth.csv`：对应 8 行仅用于预留人工标注，`review_status=NOT_EVALUATED`。经纬角、经纬密度、组织真值均为空，不填入来源页的弱组织候选。
- 没有确认过与布同平面的 5 cm×5 cm 标定方框，没有独立经纬根数真值，也没有可靠的经纬身份；故不开展真实经密/纬密误差评价。
- 以上数量指 **8 张已下载图片**，不是 8 块有可核实配对关系的样布；同布正反面配对尚未证实。

## 建议第一轮实际任务

1. 做入库、来源许可、重复图片/破损、未知标签的质量检查，保证可复现输入。
2. 对开发集做**人工可见纱段/方向标注**（可先选 P001、T001、T002、T004）；标注真实纱线 P1/P2，不沿斜纹纹理和颜色条纹点选。
3. 用 V5 的人工两点参考 + 冻结 V4 输出候选线三联图，记录错向、错峰、重数、遗漏及不能识别情况；没有人工参考点不能直接批量调用 V5。
4. 有 5 cm 方框与真实根数的**新采集样布**再进入经密、纬密 Benchmark。公开图片原则上不做物理密度验收。
5. 后续照片到来时运行 `python -m benchmark.public_intake --write`，再运行 `python -m benchmark.dataset --check-images`，提交新的 `manifest.csv` 与 `ground_truth.csv`，不重排已冻结的样布划分。

## 不允许夸大的结论

- 当前 8 张公开样本只能先验证数据流程和视觉诊断，不代表跨织物定向或密度算法准确率。
- 公开来源“平纹/斜纹/2/2”只作为弱标签，必须有独立核验才能进入组织分类真值。
- 目前 V5 读取真实用户点击的 P1/P2；没有 P1/P2 不得构造假人工坐标或使用纹理方向代替。
- `NOT_EVALUATED` 是当前正确状态；不是零误差，也不是算法已经失败。

## 自动化检测

```bash
python -m benchmark.dataset --check-images
python -m benchmark.public_intake
python -m unittest discover -s benchmark/tests -v
python -m benchmark.runner --out experiments/public-dev
```

最后一条在无有效人工真值及 V5 JSON 时返回状态 `NOT_EVALUATED`，退出码 `3` 是预期语义。GitHub Actions 只执行数据校验及单元测试，不误把“缺少真实精度”当作 CI 失败。
