# shibie 原生8000×6000 R/T双图研发与物理中心实验报告（2026-10-20）

> 实验分支：experiment/shibie-8k-capture-multiwindow；不合并 main。所有结果是有种子的**程序化物理织物仿真**，不是经过认证的实际50MP手机拍摄数据。

## 已执行的研发闭环

1. 已核实 codex/photo1.0、review、synthetic-physics、phase-guard、polarity-topology 五条历史分支及原版 shibie/engine。
2. 以 polarity-topology 实验分支独立派生新分支。原版 V0.6.3 的 pipeline/config 未改。
3. 编写 synthetic_capture_8k.py：8000×6000 直接物理坐标分块生成，唯一纱线ID+遮挡连续曲线+组织浮沉+宽度、R/T光学变化+50mm实体框+H/H_inv，输出全尺寸双图与随机种子、JSON真值、SHA256。uint8 memmap，96行分块，原始图作为Actions Artifact，不把大图提交Git。
4. 编写 multiwindow_pitch.py、physical_center_validation.py，基于相机图像找框角，9个高像素ROI，各自竞争周期/半周期/倍周期，候选两侧宽度和R/T/纵向一致性。设置LOW_CONFIDENCE时主动弃权。
5. 原版、ACF加强、相位保护与新多窗口在同一R/T原图上跑通；测试并视觉打开真实程序生成的原图、真值线及两版覆盖图。
6. 实测发现布料相对标定框独立旋转15°时的严重失败；新增 local_axis_rectification.py 和 run_local_axis_experiment.py 以图像自身ACF提出旋转方向候选。未合入正式pipeline。
7. 原版/ACF候选在六张真实手机照片及四张FabricNET上回归，并对五张确认PHYSICAL_YARN_REFERENCE照片在推理完成后执行间距/角度核验；仓库现有真实未标定R/T只做原版诊断。

## 物理合成与验收规格

像素视野 8000×6000；100×75mm；0.0125mm/px。固定工位50×50mm方框在未畸变坐标上4000×4000px。经纬真实纱距为800/密度_cm px；**纱线实体宽度独立计算**，width P10少于12px视为采集条件不合格。反射、透射从同一物理纱线、交织拓扑产生，绝不把检测结果作为标签来源。

真实程序执行的完整8K原图累计不少于六组（首组30/25平纹，以及下表5组，另有局部方向归一化专项实验两个完整8K输入）。背景光、高光/反相/混合吸收、R/T错位、轻度透视、几何扰动、旋转、斜纹假纹理和噪声均为程序化近似，不可称真实相机认证。

## 同图消融 A/B/C/D（原生8K平纹30/25）

| 配置 | 经向中心位置F1（代理） | 纬向中心位置F1（代理） | 说明 |
|---|---:|---:|---|
| A 原版V0.6.3 | 0.3039 | 0.9730 | 原版全局ROI投影 |
| B ACF加强版 | 0.3039 | 0.9730 | 无变化 |
| C 原暗纱相位保护 | 0.3039 | 0.0000 | 纬向错位急剧退化，应拒绝 |
| D 多窗口实体核验 | 0.9614 | 0.9594 | **仅局部9窗口投影** |

**不能**直接把 A/B/C 的全局F1与D的局部F1作为同口径提升。完整跨遮挡实体轨迹ID覆盖F1尚未实现。D在首组中27/32px，对应真实26.67/32px；9/9窗口各自通过局部物理实体审查。原版在首组未经调参、处于低置信状态，显著偏移。

独立实验测得原版8K在GitHub Ubuntu runner耗时约19–43秒、进程峰值约1.4–1.5GiB；D单独执行时约0.7–1.2秒、约542–587MiB（不同进程/任务，不能当作同一个端到端性能比较）；混合基线+新版的压力测试峰值RSS包含原版的内存驻留，不能当作新版独立RSS。RK3576 4GB+前端资源竞争**未验证**。

## 五组固定压力测试的新版表现

| 样本 | 真实密度 经/纬 | 新版纱距像素 经/纬 | 局部中心F1 经/纬（发布的线） | 两族P10≥12px | 结论 |
|---|---|---|---|---|---|
| 平纹亮暗反相 | 25/25 | 32/32 | .9663/.9627 | 是 | 局部较好 |
| 2/1斜纹 | 40/30 | 20/26 | 0/.7156 | 否（经纱11.461） | 经向弃权；纬向未达0.90 |
| 3/1斜纹混合光学 | 50/40 | 16/20 | 0/0 | 否（9.169/11.189） | 由于宽度/相位证据不足主动弃权；并非测得全是错线 |
| 缎纹亮暗反相 | 60/50 | 13/16 | 0/0 | 否（7.640/8.952） | 周期接近，中心不发布；采集门限不达标 |
| 平纹布料独立旋转15° | 30/25 | 26/30 | 0/0 | 是 | 框坐标正确但纱线未归一化；9窗口不能发布中心线 |

