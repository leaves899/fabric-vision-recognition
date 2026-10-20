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


## 2026-10-20 后续研发：亚像素相位 + 计分器修复（已真实运行）

### 执行内容与代码（未触碰 V0.6.3 默认 pipeline）
- `shibie/engine/subpixel_physical_phase.py`：不取整局部纱距的ACF局部拟合、连续浮点相位折叠、R/T双侧边界及纵向一致性候选审查。
- `shibie/engine/midsection_anchor.py`：额外中截面相位重锚定的独立试验。
- `shibie/engine/phase_conflict_audit.py`：按测得实体宽度建立两种中心候选的冲突警报；在本轮中**漏报**严重下降个例，不得声称安全可靠。
- `shibie/evaluate_center_matching.py`：**已证实的关键评估修复**。不能先最小化无门限L1距离、再计算门内F1；那会错误地把周期纱线配到旁边整根。现在首先在阈值内最大化唯一正确配对数量，再做微小的距离次级排序。
- `shibie/replay_corrected_center_matching.py` 和单元测试：使用冻结的旧/新检测坐标，推理完成后重建合成真值并公平重评分。

三种固定场景每个重新运行了原生8000×6000 R/T双图：15°布料相对框独立旋转30/25、0°对照30/25、反相光照25/25。第一轮与第二轮共六次完整原生R/T生成；重复同一随机种子，**不能当作六个独立留出样本**。

### 修正后公允比较：同窗口、同图、同物理真值和门限
| 场景 | 纱线族 | 原整数算法F1 | 新浮点算法F1 | 中段重锚定F1 |
|---|---|---:|---:|---:|
| 15°旋转30/25 | 经向 | .8144 | **.8890** | .8860 |
| 15°旋转30/25 | 纬向 | **.8449** | .8360 | .8360 |
| 0°对照30/25 | 经向 | .9587 | .9587 | .9587 |
| 0°对照30/25 | 纬向 | .9601 | **.9639** | .9639 |
| 25/25光学反相 | 经向 | .9476 | .9476 | .9476 |
| 25/25光学反相 | 纬向 | .9543 | .9543 | .9543 |

**重要撤销旧结论**：旧评分曾将15°旋转角落窗口浮点纬向F1错误算为0.0800，实际上按门内最大唯一匹配是**0.8000**（整数版0.8462）。这是评分错误放大，并非物理中心必然整体差一个纱距。该窗口的绝对最近物理真值中位距离仅0.0184纱距，但旧评估器施加的匈牙利L1配对中位距离竟达到1.0047纱距；详见 `metric-sensitivity/REPORT.md`。

在3个场景共54个局部窗口上，基于旧/新中心候选的宽度尺度冲突审计只发出0次警报，无法捕捉此前错误评分判定的一个大跌分窗口；该路线本轮未验证，**不推荐启用**。中段重新锚定亦未在本轮合理评分下优于浮点版，不予推广。

