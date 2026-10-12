# 第一批公开织物照片：批量入库、审计与人工方向标注

本阶段兼容 V5 普通手机照片路线，不依赖透射图或 Camera Profile。冻结 V4/V5 不变。

## 注册与真值边界

- manifest.csv 只登记 GitHub 中确实存在的原始照片；来源目录会继续增加，尚未下载的来源记录不能算照片。
- ground_truth.csv 的方向、经纬密度、组织真值仍为空，状态为 NOT_EVALUATED。原始网页 weave_candidate 仅为弱标签，不能用于正式组织准确率。
- T009/T010 和 S001/S002 是各自公开来源关联的正反面，按保守方式归为同一个 fabric_id，不能拆到不同测试集合；不意味着照片已经配准或确证相同位置。物理面先保留 UNKNOWN。
- 全部图片暂置 DEV；后续需要独立布料样本再划分 VALIDATION 和 TEST，避免数据泄漏。
- 不具备与布料同一平面的 5×5cm 实体框和人工真值时，根/cm 不能作为正式可信计量。

## 本地运行命令

从仓库根目录运行：

    python -m pip install Pillow
    python -m benchmark.public_intake             # 预览
    python -m benchmark.public_intake --write     # 增量注册
    python -m benchmark.dataset --check-images
    python -m unittest discover -s benchmark/tests -v
    python -m benchmark.photo_audit --out experiments/public-photo-audit
    python -m benchmark.runner --out experiments/public-baseline

image_inventory.csv、annotation_queue.csv、summary.json、summary.md 将保存在 experiments/public-photo-audit 下。CI 运行时也会上传审计报告 Artifact。亮度、尺寸、灰度跨度只是粗筛标记，不能代替可靠的清晰度或物理尺度验收。

没有保存的人工确认 V5 JSON 或可靠 Ground Truth 时，Benchmark 返回 NOT_EVALUATED（退出码 3），不代表识别准确率为 0%，也不意味着算法已经通过。

## 优先人工核查队列

| ID | 选择理由 |
|---|---|
| P001 | 平纹真实纱线基准 |
| T001 | 牛仔斜纹图案干扰 |
| T002 | 彩色格纹与纱线方向区别 |
| T004 | 手机拍摄牛仔近景 |
| T005 | 破斜纹的假周期 |
| H001 | 人字纹及表面纹理误导 |
| S001 | 缎纹浮长造成可见纱段不连续 |
| X002 | 灯芯绒绒条不是单根经纬纱线 |
| U001 | 未知组织，应支持拒判 |

下一阶段对这些照片人工点击同一根真实纱线上的 P1/P2，再单独确认经纬身份，保存 V5 JSON 与叠加证据图。缺少足够证据的条目应保持未评估，不能凭来源名称猜经纬身份。

随后用同一纱线真值测试 0°、90°、180°、270° 的方向一致性和跨布料错误，之后再引入 V1.5 FFT、自相关、投影候选与冻结 V5 对比。正式经纬密度验证须等待有物理标定与人工根数真值的照片。
