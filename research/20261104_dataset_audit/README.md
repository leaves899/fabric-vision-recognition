# 2026-11-04 · 全量图片经纬密度 / 组织候选盲测入口

## 阶段与性质

本分支从 \`experiment/fabricnet-horizontal-twice-20261021\` 隔离创建。新增的是 **全 ZIP 批量入口与不隐瞒失败的审计/验收框架**，没有修改已冻结的 V0.6.3 Ridge/Centerline/Density 主链，也没有宣称这批照片全部识别成功。

历史 FabricNET 130 张基线：双次横向检测的经/纬密度同时 ≤10% 相对误差仅 59/130；**不是本次布料数据集.zip 的成绩**。V5 返回的是组织 *candidate*，不是已经验证的物理交织 0/1 矩阵。任何未测出/拒判/没有 GT 的结果都不能计入正确率分母中的“正确”。

## 快速检查

仓库根目录运行：

\`\`\`bash
python -m pip install numpy opencv-python-headless
python research/20261104_dataset_audit/run_dataset.py \
  --archive "/data/布料数据集.zip" \
  --out "/data/fabric_audit" \
  --inventory-only
\`\`\`

输出 \`all_images.csv\`、\`summary.json\`，列出每个 ZIP 内图像（包含损坏、不能解码图片的失败记录），不推断纱线数量或组织。

## 实际识别（需要正确标定）

本项目原有 Density 主链使用物理密度范围筛选峰值，**不能将未知照片的 mm/px 随意填成假定数值**。

单照片、图像基本横竖对齐时：

\`\`\`bash
python -m pip install -r shibie/requirements.txt
python -m pip install -r modules/image_recognition/weave_v5/requirements.txt
python research/20261104_dataset_audit/run_dataset.py \
  --archive "/data/布料数据集.zip" --out "/data/fabric_audit" \
  --mm-x <经实际标定的X轴mm/px> --mm-y <经实际标定的Y轴mm/px> \
  --assume-axes-aligned --rois 3
\`\`\`

单照片模式仅复用 FabricNET 验证的“0° 横向 + 旋转90° 后再次横向”兼容性算法，不把同一张照片伪装成两张独立的真实反射/透射图片。没有可靠物理标定时仍可单独运行 V5 的组织候选（不加 \`--mm-x/--mm-y\`），密度保留 \`NOT_RUN_MISSING_PHYSICAL_CALIBRATION\`。

真实配准的反射 / 透射双图，提供外部 \`pairs.csv\`，精确逐对指定（没有自动依赖文件名猜测）：

\`\`\`csv
sample_id,reflection,transmission
sample_001,images/001_FL.jpg,images/001_BL.jpg
\`\`\`

\`\`\`bash
python research/20261104_dataset_audit/run_dataset.py \
  --archive "/data/布料数据集.zip" --out "/data/fabric_audit" \
  --pairs-csv /data/pairs.csv \
  --mm-x <实际标定值> --mm-y <实际标定值> --rois 3
\`\`\`

含图片源 SHA256、每图经密/纬密、已跟踪候选线数量、纱距、双路径分歧、组织候选、状态、异常原因、真实叠线/组织中间结果。**检测到的中心线条数不是已验证的独立完整物理纱线数**；不能直接当做真值。

## 可选盲测标注（不参与算法决策）

外部 \`truth.csv\` 以 ZIP 内完整路径为唯一键：

\`\`\`csv
image,warp_density_per_cm,weft_density_per_cm,weave
images/001_FL.jpg,38,30,3/1
\`\`\`

加 \`--truth-csv /data/truth.csv\`，只有推理结束之后才逐张关联真值，给出真实经纬误差和**完全相同名称**的组织候选是否匹配。没有任何分类粗细映射（例如 \`twill\` 不会偷偷按 \`3/1\` 判对）。缺失标签、失败结果、候选空值不计为已验证正确。真值只用于统计，不可用于角度、周期、尺度或组织候选选择。

## 已知未完成（不可将运行成功等同于识别成功）

1. **当前新增的是审计入口而非提高准确率的模型更新**，真实《布料数据集.zip》尚未跑通，不能给出每张图的数值。
2. 对任意角度、卷曲、倾斜织物，单照片固定横向算法不具备普适正确性。
3. 密度数值与完整独立纱线数量不同，只有人工逐根 GT 可以证实中心线有没有“同根重复 / 漏根 / 浮纹误判”。
4. V5 组织为候选，物理交织 0/1、S/Z 与组织周期尚未完成整套数据集盲测。
5. 目标须分项评分：逐根线质量、经纬密度误差、组织类别、组织周期/方向、拒判率；分组织和拍摄条件记录。不能依据已知真值调单图参数后再报训练集 100%。

## 代码测试

\`\`\`bash
python -m unittest discover -s research/20261104_dataset_audit \
  -p 'test_run_dataset.py' -v
\`\`\`

CI 只核查：ZIP 全量发现、防路径穿越、坏图不被隐身、标注不影响候选、缺失标注不计正确、R/T 输入路径约束。**CI 通过不代表物理识别算法通过。**
