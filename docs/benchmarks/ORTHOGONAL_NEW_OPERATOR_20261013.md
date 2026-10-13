# 单张牛仔布第二组纱线：最新人工标注独立核查（2026-10-13）

研究分支：\`research/orthogonal-cross-evidence-20261013\`；基线 main \`e1b2193\`。

## 必须遵守的证据边界

- 照片输入为 \`datasets/user_contributed/2026-10-13-six-fabric-images/zoom_unmarked/\` 中的无标记 2× 中心裁剪图。坐标属于 \`ZOOM_2X_NATIVE_PIXELS\`。
- 现有人工审核文件为 01、02、03、05、06；04 尚无已审标注，自动跳过。
- 第二方向检测器**仅使用照片及人工 \`reference\` 第一组方向**，不读取 cross 两条段的坐标用于预测。
- \`check_cross\` 和 \`check_cross_second\` 独立作为第二方向核查，\`check_same\`、\`holdout_same\` 用于第一方向核查。cross 两条本身也没有完整物理根数真值。
- 通过交织图案的长链不能证明同根纱线，输出状态只允许 \`IMAGE_SUPPORTED_DIRECTION_ONLY_NOT_YARN_PROOF\` 或 \`ABSTAIN_*\`。
- \`same_family_intervals\` 和 \`cross_family_intervals\` 用于换算人工两条独立纱线的**像素间距候选**，不是图像自动算出的根数、也不是独立测试准确率。
- 当前无同平面5cm标尺，不输出根/cm；放大2倍不提升原始物理分辨率。
- 方向角为无向轴0~180°，90°旋转复测与抽样负对照都要通过，失败视为拒识。

## 复现实验

\`\`\`powershell
git fetch origin
git switch research/orthogonal-cross-evidence-20261013
python -m pip install -r demo/v5/requirements.txt
python -m benchmark.manual_annotation audit
python -m unittest benchmark.tests.test_orthogonal_evidence -v
python -m benchmark.orthogonal_evidence --out experiments/orthogonal-new-reviewed
\`\`\`

结果：\`summary.json\` 包含每张的 direction、两条人工第二组参考的独立角度误差、90°重投影漂移、点/链与间隙支持比例；每张双联图左侧显示图像候选连线、右侧显示人工参考和独立核查线段。无需重建完整纱线网格。

**判定规则：本实验不把近正交约束导致的低角度误差计为自动识别成功。必须再验证真实纱线身份和未参与任何训练的实物计数真值。**