原版在独立旋转15°样本的方向误差为11.512°/13.502°；它的角度回归明显失败。首版D错误地依赖纱线与标定框方向近似对齐。图像自身ACF角度扫描专项实验（独立种子812613）在旋转15°场景输出16°、未旋转场景输出0°；旋转后局部中心线投影代理F1 .7509/.8319（8/9、9/9窗口通过），尚未达0.90。角度扫描仍属独立探索，不是已获真实照片验证的正式算法。**后续1°步长独立复测**（[Actions 39420281024](https://github.com/leaves899/fabric-vision-recognition/actions/runs/39420281024)）仍在15°布料场景返回16°、局部F1 .7509/.8319，未达到0.90；0°对照返回1°、F1 .9588/.9601，但该1°相对0°的得分优势很弱，不应视为确定旋转。缩小角度扫描步长未改善主要失败，因此不继续做无证据的步长搜索。

## 真实照片回归（原版/ACF；不是新版D真实精度）

| 人工确认的真实手机照片 | 原版平均角误差 | 原版平均纱距误差 | ACF表现 |
|---|---:|---:|---|
| U20261013_01 | 27.84° | 55.89% | 同原版 |
| U20261013_02（留出） | 8.71° | 231.40% | 同原版 |
| U20261013_03 | 9.31° | 125.37% | 同原版 |
| U20261013_05 | 11.89° | 75.29% | 同原版 |
| U20261013_06（留出） | 7.90° | 230.55% | 同原版 |

原版为兼容历史旧R/T接口，将真实手机单图**重复**为两输入，绝不可充当真实配准R/T验收；标尺未经独立认证，误差只代表相对像素间距几何核验。人工两根标记之间的 intervals 按多纱距真实间隔处理，不默认为相邻。第六张真实手机照片未有同等级可用于该表的已确认间距真值。

仓库已有真正R/T图像经原版获得LOW_CONFIDENCE，中心线数量33/9，但没有真实完整物理ID和独立尺度，不能声称正确或给出真实密度。新版D要求8K固定框，尚无符合要求的真实R/T黄金标注；**真实照片提升未验证**，也不能据原版未变化断言新版无退化。

## 已证明、被否定、待攻克

- **已证实（仅合成）**：物理尺度分块合成、50mm标定框像素检测、9窗候选真实纱距、局部相位弃权、全分辨率内存可控实验、图像自身旋转候选扫描。
- **已否定**：简单ACF加强可以消除半纱距相位；未经独立认证直接开暗纱相位保护就能稳定识别；仅靠固定框轴就能应对任意布料旋转。
- **未达到**：不同织物/扰动下局部中心F1均≥0.90、真实物理曲线跨遮挡1对1身份连续性核验、真正高分辨率真实R/T的非退化、RK3576真机测试、前端共存内存、完整端到端新版pipeline自动切换、真实采集认证。
- **部署决策**：只保留试验分支与证据，新算法不能直接启用默认，更不能合入main。

## 路径与可审计性

源码：
- shibie/synthetic_capture_8k.py
- shibie/engine/multiwindow_pitch.py
- shibie/engine/physical_center_validation.py
- shibie/engine/local_axis_rectification.py
- shibie/run_native8k_smoke.py
- shibie/run_native8k_multiwindow.py
- shibie/run_native8k_case.py
- shibie/run_local_axis_experiment.py
- shibie/run_8k_ablation.py
- shibie/run_8k_real_regression.py

分支内 small metrics + preview：
- experiments/shibie-8k-capture-multiwindow/smoke/ablation_4way.json
- experiments/shibie-8k-capture-multiwindow/smoke/multiwindow_metrics.json
- experiments/shibie-8k-capture-multiwindow/smoke/multiwindow_center_evidence_preview.jpg
- experiments/shibie-8k-capture-multiwindow/smoke/physical_truth_overlay_crop.jpg
- experiments/shibie-8k-capture-multiwindow/smoke/baseline_overlay_crop.jpg
- experiments/shibie-8k-capture-multiwindow/smoke/ablation_visual_compare.jpg

GitHub Actions 真正运行与完整大图（下载Artifacts）：
- 首轮原版8K smoke：https://github.com/leaves899/fabric-vision-recognition/actions/runs/39416065894
- 同输入 A/B/C/D：https://github.com/leaves899/fabric-vision-recognition/actions/runs/39418067645
- 五组固定8K压力：https://github.com/leaves899/fabric-vision-recognition/actions/runs/39419205151
- 真实照片人工标注回归：https://github.com/leaves899/fabric-vision-recognition/actions/runs/39418580505
- 独立纱线相对固定框旋转专项：https://github.com/leaves899/fabric-vision-recognition/actions/runs/39420048832

32项现有 shibie 单元测试在 smoke CI 中通过，仍不足以代替物理识别验收。

备注：为避免重复任务并发提交相同truth/metrics造成Git rebase冲突，已启用workflow concurrency。高分辨率真实原图以Actions Artifact保存，Artifact会按设定保留期过期；源码配置+种子+Git Commit+SHA256可复现。
