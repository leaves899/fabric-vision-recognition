# 此前用户照片的报告路线测试输入

- `reflection.png`、`transmission.png`：来自 2026-10-16 已有同位置配准与转正记录的 1080×1080 ROI。哈希、原图哈希及几何过程保存在 `provenance.json`；本次没有重新估计或覆盖历史配准。
- `phone_blue_white.jpg`：此前实验登记的原始蓝白手机照片，SHA-256 `43657923971720220414447a236daeaf7bf0b27c5362e52ed032f5c6474f63bc`。
- 另 6 张旧手机照片直接使用 `datasets/user_contributed/2026-10-13-six-fabric-images/images/`，未重复复制或更改。

样本目录是用户私有测试资料，不增加对外发布授权。历史 256 px/cm 在新系统中作为未确认的候选尺度保存；具体输入参数和全部照片哈希见 `fabric_measurement/sample_catalog.json`。