45个 `shibie` 单元测试在完成的[新一对一评分工作流](https://github.com/leaves899/fabric-vision-recognition/actions/runs/39439539261)中通过。
- [三场景第一轮原生8K像素级对照](https://github.com/leaves899/fabric-vision-recognition/actions/runs/39436283053)
- [三场景第二轮同种子三方对照](https://github.com/leaves899/fabric-vision-recognition/actions/runs/39437637934)
- [F1计分阈值审计](https://github.com/leaves899/fabric-vision-recognition/actions/runs/39438732029)
- [纠正后的原生8K F1完整结果](https://github.com/leaves899/fabric-vision-recognition/blob/experiment/shibie-8k-capture-multiwindow/experiments/shibie-8k-capture-multiwindow/corrected-matching/REPORT.md)
- [新旧算法与真实纱线标记的程序生成叠图](https://github.com/leaves899/fabric-vision-recognition/tree/experiment/shibie-8k-capture-multiwindow/experiments/shibie-8k-capture-multiwindow/phase-conflicts)

当前适用范围**仅为合成的局部单截面中心线位置匹配**，不是完整物理纱线跨遮挡身份F1。没有新的符合工位条件的真实8K R/T黄金标注，故**真实样本非退化仍未验证；不得合并main或部署RK3576**。下一步需独立补齐可见轨迹覆盖、连续性及真实R/T证据，不能继续沿用原始错误计分器。


## 2026-10-20 进一步研发：多截线物理ID关联与强弯曲反证

**分支继续隔离，未修改默认shibie/engine/pipeline.py，未合并main。** 所有试验均是真正程序原生8000×6000 R/T双图（直接物理坐标生成，不是小图插值），真实相机工位认证**不存在**。这一轮按4组开发/留出、2组独立强弯曲及3组逐根跟踪复测共运行9组原生8K生成；其中已有两个固定失败场景重复用于回归，不能把9组说成9个独立样本。

### 研发代码（核心模块真实执行）
- `shibie/engine/local_yarn_tracks.py`：同窗7个独立截线，以R/T相位、宽度和极性生成**整组公共相位曲线候选**。
- `shibie/evaluate_yarn_track_identity.py`：将每条候选与合成时已分配的同一根`physical_yarn_id`作多截面匹配，使用门限内最大一对一匹配而非有漏洞的后阈值Hungarian。
- `shibie/engine/individual_yarn_tracelets.py`：每根纱线独立根据相邻孔隙/实体的R/T光学证据更新中心位置，对邻近不同候选执行非重叠排他，不读取合成纱线ID或组织先验。
- `shibie/evaluate_strict_yarn_identity.py`：修正身份验收漏洞。宽松版只需60%采样点持续对应同根；严格版至少85%且任何已确认跳至别根ID都否决该候选。
- `shibie/run_8k_yarn_identity.py`、`shibie/run_8k_individual_comparison.py`、`shibie/replay_strict_identity.py`：同R/T真值隔离推理、多算法同图对比、冻结输出后严格重评分。

### 4组原生8K开发/新留出（局部同ID宽松轨迹F1，不能和此前单截面F1比较）
| 场景 | 方向 | 浮点直线 | 公共相位7截线 |
|---|---|---:|---:|
| 平纹布相对标定框15°（开发） | 经/纬 | .9645/.9452 | **.9735/.9643** |
| 平纹0°（开发） | 经/纬 | .9616/.9639 | **.9706/.9749** |
| 2/1斜纹−10°混合光学（新留出） | 经/纬 | .7562/.9526 | **.7686/.9603** |
| 平纹19°光学反相（新留出） | 经/纬 | .9677/.9567 | .9677/**.9643** |

上述结果提示曲线化有改善，但并不具备强弯曲的覆盖。本轮随后在**之前未用过的新种子**构造0.28纱距弯曲强度的2/1、3/1高压样本，一开始使用冻结公共相位算法，发现严重崩溃：

| 强弯曲反证 | 方向 | 浮点直线 | 公共相位7截线 |
|---|---|---:|---:|
| 2/1混合光学，wave_fraction=.28 | 经/纬 | .2518/.3915 | .2496/.3916 |
| 3/1光学反相，wave_fraction=.28 | 经/纬 | .4824/.6116 | .4822/.6247 |

原因尚未完全证明，但整组纱线共享一个相位偏移不能表达**逐根独立弯曲**，与错误ID连续性的观测一致。改为逐根R/T物理中心短轨迹后再次运行（已见过失败场景，所以**现在是回归，不再是新留出**）：

| 场景 | 方向 | 公共相位7截线F1 | 逐根独立R/T F1（宽松） | 逐根独立R/T F1（严格） |
|---|---|---:|---:|---:|
| 2/1高弯曲 | 经/纬 | .2496/.3916 | **.4474/.5446** | .3829/.2688 |
| 3/1高弯曲 | 经/纬 | .4822/.6247 | **.8232/.7698** | .6276/.3040 |
| 2/1中等弯曲（新种子留出） | 经/纬 | **.9853/.9679** | .9673/.9605 | .9673/.9605 |

**严格身份F1并未同口径计算旧公共相位7截线，因此严格列不得用于新旧相对提升宣称。** 严格评估重建物理真值并逐窗口验证冻结宽松分数完全复现后才计算；在高弯曲下出现大量ID候选关联风险，说明简单放宽连续性门限会掩盖错误。

### CI、性能与视觉产物
- [原生8K 4场景多截线实测](https://github.com/leaves899/fabric-vision-recognition/actions/runs/39443643770)（其中算法运行均成功，最初汇总脚本有路径错误；已在[独立修复汇总任务](https://github.com/leaves899/fabric-vision-recognition/actions/runs/39444280148)成功归档）。
- [2组高曲率原生8K独立压力测试](https://github.com/leaves899/fabric-vision-recognition/actions/runs/39444581720)与[程序生成的失败叠图](https://github.com/leaves899/fabric-vision-recognition/tree/experiment/shibie-8k-capture-multiwindow/experiments/shibie-8k-capture-multiwindow/curvature-failures)。
- [逐根R/T光学追踪3场景真实运行及归档](https://github.com/leaves899/fabric-vision-recognition/actions/runs/39445943439)；[对应多窗具体失败表与叠图](https://github.com/leaves899/fabric-vision-recognition/tree/experiment/shibie-8k-capture-multiwindow/experiments/shibie-8k-capture-multiwindow/individual-holdout)。
- [严格同ID评价59项单元测试与后验重评分](https://github.com/leaves899/fabric-vision-recognition/actions/runs/39446998739)；[严格身份验收报告](https://github.com/leaves899/fabric-vision-recognition/blob/experiment/shibie-8k-capture-multiwindow/experiments/shibie-8k-capture-multiwindow/strict-identity/REPORT.md)。
- 逐根子算法与图像加载的单独进程时间约1.5至3.0秒、峰值RSS约541至587MiB（GitHub Ubuntu Runner，**不是**RK3576端到端耗时）。

以上6宫格叠图均为算法根据真实程序图像/轨迹结果绘制并保存；本会话无法通过容器直接进行像素级人工图像审阅，故只能确认**已实际生成和保存**，不能把其称作已完成人工视觉验收。已提供可直接打开的GitHub图片链接供独立审阅。

### 合并结论
- **已实证**：真正8K多截面同ID评估、正确门限内一对一物理身份匹配、逐根R/T证据对部分强弯曲样本显著优于整组公共相位；自动化结果可复现，59测试通过。
- **被否定**：仅靠公共相位曲线就能泛化高曲率；宽松60%同ID F1可以当作严格可靠的身份指标；逐根追踪可无条件替代既有算法（中等弯曲新留出有退化）。
- **仍未证明**：对不同实物纱线跨遮挡区域恢复唯一物理ID、以真实8K相机R/T完成非退化验收、设备RK3576 4GB+前端共存。
- **执行决策**：继续保留独立研发分支；不将未达标识别模块写入生产默认pipeline，更不合并main。
