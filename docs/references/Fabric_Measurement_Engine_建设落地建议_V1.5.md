# Fabric Measurement Engine 建设落地建议 V1.5

> 适用范围：牛仔布结构视觉计量  
> 当前阶段：一期 / Fabric Measurement Engine 落地  
> 本版边界：不建设 Gate 1 手机/工位认证；一期不建设数据驱动的 Yarn Count Estimator，但允许输出“Ne/tex 粗略参考建议”；不引入本地视觉模型  
> 核心目标：把“标准化图片进来后，稳定量出经密、纬密、经纬密度比、经纬纱表观宽度和斜纹特征”做成可测试、可版本化、可在 RK3576 上运行的确定性计量引擎。本文同时明确测量原理、图片范围与门禁，以及为什么采用反射/透射双光源和多尺度处理。

---

## 1. 建设目标

### 1.1 总体产品定位：牛仔面料智能视觉分析系统

从完整产品视角看，本项目不是单独建设一个“经纬密度计算程序”，而是逐步建设一套 **牛仔面料智能视觉分析系统**。

系统希望解决的核心业务问题是：

> **拿到一块牛仔样布后，通过标准化视觉采集，把原本依赖人工观察、人工数纱和经验描述的结构特征转换成可计算、可比较、可追溯的数字面料特征。**

系统总体可以分成五个层次：

```text
① 标准化视觉采集
固定手机 / 固定工位 / 反射光 / 透射背光
        ↓
② Fabric Measurement Engine
经纬方向、周期、中心线、密度、表观宽度、斜纹/组织
        ↓
③ 样本与数据中心
样布、图片、Measurement JSON、Evidence、Ground Truth
        ↓
④ GPT 智能分析层
结果解释、异常说明、多位置综合、样布对比、报告
        ↓
⑤ 数字面料卡
形成可以保存、检索、比较和后续建模的数字化样布资产
```

后续在积累足够“视觉特征 + 真实纱支标签”后，还可以增加第二阶段的 Yarn Count Estimator，对 Ne/tex 做数据驱动的正式推断。

因此，Fabric Measurement Engine 是整个系统中的**基础计量核心**：上游负责把图片采好，下游负责把结果用起来，而 Engine 负责把图片稳定地转换成结构化、可验证的数字量。

### 1.2 到底要识别和输出什么

当前系统聚焦牛仔布的**结构视觉分析**。为了避免“识别”“计量”“推断”混在一起，正式指标建议分成四类。

| 指标类别 | 正式指标 | 结果性质 | V1状态 |
|---|---|---|---|
| 结构计量 | 经密 | 直接视觉计量 | 核心输出 |
| 结构计量 | 纬密 | 直接视觉计量 | 核心输出 |
| 结构计量 | 经纬密度比 | 计算结果 | 核心输出 |
| 粗细计量 | 经纱表观宽度 P10/P50/P90 | 直接视觉计量 + 统计 | 核心输出 |
| 粗细计量 | 纬纱表观宽度 P10/P50/P90 | 直接视觉计量 + 统计 | 核心输出 |
| 结构识别 | 左斜/右斜 | 视觉规则/识别结果 | 核心输出 |
| 结构计量 | 斜纹角度 | 几何测量 | 核心输出 |
| 组织识别 | 2/1、3/1 等组织 | 视觉识别结果 | 在核心计量稳定后逐步建设 |
| 辅助判断 | Ne/tex 粗略参考 | 经验规则驱动的视觉推断建议 | V1可输出，但不作精确结果 |
| 可信度 | Gate 2 / Gate 3 状态、失败原因、证据图 | 质量与证据结果 | 核心输出 |

其中，客户口头所说的“经纬纱比例”，在本系统中应正式定义为：

> **经纬密度比 = 经密 ÷ 纬密。**

不要继续使用含义不明确的“经纬纱比例”作为正式字段。

### 1.3 数字面料卡的目标形态

Fabric Measurement Engine 的结果最终不是孤立的几个数字，而应进入一张可持续积累的 **数字面料卡（Digital Fabric Card）**。

建议数字面料卡至少包含：

```text
Sample ID / 样布基本信息
        ↓
样布总览图（系统级可选，用于档案与人工查看）
        ↓
计量图引用
  - 正面反射图
  - 透射图
  - 条件补拍图（如有）
        ↓
Camera Profile / Engine Version / Algorithm Profile
        ↓
经密 / 纬密 / 经纬密度比
        ↓
经纱表观宽度 P10/P50/P90
纬纱表观宽度 P10/P50/P90
        ↓
斜纹方向 / 斜纹角度 / 组织结果
        ↓
Ne/tex 粗略参考建议（如适用）
        ↓
Gate 状态 / Confidence / Evidence
```

数字面料卡的意义在于把“这块布看起来怎么样”转换成可以：

- 保存；
- 检索；
- 横向比较；
- P1/P2/P3 多区域统计；
- 后续建立相似面料检索；
- 后续训练 Yarn Count Estimator；
- 支撑 GPT 生成面料分析说明。

### 1.4 本次建设在总体系统中的位置

本次文档不建设完整的“牛仔面料智能视觉分析系统”，而是集中建设其中最关键、也最需要先验证的 **Fabric Measurement Engine**。

本次边界可以用下面的位置关系理解：

```text
【上游：本次不建设】
固定手机采集 / Gate 1 / Camera Profile
              ↓
=========================================
【本次建设重点】
Fabric Measurement Engine
Gate 2 → 几何归一化 → 方向/周期/中心线
→ 经密/纬密 → 表观宽度 → 斜纹/组织 → Gate 3
→ Measurement JSON / Evidence
=========================================
              ↓
【系统级承接】
样本与数据中心 / 数字面料卡 / GPT 分析
              ↓
【后续阶段】
数据驱动 Yarn Count Estimator
```

因此，本次建设成功的判断标准不是“界面是否完整”或“GPT是否能说出一段漂亮的面料描述”，而是：

> **在标准图片输入条件下，Engine 能否稳定、可重复、可解释地量出结构指标，并对不能可靠计量的样本明确拒绝或降级。**

### 1.5 Fabric Measurement Engine V1.0 的直接目标

Fabric Measurement Engine V1.0 的目标不是“识别牛仔布是什么”，而是完成一条可重复、可追溯的视觉计量链路：

```text
标准反射图 + 标准透射图 + Camera Profile
                  ↓
             Gate 2
                  ↓
          几何归一化 / 配准
                  ↓
             多尺度处理
                  ↓
      经纬方向 / 周期 / 中心线
                  ↓
             经密 / 纬密
                  ↓
          经/纬表观宽度分布
                  ↓
           斜纹方向 / 角度
                  ↓
             Gate 3
                  ↓
        Measurement JSON + 证据图
```

V1.0 首要目标是“量准、量稳”，而不是一次性覆盖所有复杂面料。

### 1.5.1 整个系统的测量原理

Fabric Measurement Engine 的基本思想不是让 AI “看图猜参数”，而是把牛仔布表面的周期性结构转换为可以重复计算的几何量。

一块机织牛仔布可以抽象成两组近似正交的周期结构：

```text
经纱方向：│ │ │ │ │ │ │
纬纱方向：─ ─ ─ ─ ─ ─ ─

两组结构交织后形成：
┼─┼─┼─┼─┼
│ │ │ │ │
┼─┼─┼─┼─┼
│ │ │ │ │
```

对于视觉计量，真正需要获得的是：

1. 两组纱线的主方向；
2. 相邻纱线中心之间的周期/间距；
3. 每根纱线的中心位置；
4. 每根纱线在图像中的表观宽度；
5. 图像像素与实际毫米之间的比例关系。

一旦 Camera Profile 已经给出 `mm/px`，像素空间中的距离就可以转换为真实物理距离。

例如：

```text
mm_per_px = 0.0125 mm/px
经纱中心间距 = 20 px

实际中心间距：
20 × 0.0125 = 0.25 mm

经密：
10 mm ÷ 0.25 mm = 40 ends/cm
```

因此，经密、纬密并不是由 GPT 给出的“识别答案”，而是由图像中的周期和中心线通过确定性公式计算出来的。

表观纱线宽度同理。例如：

```text
纱线左边缘：x = 120.4 px
纱线右边缘：x = 143.1 px

像素宽度：
143.1 - 120.4 = 22.7 px

如果 mm_per_px = 0.0125：

表观宽度：
22.7 × 0.0125 = 0.284 mm
```

### 1.6 为什么必须同时使用反射图和透射图

两类图片解决的是不同问题，不能简单理解为“同一个位置多拍一张”。

#### 正面反射图

光源位于布料上方，光线照射布面后反射进入摄像头。

```text
        固定摄像头
            ↓

       ↘         ↙
       漫射反射光

          牛仔布
```

反射图更接近人眼看到的布面，主要保留：

- 纱线表面边界；
- 斜纹；
- 浮长；
- 毛羽；
- 竹节；
- 表面宽度形态。

因此它主要用于：

> **表观纱线宽度、斜纹、组织和表面结构。**

#### 透射图

光源位于牛仔布下方，光线穿过纱线间隙进入摄像头。

```text
        固定摄像头
            ↓
          牛仔布
            ↑
          扩散板
            ↑
        均匀背光板
```

透射图会强化“纱线”和“空隙”的差异：

```text
亮区域 ≈ 纱线间空隙
暗区域 ≈ 纱线主体
```

因此它更适合：

- 经纬方向；
- 周期检测；
- 中心线；
- 经密；
- 纬密；
- 孔隙和结构周期。

两者组合的核心逻辑是：

> **透射图负责回答“纱线在哪里、间距是多少”；反射图负责回答“纱线表面看起来有多宽、纹理是什么”。**

这样比单独依赖一张反射图更稳健。

### 1.7 为什么一期不直接使用本地视觉模型

一期目标是计量，而不是语义分类。

对于：

- 周期；
- 中心间距；
- px/mm 换算；
- 边缘距离；
- P10/P50/P90；

这些问题，确定性 CV/信号处理算法的优点是：

- 结果可重复；
- 中间过程可解释；
- 可输出证据；
- 易于建立精度门禁；
- 同一算法版本对同一输入必然给出相同结果。

因此一期优先采用：

```text
OpenCV + NumPy + SciPy + 自研几何/统计代码
```

而不是优先训练 CNN / ViT / YOLO / SAM。

如果后续传统视觉在特殊竹节、毛羽或复杂组织上出现稳定瓶颈，再单独评估 NPU 视觉模型，而不是一开始为了使用 RK3576 NPU 而引入模型。

### 1.8 从图片到结果的完整原理过程

整个 Engine 可以理解为“先把图片变成可测量坐标，再把纹理变成周期和边界，最后把像素量转换成物理量”。

```text
【上游标准化采集】
反射图 + 透射图 + Camera Profile
              ↓
【Gate 2】
判断图片是否具备计量条件
              ↓
【几何归一化】
畸变校正 / 透视校正 / 固定毫米尺度
              ↓
【反射-透射配准】
保证两类图片对应同一块物理区域
              ↓
【多尺度图像】
低分辨率找方向与周期
高分辨率只做局部精测
              ↓
【方向检测】
识别两组近似正交的纱线轴
              ↓
【周期粗估】
FFT / Autocorrelation / Gabor
得到相邻纱线的大致周期
              ↓
【中心线精定位】
Projection + Peak
得到每根有效纱线中心
              ↓
【经密 / 纬密】
中心间距 px × mm/px
或
有效长度内中心线计数
              ↓
【高分辨率局部测宽】
中心线映射到反射图
沿法向寻找左右边缘
              ↓
【表观宽度分布】
P10 / P50 / P90
              ↓
【斜纹 / 组织】
方向场 / 交织点 / 重复单元
              ↓
【Gate 3】
周期稳定性、双路径一致性、
P10像素宽度、有效样本数
              ↓
【正式输出】
Measurement JSON + Evidence
```

各环节为什么存在：

| 环节 | 解决的问题 | 如果省掉可能发生什么 |
|---|---|---|
| Gate 2 | 图片是否真的可测 | 虚焦/皱褶会被误认为纱线特征 |
| 几何归一化 | 像素距离可否代表真实距离 | 同一根纱在不同位置换算成不同 mm |
| 双图配准 | 反射和透射是否对应同一区域 | 中心线无法可靠映射到表面宽度 |
| 多尺度 | 50MP计算量过大 | RK3576内存和CPU压力失控 |
| 方向检测 | 经纬轴在哪里 | 一维投影和周期检测方向错误 |
| 周期粗估 | 相邻纱线大概隔多远 | Peak搜索容易找到错误峰 |
| 中心线精定位 | 每根纱实际在哪里 | 只知道频率，不能稳定计数与测宽 |
| 双路径密度 | 防止单一算法误判 | FFT谐波/漏峰可能直接变成错误密度 |
| 高分辨率局部测宽 | 表观粗细 | 低分辨率图只能数纱，不能稳健测边缘 |
| P10/P50/P90 | 表达纱线不是完全均匀的 | 单平均值会掩盖竹节和局部异常 |
| Gate 3 | 是否允许发布结果 | 低分辨率/弱周期样本仍会输出“伪精确值” |
| Evidence | 能否解释和复核 | 出错时只能看到结果，看不到原因 |

### 1.9 V1.0 各输出指标的性质

为了避免后续把“测量”“识别”“推断”混在一起，V1.0 建议这样定义：

| 指标 | 性质 | 依据 |
|---|---|---|
| 经密 | 直接视觉计量 | 中心间距/计数 + mm/px |
| 纬密 | 直接视觉计量 | 中心间距/计数 + mm/px |
| 经纬密度比 | 计算结果 | 经密 ÷ 纬密 |
| 经纱表观宽度 | 直接视觉计量 | 高分辨率边界距离 + mm/px |
| 纬纱表观宽度 | 直接视觉计量 | 高分辨率边界距离 + mm/px |
| P10/P50/P90 | 统计结果 | 多根纱线宽度分布 |
| 左斜/右斜 | 视觉识别/规则结果 | 方向场、Hough、Gabor 等 |
| 斜纹角度 | 几何测量 | 方向线角度 |
| 2/1、3/1组织 | 视觉识别结果 | 交织矩阵/重复单元 |
| Ne/tex 粗略参考 | **视觉特征驱动的经验推断/建议值** | 表观宽度、经纬密度、组织等结构化视觉特征 + 经专家/样本校验的经验规则或查表逻辑 |

这一分类的目的，是保证报告不会把“表观宽度”直接等同于“纱支”，也不会把组织识别结果包装成物理计量结果。

V1.0 可以把 Ne/tex 作为输出的一部分，但必须使用“**粗略参考/视觉推断建议**”的名称，并同时满足以下约束：

1. 不输出为单一确定真值，优先输出“建议值 + 区间”；
2. 同时给出置信等级/适用状态；
3. 明确标记 `reference_only=true`，不进入计量验收；
4. 不能反向修改经密、纬密、表观宽度等直接计量值；
5. 如果当前样布超出经验规则覆盖范围，应输出 `NOT_AVAILABLE`，而不是强行给出 Ne/tex；
6. 后续积累足够“视觉特征 + 真实 Ne/tex”标签后，再由第二阶段 Yarn Count Estimator 替换/增强该经验规则。

### 1.10 V1.0 纱支粗略建议的定位

V1.0 的纱支输出本质上是“**计量结果之上的辅助判断**”，而不是 Fabric Measurement Engine 的直接测量能力。

建议链路：

```text
Fabric Measurement Engine
        ↓
经/纬表观宽度 P10/P50/P90
经密 / 纬密
组织 / 斜纹 / 竹节等结构特征
        ↓
Yarn Count Advisory Rules（V1）
        ↓
Ne/tex 粗略建议值 + 建议区间 + 置信等级
```

V1 建议采用可解释、可配置、可审计的规则/查表方式，例如：

```text
纱线表观宽度区间
+ 经/纬密度区间
+ 组织类型
+ 是否竹节/异常
        ↓
经验规则表
        ↓
候选纱支范围
```

这套规则应由纺织专业经验和少量已知真实纱支样本共同校正，而不是让 GPT 直接看图猜 Ne/tex。

建议输出示例：

```json
{
  "warp_yarn_count_advisory": {
    "recommended_ne": 10.0,
    "range_ne": [9.0, 11.0],
    "confidence": "MEDIUM",
    "basis": [
      "warp_width_p50_mm",
      "warp_density_per_cm",
      "weave_type"
    ],
    "nature": "visual_estimation",
    "reference_only": true
  }
}
```

> 该字段可用于选样、快速判断和后续数据积累，但不得表述为实验室纱支测量值。

---

## 2. 本次建设范围

### 2.1 纳入范围

1. Engine 输入适配与数据契约。
2. Gate 2 图片质量检查。
3. 根据既有 Camera Profile 进行畸变/几何归一化。
4. 正面反射图与透射图配准。
5. 50MP 图像的多尺度与 Tile 处理。
6. 经纬两组纱线方向检测。
7. 经纬周期检测。
8. 经纬中心线精定位。
9. 经密、纬密、经纬密度比计量。
10. 经/纬表观纱线宽度 P10/P50/P90 计量。
11. 左斜/右斜、斜纹角度分析。
12. 组织识别能力的基础框架，待核心计量稳定后再逐步支持 2/1、3/1 等。
13. Gate 3 计量可信度判断。
14. 证据图、中间结果、算法版本与 Measurement JSON 输出。
15. x86 研发环境 Benchmark。
16. RK3576 ARM64 生产化与性能验证。
17. 基于表观宽度、密度、组织等结构化特征输出 Ne/tex 粗略参考建议；该结果仅作辅助判断，不作为计量验收值。

### 2.2 明确不纳入范围

1. Gate 1 手机、镜头、支架的设备认证。
2. 手机 Camera App。
3. ChArUco/标定板采集流程本身。
4. 数据驱动的 Yarn Count Estimator / Ne、tex 正式预测模型；该能力留到第二阶段。V1 仅保留规则型粗略参考建议。
5. YOLO、SAM、CNN、ViT 等本地视觉模型。
6. GPT 在生产运行时动态选择或修改计量算法。
7. OpenAI Code Interpreter 作为正式生产计量环境。

---

## 3. 上游输入基线

Fabric Measurement Engine 默认上游已经完成手机和工位认证，并提供可信 Camera Profile。

### 3.1 图片范围与质量要求

#### 3.1.1 一张计量图片到底拍多大的布

V1.0 建议把单张计量图片的**标称物面视野（FOV）固定为约 100 × 75 mm**。

这里的 100 × 75 mm 指：

> **整张计量图在真实牛仔布上覆盖的实际物理区域。**

不是图片的打印尺寸，也不是 ROI 的像素尺寸。

示意：

```text
实际牛仔布

          100 mm
┌──────────────────────────────┐
│                              │
│    ┌────────────────────┐    │
│    │                    │    │
│    │   中央有效计量区    │    │ 75 mm
│    │     ≈80×60 mm      │    │
│    │                    │    │
│    └────────────────────┘    │
│                              │
└──────────────────────────────┘
```

建议中央约 80 × 60 mm 作为主要高可信计量区，外围区域用于：

- 镜头畸变和边缘解析能力缓冲；
- 配准安全边界；
- 压布框和机械结构避让；
- ROI 裁切余量。

#### 3.1.2 为什么建议约 100 × 75 mm

这个范围是“覆盖足够多根纱线”和“每根纱线拥有足够像素”之间的折中。

如果 FOV 太小：

- 只能看到很少几根纱；
- 局部竹节或异常会过度影响结果；
- 经密/纬密统计代表性下降。

如果 FOV 太大：

- 同一根纱分到的像素数下降；
- 宽度边缘定位能力下降；
- 50MP 的高像素优势被大视野稀释。

因此 V1.0 不建议拍 A4/A3 范围，更不建议拍整条裤子或整块大样。

#### 3.1.3 分辨率与 mm/px 的关系

推荐使用 48/50MP 级认证摄像头，并获得约：

```text
8000 × 6000 px
```

的全分辨率计量图。

如果横向 8000 px 对应 100 mm：

```text
100 mm ÷ 8000 px
= 0.0125 mm/px
```

这就是物面采样精度。

V1.0 的**硬门槛**：

```text
mm/px ≤ 0.015
```

推荐目标：

```text
mm/px ≈ 0.0125
```

这里应特别强调：

> **50MP 是推荐的设备准入条件，真正决定是否适合计量的是 mm/px，而不是手机宣传页上的 MP 数字。**

例如：

- 50MP + 100 mm FOV：通常很好；
- 50MP + 300 mm FOV：可能不适合精确纱宽；
- 更高像素但失焦：仍然不合格。

#### 3.1.4 为什么还有“有效纱线宽度 P10 ≥ 12 px”

`mm/px` 说明工位理论上具有多高的空间采样能力，但并不能证明当前面料里的纱线真的足够宽、足够清晰。

因此 Engine 在完成初步中心线和边界检测后，还要检查：

```text
有效纱线宽度 P10 ≥ 12 px
```

这里不采用“最细一根纱必须 ≥12 px”，因为最小值很容易受到：

- 毛羽；
- 错误边缘；
- 局部断裂；
- 交织点；
- 噪声；

影响。

采用 P10 表示：

> 至少约 90% 的有效纱线测宽结果处于足够的像素尺度。

推荐目标：

```text
P10 ≥ 16 px
```

如果一根表观宽度约 0.20 mm 的纱线，在 0.0125 mm/px 下：

```text
0.20 ÷ 0.0125 = 16 px
```

因此 100 mm FOV + 8000 px 横向分辨率与 16 px/0.20 mm 纱线正好形成合理的工程匹配。

#### 3.1.5 V1.0 图片输入基线

| 项目 | V1.0要求 | 为什么 |
|---|---|---|
| 摄像头 | 48/50MP 级认证摄像头 | 为 100 mm FOV 下保留足够像素余量 |
| 推荐图片分辨率 | ≥8000×6000 级 | 支撑约0.0125 mm/px |
| 标称物面视野 | 约100×75 mm | 平衡统计代表性与局部细节 |
| 中央主要计量区 | 约80×60 mm | 避开镜头边缘和机械边界 |
| mm/px 硬门槛 | ≤0.015 mm/px | 保证基础空间采样能力 |
| 推荐 mm/px | ≈0.0125 mm/px | 对0.20 mm纱线约16 px |
| 有效纱宽 P10 | ≥12 px | Gate 3计量可信度门槛 |
| 推荐纱宽 P10 | ≥16 px | 提高表观宽度稳定性 |
| 图片类型 | 同位置正面反射 + 透射 | 两类图承担不同测量职责 |
| 数字变焦 | 禁止 | 防止丢失真实空间分辨率 |
| 对焦 | 必须清晰且稳定 | 高像素不能补偿失焦 |
| 曝光 | 稳定、不过曝/欠曝 | 保证边缘和周期信号 |
| 布料 | 平整、无明显皱褶 | 皱褶会破坏 mm/px 与中心间距 |
| 经向信息 | 建议由工位/人员提供 | 不让算法承担不必要的经纬身份猜测 |

#### 3.1.6 从“多类图片”到“两张标准计量图”的收敛说明

项目最初讨论时，曾把采集图片拆成：

- 正面整体图；
- 正面微距图；
- 背面微距图；
- 透射光图。

随着目标逐步收敛到“结构计量”，这些图片需要重新按**是否真正参与计量**来分类，而不是全部作为强制输入。

| 最初图片类型 | 当前定位 | 是否属于 Engine 标准输入 | 原因 |
|---|---|---:|---|
| 正面整体图 | 样布档案/数字面料卡总览图 | 否，可选 | 视野太大，单根纱像素不足；适合人工浏览和样布记录，不适合毫米级结构计量 |
| 正面微距图 | **正面反射计量图** | **是，必需** | 保留纱线表面边界、斜纹、浮长和表观宽度信息 |
| 背面微距图 | **条件补拍图** | 否，按需 | 对正常样布往往与“正面反射 + 透射”信息重复；当纬向或组织识别置信度不足时再补 |
| 透射光图 | **透射计量图** | **是，必需** | 强化纱线与空隙、周期与中心线，是经密/纬密主输入 |

因此，当前不是“从四张图随意减成两张”，而是把图片分成了三个层级：

```text
【系统级档案图】
正面整体图
用途：样布档案、数字面料卡、人工查看
不参与精确计量

【标准计量最小集】
正面反射图 + 透射图
用途：V1核心结构计量

【条件补拍】
背面反射图
用途：低置信度样本补充信息
```

#### 3.1.7 两张图片是否足以支撑正确识别

结论需要严格表述为：

> **对于当前 V1 已定义的核心指标，“同位置正面反射图 + 透射图”可以作为标准计量最小集；但它不是对所有牛仔布都保证充分。Engine 必须通过 Gate 2 / Gate 3 判断当前两张图是否真的足够。**

两张图之所以能够覆盖当前核心指标，是因为它们的职责互补：

| 指标 | 主要输入 | 为什么 |
|---|---|---|
| 经纱方向 / 纬纱方向 | 透射图为主 | 周期和间隙更突出 |
| 经密 / 纬密 | **透射图为主** | 可稳定寻找周期、中心线和间距 |
| 经纬密度比 | 经密/纬密结果 | 不需要新增图片 |
| 经纱表观宽度 | **反射图 + 透射中心线约束** | 透射图先定位纱线，反射图测表面边缘 |
| 纬纱表观宽度 | **反射图 + 透射中心线约束** | 同上；若有效测宽段不足则补拍 |
| 左斜/右斜、斜纹角度 | 反射图为主 | 表面斜纹方向最清晰 |
| 2/1、3/1 组织 | 反射 + 透射联合 | 交织点和周期联合判断；低置信度时允许补拍背面 |
| Ne/tex 粗略参考 | 已有结构化计量结果 | 不直接从新图片猜纱支 |

因此，**两张图能否够用，不由图片数量决定，而由信息是否完整和 Gate 是否通过决定。**

标准流程应是：

```text
正面反射 + 透射
        ↓
Gate 2 图片质量通过？
        ↓ Yes
Fabric Measurement Engine
        ↓
Gate 3 计量可信度通过？
        ↓ Yes
发布标准结果

如果 Gate 3 不通过：
        ↓
根据 failure_reason 决定
重新拍摄 / 平整样布 / 补拍背面反射图 / 标记超出当前能力范围
```

##### 必须补拍背面反射图的典型条件

背面图不作为默认输入，但出现以下情况时应作为条件补拍：

1. 纬纱中心线或有效边缘数量不足；
2. 纬纱表观宽度 `P10` 或有效样本数未通过 Gate 3；
3. 组织交织矩阵存在多个同等可能结果；
4. 反射图中纬向有效表面段被大面积遮挡；
5. 透射图对某类高密、厚重或特殊结构样布的对比度不足，而背面能够提供更多有效纹理证据；
6. Engine 返回专门的 `BACK_REFLECTION_REQUIRED` 状态。

需要注意：

> **背面补拍不是用来补救虚焦、严重皱褶、错误 FOV 或反射/透射图错位。**

这些问题属于采集失败，应重新拍摄，而不是增加更多错误图片。

##### 正面整体图为什么不再作为 Engine 输入

正面整体图仍然有价值，但它属于“牛仔面料智能视觉分析系统”而不是 Fabric Measurement Engine 的计量输入。

它适合放入数字面料卡，用于：

- 样布档案；
- 人工浏览；
- 样布外观上下文；
- 后续样布检索或 GPT 结果解释。

但整体图为了覆盖更大的样布范围，会显著降低单根纱线的 px 数，因此不能替代 100 × 75 mm 的标准计量图。

综上，建议正式定义为：

> **系统级可选：1 张正面整体图；单位置标准计量：1 张正面反射图 + 1 张透射图；只有 Gate 3 指示信息不足时，才增加背面反射图。**

#### 3.1.8 一个位置需要几张图

每个采样位置，例如 P1，默认两张：

```text
P1-Reflection
正面反射图
+
P1-Transmission
透射图
```

即：

> **2 张 / 位置。**

如果只是分析一个局部位置，P1 即可。

如果上层业务希望输出更能代表“整块样布”的结果，可采集：

```text
P1 + P2 + P3
```

三个不同物理区域，每个区域 2 张，总计 6 张。

P1/P2/P3 的目的不是重新对焦，也不是让算法“多图投票”，而是进行**空间抽样**：

```text
手机、镜头、焦点、曝光、光源不动
                ↓
              移动布料
                ↓
      P1 / P2 / P3 分别采样
```

Engine 本身不强制必须三个位置。

#### 3.1.9 RAW 与 JPEG 的建议

RAW 在本项目中的主要价值，是用于 PoC 判断：

> 手机 ISP、锐化、降噪和 JPEG 压缩是否会显著影响周期和纱宽。

建议 PoC：

```text
同一位置：
RAW/DNG + 最高质量 JPEG 同时保留
```

用相同 Ground Truth 比较：

- 经密误差；
- 纬密误差；
- 纱宽误差；
- 重复性；
- 运算和存储成本。

如果高质量 JPEG 与 RAW 的计量差异可以忽略，正式生产优先使用 JPEG。

原因是 50MP RAW 单张可能达到几十 MB 甚至约 80 MB 级，对：

- RK3576 内存；
- 本地缓存；
- 网络；
- 云端归档；

压力明显更高。

因此：

> **RAW 是 PoC 验证项，不预先作为正式生产硬要求。**

#### 3.1.10 明确不接受的计量图片

以下图片不得作为正式 Fabric Measurement Engine 计量输入：

- 微信/企业微信等二次压缩后的图片；
- 截图；
- 视频帧截取；
- 数字变焦图片；
- AI 超分图片；
- 二次锐化/滤镜图片；
- 明显虚焦图片；
- 布料明显皱折或拱起的图片；
- 未绑定 Camera Profile 的任意手机照片。

#### 3.1.11 图片要求的简化记忆版

后续研发、采购和测试可以统一记住四个数字：

```text
50MP
100 mm
0.015 mm/px
12 px
```

分别表示：

- **50MP**：推荐的采集设备等级，不是最终计量门禁；
- **100 mm**：一张计量图横向大约覆盖 100 mm 牛仔布；
- **0.015 mm/px**：设备/采集层必须满足的物面分辨率上限；
- **12 px**：Engine 对有效纱线宽度 P10 的最低可信门槛。

推荐状态则是：

```text
约 8000 px / 100 mm
≈ 0.0125 mm/px
对 0.20 mm 纱线 ≈ 16 px
```

因此可以把 V1.0 的图片设计思想概括成：

> **既要一张图看见足够多根纱，又要保证最细目标纱线仍然占据十几个像素；这就是 100 mm FOV 与 50MP 组合的核心原因。**

### 3.2 输入数据契约建议

```json
{
  "sample_id": "D001",
  "position_id": "P1",
  "reflection_image": "D001_P1_R.jpg",
  "transmission_image": "D001_P1_T.jpg",
  "camera_profile_id": "ST001_CAM01_V3",
  "mm_per_px_x": 0.01242,
  "mm_per_px_y": 0.01239,
  "warp_axis_hint": "vertical",
  "capture_timestamp": "2026-08-11T12:00:00+08:00"
}
```

---

## 4. 建设原则

### 4.1 先计量，后智能

优先级：

```text
采集质量
  >
确定性视觉计量
  >
数据质量
  >
后续纱支推断
  >
GPT 解释
```

GPT/Codex 参与研发，但不直接产生生产计量值。

### 4.2 先单点，再多点

Engine 本身只处理单个位置 P1/P2/P3。

- 单点：反射 1 张 + 透射 1 张。
- 多点：由上层业务调用 Engine 分别处理 P1/P2/P3，再做统计融合。

不要在 Engine 内硬编码“必须三个位置”。

### 4.3 先密度，再宽度，再组织

实施顺序必须是：

```text
经纬方向
  ↓
经纬周期
  ↓
中心线
  ↓
经密 / 纬密
  ↓
表观宽度
  ↓
斜纹 / 组织
```

不要一开始同时开发所有指标。

### 4.4 50MP 必须多尺度处理

禁止对 50MP 全图依次执行完整 FFT、Gabor、边缘、形态学和组织识别。

应采用：

```text
L0 50MP 原图
 ├─ 高分辨率 Tile → 精确纱宽
 ├─ L1 中尺度图 → 边缘/组织
 └─ L2 低尺度图 → 方向/FFT/周期
```


### 4.5 原理与工程设计之间的对应关系

| 原理问题 | 工程设计 | 目的 |
|---|---|---|
| 纱线是周期结构 | FFT / Autocorrelation / Projection | 找到经纬周期 |
| FFT适合找周期但可能选谐波 | Projection/Peak 二次精定位 | 避免只相信频域主峰 |
| 需要真实 mm 值 | 使用上游 Camera Profile 的 mm/px | px → mm |
| 透射图更容易看到纱线/空隙 | 密度优先使用透射图 | 提高周期和中心线稳定性 |
| 反射图保留表面边界 | 宽度优先使用反射高分辨率 Tile | 测表观纱宽 |
| 50MP太大 | L0/L1/L2 多尺度 + Tile | 控制 RK3576 算力和内存 |
| 单条扫描线易受局部异常影响 | 多 Strip、多点统计 | 提升稳健性 |
| 毛羽、交织点会污染边缘 | 中心线约束 + 1D Profile + 异常剔除 | 避免粗暴轮廓测宽 |
| 一个异常值不能判整图失败 | P10/P50/P90 | 使用稳健统计 |
| 同一方法可能出现误判 | 双路径密度计算 + Gate 3 | 形成交叉验证 |
| GPT不适合做精确计量 | GPT只进入研发/解释闭环 | 保证生产结果确定性 |

---

# 5. 建设步骤

## Step 0：冻结指标、Ground Truth 与 Golden Dataset

这是第一项工作，不要先写复杂算法。

### 目标

建立一套所有候选算法都使用的固定基准数据集。

### 建议样本

第一轮：

- 30～50 块开发样布；
- 另留约 20 块独立验证样布；
- 验证样本在算法调参阶段不得参与参数选择。

样本重点覆盖：

- 常规 3/1 牛仔；
- 2/1；
- 粗纱；
- 细纱；
- 竹节；
- 紧密结构；
- 疏松结构；
- 明显洗水；
- 毛羽较重；
- 异常或困难样布。

### 每个样本至少需要的人工基准

```text
Sample ID
经向确认
人工经密
人工计划纬密
显微/人工经纱表观宽度（如可获得）
显微/人工纬纱表观宽度（如可获得）
真实经纱 Ne/tex（如客户/实验室可提供）
真实纬纱 Ne/tex（如客户/实验室可提供）
已知组织
备注/异常类型
```

### 关键要求

训练/验证拆分必须按“样布/SKU”拆分，不能把同一块布的不同位置随机拆到不同集合。

### 交付物

```text
dataset/
ground_truth.csv
dataset_manifest.json
data_quality_report.md
```

---

## Step 1：搭建 Fabric Algorithm Workbench

### 目标

先建立“算法可替换、可批量跑、可比较”的研发骨架。

### 为什么本项目建议使用 Codex 做研发闭环，而不能完全依赖 GPT/VLM 直接识别

这里必须区分“**大模型帮助研发算法**”和“**大模型直接承担计量算法**”两件完全不同的事情。

Fabric Measurement Engine 的核心输出包含：

- 经密；
- 纬密；
- 中心间距；
- 表观宽度；
- P10/P50/P90；
- 斜纹角度。

这些输出具有明确的几何和统计定义，因此系统必须能够回答：

> 这个数字是怎样从像素一步一步计算出来的？

如果完全依赖 GPT/VLM 直接看图回答，会存在几个根本问题：

1. **结果不是严格确定性计算。** 同一图片在提示词、模型版本或推理策略变化后，可能出现不同估计；
2. **精确计数和空间测量不是大模型最可靠的能力。** 模型能够理解纹理，但不等于能够稳定完成 0.2 mm 级边缘定位；
3. **难以建立计量证据链。** 无法稳定保存“周期峰—中心线—边缘—mm/px—最终数值”的全过程；
4. **难以做严格回归。** 计量系统需要同一 Engine Version 对同一输入得到相同结果，并能比较版本前后的误差变化；
5. **模型升级不可控。** 即使大模型整体能力提升，也不能假设某个具体纱线计量指标不会发生行为漂移；
6. **无法替代信息本身。** 如果图片失焦、分辨率不足或一根纱只有数个像素，大模型不能恢复已经不存在的物理信息。

因此，GPT/VLM 不应成为 Fabric Measurement Engine 的生产计量核心。

Codex 在这里更适合的原因不是“Codex 比 GPT 更懂图片”，而是它能够围绕**真实代码仓库、固定数据集和自动测试环境**完成工程闭环：

```text
工程师定义计量问题
        ↓
Codex 阅读现有代码和 Ground Truth
        ↓
实现 FFT / Projection / Autocorrelation / Gabor 等候选
        ↓
实际运行代码
        ↓
Benchmark Runner 批量计算误差
        ↓
生成失败样本和 Evidence
        ↓
Codex/GPT 分析失败模式
        ↓
Codex 修改代码 / 参数
        ↓
Regression
        ↓
验证集通过
        ↓
冻结为确定性 Algorithm Profile
```

这意味着：

> **Codex 的价值是把大模型的分析能力转化为“可执行代码 + 可重复实验 + 可冻结版本”，而不是让大模型直接替代 OpenCV/数值算法。**

在本项目中建议形成如下职责分工：

| 能力 | GPT/VLM直接识别 | Codex研发确定性算法 | 最终生产 Engine |
|---|---:|---:|---:|
| 理解失败样本 | 强 | 强 | 不负责 |
| 提出算法思路 | 强 | 强 | 不负责 |
| 修改真实工程代码 | 不作为主方式 | **强** | 不负责 |
| 批量运行 Golden Dataset | 不适合作为主计量 | **可自动执行** | 可执行 |
| 经纬精确计量 | 不建议 | 研发算法 | **确定性输出** |
| 证据链 | 弱/不稳定 | 可生成 | **必须保存** |
| 回归测试 | 难直接保证 | **核心优势** | 必须通过 |
| 版本冻结 | 不适合 | 支持工程实现 | **Engine/Profile版本化** |

所以本项目的研发原则应明确为：

> **GPT负责帮助工程师理解问题，Codex负责把候选方案落实为真实代码并驱动自动实验，Golden Dataset和Benchmark负责裁决，最终RK3576只运行冻结后的确定性算法。**

### 什么叫“用 Codex 把算法固定下来”

这里的“算法固定”不是让 Codex 给出一句“建议使用 FFT + Projection”就结束，而是把一个候选方法变成**可发布的软件资产**。

一个算法只有同时固定以下内容，才算真正完成工程化：

```text
算法结构
+ 关键参数
+ 输入/输出契约
+ 代码 Commit
+ 依赖版本
+ Algorithm Profile
+ Golden Dataset Benchmark
+ 独立验证集结果
+ RK3576 数值一致性
+ RK3576 性能结果
+ 已知失败边界
```

Codex 在这个过程中最有价值的地方，是它可以直接围绕代码仓库完成：

1. 阅读现有实现和历史实验；
2. 把 GPT/工程师提出的算法假设实现成可运行代码；
3. 同时补 Unit Test、Regression Test 和 Evidence；
4. 批量运行 Golden Dataset；
5. 根据失败样本继续修改最小 Patch；
6. 把已经通过验证的算法参数写入 `Algorithm Profile`；
7. 生成可以提交 Git、审查、回滚和重新构建的版本。

所以本项目选择 Codex 的核心理由不是“让另一个 AI 来决定算法”，而是：

> **利用 Codex 把算法研究过程变成软件工程过程。**

最终发布到 RK3576 的不是 Codex，也不是 GPT，而是：

```text
Fabric Measurement Engine <version>
+
Approved Algorithm Profile <version>
```

例如：

```text
Engine: 1.0.0
Profile: denim_standard_v1.0.3
Git Commit: a1b2c3d
OpenCV: x.x
Benchmark Report: BR-0018
Validation Dataset: VD-01
RK3576 Benchmark: PASS
```

这样未来出现结果争议时，可以准确回答：

> “这次 42.3 ends/cm 是由哪个 Engine、哪个 Profile、哪组参数、哪版代码计算出来的。”

这正是完全依赖 GPT/VLM 直接识别无法稳定提供的工程属性。

### 推荐环境

```text
Python 3.x
OpenCV
NumPy
SciPy
pytest
pandas
matplotlib
```

### GPT/Codex 在本阶段的角色

用于：

- 编写候选算法；
- 重构公共模块；
- 自动生成中间证据图；
- 分析失败样本；
- 生成回归测试；
- 修改参数搜索脚本；
- 比较 Benchmark 结果。

但算法是否采用，由数据指标决定。

### 必须先搭建 Benchmark Runner

输入：

```text
Dataset + Algorithm Profile
```

输出至少包括：

```text
sample_id
gt_warp_density
pred_warp_density
warp_error_pct
gt_weft_density
pred_weft_density
weft_error_pct
latency_ms
peak_memory_mb
status
failure_reason
```

### 交付物

```text
benchmark_runner.py
benchmark.csv
benchmark_summary.md
```

---

## Step 2：Input Adapter + Gate 2 + 几何归一化

这一阶段的本质是：

> **先证明输入图片“可量”，再进入任何经纬算法。**

Gate 1 已由手机/工位侧完成，本次 Engine 不负责重新标定相机，但必须验证输入数据契约完整，并使用 Camera Profile 完成后续几何归一化。

如果图片本身虚焦、起皱、严重过曝，后面的 FFT、Gabor 或 GPT 都无法恢复已经丢失的真实结构信息。

### 2.1 Input Adapter

统一处理：

- 图片读取；
- Camera Profile；
- mm/px；
- 经向提示；
- 反射/透射图配对。

### 2.2 Gate 2

首版至少检查：

1. 文件是否损坏；
2. 图片尺寸；
3. 图片是否严重失焦；
4. 是否严重过曝；
5. 是否严重欠曝；
6. 是否存在明显运动模糊；
7. 是否缺失检测区域；
8. 反射/透射图尺寸是否一致。

清晰度候选方法：

- Laplacian variance；
- Tenengrad/Sobel。

阈值不要凭经验直接冻结，应通过“正常图 + 人为失焦图”统计得到。

### 2.3 几何归一化

本次不计算 Camera Profile，只使用上游参数：

```text
Camera Profile
    ↓
Undistort
    ↓
Perspective/metric normalization
    ↓
固定毫米尺度 ROI
```

### 2.4 反射/透射配准

机械结构目标应保证“布不动，只切灯”。

软件仅做：

- 坐标一致性验证；
- 必要时小范围 ECC/Homography 修正。

不要用复杂图像配准去补偿糟糕的采集机械结构。

---

## Step 3：Density MVP —— 第一阶段最重要的里程碑

这是整个 Engine 的第一个正式可验收版本。

### 目标

只解决：

- 两组纱线方向；
- 经/纬周期；
- 中心线；
- 经密；
- 纬密；
- 经纬密度比。

暂时不做表观宽度和组织。

### 3.1 方向检测候选

建议实现至少：

```text
A. Gradient / Structure Tensor
B. Gabor orientation
C. FFT orientation
```

评价：

- 正确率；
- 对竹节/毛羽敏感度；
- RK3576 计算代价。

### 3.2 周期检测候选

必须同时实现并 Benchmark：

```text
A. Projection + Peak
B. FFT + Peak
C. Autocorrelation + Peak
D. Gabor/方向分离 + FFT + Projection 精定位
```

初步看好 D，但不得预先指定 D 为最终答案。

### 3.3 为什么 Density MVP 优先使用透射图

经密/纬密的核心是“周期和中心位置”，不是表面明暗和视觉质感。

反射图中容易存在：

- 斜纹浮长；
- 毛羽；
- 洗水痕迹；
- 表面明暗；
- 纱线互相覆盖；

这些因素会污染周期信号。

透射背光的目的就是把问题简化为：

```text
纱线主体 → 相对暗
纱线间隙 → 相对亮
```

从而让“周期”比“表面纹理”更加突出。

因此 V1.0 建议：

> **透射图作为密度主输入，反射图作为表面宽度与结构主输入。**

### 3.4 建议处理流程

```text
透射图
  ↓
灰度/背景归一化
  ↓
降采样至 L2
  ↓
方向检测
  ↓
旋转/方向归一
  ↓
FFT 或 Autocorrelation
  ↓
获得粗周期
  ↓
多 Strip 1D Projection
  ↓
Peak 精定位
  ↓
中心线集合
```

### 3.5 密度双路径计算

不要只依赖一个公式。

路径 A：

```text
Median center spacing
      ↓
spacing_px × mm/px
      ↓
ends/cm / picks/cm
```

路径 B：

```text
有效物理长度
      ↓
实际中心线数量
      ↓
ends/cm / picks/cm
```

两条路径差异过大：

```text
LOW_CONFIDENCE / FAIL
```

### Density MVP 交付物

```text
warp_density
weft_density
density_ratio
centerline evidence image
periodicity evidence
density confidence
```

---

## Step 4：Yarn Width Measurement

仅在 Density MVP 稳定后开始。

### 目标

这里输出的是**织物状态下的表观纱线宽度**，不是把纱线拆出后测得的真实圆形直径，也不是 Ne/tex。

原因是纱线在织物中会受到：

- 压扁；
- 弯曲；
- 织缩；
- 张力；
- 交织覆盖；
- 毛羽；

影响。

因此 V1.0 对外应使用：

> **经纱表观宽度 / 纬纱表观宽度**

而不是“纱线真实直径”。

输出：

```text
warp_width_mm_p10
warp_width_mm_p50
warp_width_mm_p90

weft_width_mm_p10
weft_width_mm_p50
weft_width_mm_p90
```

### 4.1 不建议的做法

不要简单使用：

```text
Canny
→ findContours
→ boundingRect
→ 宽度
```

因为毛羽、交叉点、斜纹会产生大量假边界。

### 4.2 推荐路线

```text
透射图
  ↓
中心线与周期
  ↓
映射到高分辨率反射图
  ↓
选择适合测宽的局部 Tile
  ↓
沿纱线法向提取多条 1D Profile
  ↓
Gradient response
  ↓
左右边缘配对
  ↓
亚像素边缘拟合（可选）
  ↓
px → mm
  ↓
P10 / P50 / P90
```

### 4.3 高分辨率 Tile

推荐从 L0 原图局部裁取：

```text
1024×1024
或
2048×2048
```

不要整张 50MP 运行高精度边缘检测。

---

## Step 4A：Yarn Count Advisory —— V1 纱支粗略建议

该步骤属于**辅助输出层**，不属于直接计量核心，也不替代第二阶段 Yarn Count Estimator。

### 目标

在已经得到可靠的经/纬表观宽度和密度以后，给用户一个可理解的粗略纱支参考，例如：

```text
经纱：建议约 10 Ne，参考范围 9～11 Ne，置信度 MEDIUM
纬纱：当前经验规则覆盖不足，NOT_AVAILABLE
```

### 为什么一期仍可以保留这个输出

客户真正使用时往往更熟悉 Ne/tex，而不是“0.286 mm 表观宽度”。如果完全不提供纱支层面的参考，计量结果与业务习惯之间仍有一道转换障碍。

但一期数据不足以支持正式回归模型，因此最合理的折中是：

> **允许输出粗略建议，但必须把它和直接计量结果严格分层。**

### V1 推荐实现

不要让 GPT 直接根据图片给出纱支，也不要在数据不足时提前训练 XGBoost。

先实现一个可审计的 `YarnCountAdvisoryRules`：

```text
经/纬表观宽度 P10/P50/P90
+
经密 / 纬密
+
组织类型
+
竹节/异常标识
        ↓
规则表 / 查表 / 经验分段
        ↓
Ne/tex 候选范围
        ↓
置信等级
```

规则来源可以包括：

1. 纺织专业人员已有经验；
2. 客户能够提供的少量“样布—真实纱支”历史样本；
3. 一期持续积累的真实 Ne/tex 标签；
4. 对规则覆盖范围的人工审核。

### 输出约束

必须同时包含：

```text
recommended_ne / recommended_tex
range_ne / range_tex
confidence
basis
reference_only = true
rule_version
```

不得：

- 作为 Gate 3 通过条件；
- 作为 Fabric Measurement Engine 精度验收指标；
- 用粗略纱支反向修正经密/纬密/表观宽度；
- 超出规则覆盖范围后仍强行输出。

### 与第二阶段的关系

当积累足够多的：

```text
视觉特征 + 真实 Warp Ne/tex + 真实 Weft Ne/tex
```

再建设第二阶段 Yarn Count Estimator：

```text
Rule-based Advisory（V1）
        ↓ 数据积累
XGBoost / Random Forest / Regression Benchmark
        ↓
正式 Yarn Count Estimator（V2）
```

V2 模型上线后，V1 经验规则仍可作为基线和异常校验工具，不必删除。


---

## Step 5：Gate 3 —— 计量可信度

Gate 3 是 Engine 内部正式结果发布门槛。

### 已冻结的核心门槛

这里有两类不同性质的门禁：

**设备/采集门禁：**

```text
mm/px ≤ 0.015
```

它由上游 Gate 1 认证，本次 Engine 只读取并校验 Camera Profile，不重新建设 Gate 1。

**结果可信度门禁：**

```text
有效纱线宽度 P10 ≥ 12 px
```

它必须在 Engine 已经完成初步边界检测以后才能判断，因此属于 Gate 3。

两者不能合并成一个拍摄前条件。

推荐目标：

```text
mm/px ≈ 0.0125
有效纱线宽度 P10 ≥ 16 px
```

### Gate 3 还应逐步增加

1. 有效纱线数量；
2. 多 Strip 周期一致性；
3. Peak prominence；
4. 周期间距离散度；
5. 双路径密度计算差异；
6. 异常纱线比例；
7. 反射/透射配准质量；
8. 宽度有效测量点数量。

### 输出状态建议

```text
PASS
LOW_CONFIDENCE
FAIL
```

不要只输出一个 0～1 confidence 而没有原因。

### failure_reason 示例

```text
IMAGE_BLUR
PERIOD_UNSTABLE
INSUFFICIENT_VALID_YARNS
WIDTH_RESOLUTION_INSUFFICIENT
REFLECTION_TRANSMISSION_MISALIGNED
DENSITY_METHOD_CONFLICT
```

---

## Step 6：Twill / Weave Analysis

这一阶段放在密度和宽度稳定之后。

### V1 优先实现

1. 左斜 / 右斜；
2. 斜纹角度；
3. 斜纹周期。

候选方法：

- Hough；
- Gabor orientation；
- 局部方向场。

### 组织识别后置

再逐步建设：

```text
经纬中心线
    ↓
交织点
    ↓
局部方向/浮长判断
    ↓
经浮 / 纬浮矩阵
    ↓
最小重复单元
    ↓
2/1、3/1...
```

组织识别不是 Density MVP 的阻塞项。

---

## Step 7：Evidence 与 Measurement JSON

这是工业化必须项，不是“调试功能”。

### 证据图建议

每次检测至少可生成：

1. 归一化 ROI；
2. 经/纬方向图；
3. FFT/周期图；
4. Peak/中心线覆盖图；
5. 高分辨率纱宽边缘图；
6. 异常/无效区域图。

### Measurement JSON 建议

```json
{
  "engine_version": "1.0.0",
  "algorithm_profile": "denim_standard_v1",
  "camera_profile_id": "ST001_CAM01_V3",
  "mm_per_px_x": 0.01242,
  "mm_per_px_y": 0.01239,

  "gate2": {
    "status": "PASS"
  },

  "warp": {
    "density_per_cm": 42.31,
    "period_px_p50": 19.05,
    "width_mm_p10": 0.251,
    "width_mm_p50": 0.286,
    "width_mm_p90": 0.329,
    "valid_yarns": 87
  },

  "weft": {
    "density_per_cm": 28.15,
    "period_px_p50": 28.65,
    "width_mm_p10": 0.301,
    "width_mm_p50": 0.341,
    "width_mm_p90": 0.386,
    "valid_yarns": 59
  },

  "density_ratio": 1.503,

  "yarn_count_advisory": {
    "warp": {
      "recommended_ne": 10.0,
      "range_ne": [9.0, 11.0],
      "confidence": "MEDIUM",
      "reference_only": true,
      "rule_version": "yarn_advisory_v0.1"
    }
  },

  "twill": {
    "direction": "right",
    "angle_deg": 42.7
  },

  "gate3": {
    "status": "PASS",
    "failure_reasons": []
  },

  "processing": {
    "latency_ms": 2380,
    "peak_memory_mb": 412
  }
}
```

---

## Step 8：Algorithm Profile 参数化

所有参数必须集中管理，不允许散落在代码里。

建议：

```yaml
profile_id: denim_standard_v1

metric:
  max_mm_per_px: 0.015
  min_yarn_width_p10_px: 12

pyramid:
  orientation_max_width: 1600
  density_max_width: 4000
  width_tile_size: 1024

density:
  coarse_method: fft
  refine_method: projection
  validator: autocorrelation

width:
  method: gradient_pair
  samples_per_yarn: 20

gate3:
  min_valid_yarns: 20
```

其中除 `0.015 mm/px`、`12 px` 等已经确认的产品基线外，其余参数必须由 Golden Dataset Benchmark 决定。

---

# 6. GPT / Codex 如何参与本次建设

本章不是说明“GPT/Codex 能做什么”，而是规定工程师在 Fabric Measurement Engine 研发过程中**如何一步一步使用 GPT/Codex 完成算法探索、代码实现、验证、失败分析、回归和版本冻结**。

核心原则只有一句：

> **GPT/Codex 负责提出假设、实现候选和分析失败；Golden Dataset、Ground Truth、Benchmark 和工程师评审负责决定算法是否成立。**

GPT/Codex 只进入研发闭环，不进入生产计量闭环。生产环境必须运行经过验证并冻结的 `Engine Version + Approved Algorithm Profile`。

---

## 6.1 GPT、Codex、工程师与自动测试平台的职责边界

为了避免“把算法决策交给 AI”，本项目建议明确四类角色。

| 角色 | 主要职责 | 不应承担的职责 |
|---|---|---|
| **算法/视觉工程师** | 定义目标、确认 Ground Truth、审核候选方案、判断是否发布 | 不凭少量肉眼样本直接宣布算法有效 |
| **Codex** | 阅读代码、实现候选算法、补测试、生成实验脚本、分析失败、提出 Patch、优化工程代码 | 不拥有算法最终选择权、不自行修改正式基线 |
| **GPT** | 帮助梳理算法原理、分析异常模式、解释 Benchmark、总结实验结论 | 不直接生成生产计量值、不决定门禁是否放宽 |
| **Benchmark / Regression 系统** | 批量执行、统计误差、记录耗时和内存、判断是否通过门禁 | 不解释业务原因、不代替人工核验 Ground Truth |

这里要特别控制两个边界：

1. **Codex 可以修改研发代码，但不能直接覆盖 Approved Profile。**
2. **任何“效果更好”的结论，都必须由同一 Golden Dataset 上的可重复 Benchmark 支撑。**

### 6.1.1 为什么生产识别不能完全依赖 GPT / 大模型

对 Fabric Measurement Engine 而言，大模型最适合解决的是“理解”和“推理辅助”，而不是最终毫米级计量。

工程上必须坚持以下区分：

```text
大模型：
看懂现象、提出假设、解释失败、辅助编码

确定性程序：
处理像素、寻找周期、定位中心线、测量边缘、换算毫米、输出计量值
```

完全依赖 GPT/VLM 直接识别的问题主要不是成本，而是**计量属性不成立**：

- 结果难以证明来自哪一个具体像素和边缘；
- 同一输入的结果无法像固定算法一样严格复现；
- 模型版本或推理行为变化会引入不可控漂移；
- 很难针对 MAE、P95、Fail Rate 建立严格版本回归；
- 无法用大模型“补回”失焦或空间分辨率不足导致的信息缺失；
- 客户后续若质疑 42.3 ends/cm 的来源，系统必须能够展示中心线、周期和换算公式，而不能只回答“模型判断为42.3”。

因此，“为什么用 Codex”不能理解为“把 GPT 换成另一个模型”。真正原因是：

> **Codex 被放在工程代码、命令行、测试和 Git 仓库中工作，可以把大模型的算法建议转化成受版本控制的确定性实现，并通过自动 Benchmark 证明是否有效。**

最终 Algorithm Profile 一旦冻结，即使 Codex、GPT 都不可用，RK3576 仍然可以独立完成计量。这是本系统能够成为“计量引擎”而不是“AI 看图 Demo”的关键。

---

## 6.2 工程师开始使用 Codex 前必须准备好的六项基础资产

如果下面六项没有准备好，不建议进入大规模算法迭代，否则会演变成“看一张图改一个参数”的无闭环调试。

### 6.2.1 代码仓库

至少具备：

```text
fabric-measurement-engine/
├── src/
├── profiles/
├── benchmark/
├── tests/
├── evidence/
└── experiments/
```

所有 Codex 修改必须发生在受 Git 管理的分支中。

### 6.2.2 Golden Dataset

必须有固定开发集和独立验证集，并按 Sample/SKU 隔离。

禁止：

```text
同一块布 P1 → 开发集
同一块布 P2 → 验证集
```

这种拆分会造成数据泄漏，使验证结果虚高。

### 6.2.3 Ground Truth

至少包括：

```text
sample_id
warp_direction
warp_density_gt
weft_density_gt
warp_width_gt（如当前阶段验证宽度）
weft_width_gt（如当前阶段验证宽度）
weave_gt（如已知）
label_source
review_status
```

Ground Truth 本身存在疑问的样本必须标记，不得用于判断算法优劣。

### 6.2.4 Baseline Algorithm

任何优化都必须从一个可运行的 Baseline 开始，例如：

```text
orientation = gradient
density_coarse = fft
density_refine = projection
```

没有 Baseline 就无法回答“新算法到底有没有变好”。

### 6.2.5 Benchmark Runner

必须支持一条命令对固定数据集运行完整算法，例如：

```bash
python benchmark/runner.py \
  --dataset datasets/golden_v1 \
  --profile profiles/denim_baseline_v01.yaml \
  --output experiments/EXP-0001/
```

### 6.2.6 实验编号与记录机制

每一次算法变化都创建独立 Experiment：

```text
EXP-0001
EXP-0002
EXP-0003
...
```

不得出现：

> “我刚才把阈值调了一下，好像效果更好。”

而无法回答调了什么、为什么调、在哪些样本上变好、哪些样本变差。

---

## 6.3 标准研发闭环总流程

工程师每开发一个计量能力，都按照同一套闭环执行：

```text
① 明确本轮单一问题
        ↓
② 固定 Baseline 与数据集
        ↓
③ 运行 Baseline Benchmark
        ↓
④ 让 GPT/Codex 分析问题并提出候选假设
        ↓
⑤ 工程师选择值得验证的候选
        ↓
⑥ Codex 实现最小 Patch + 单元测试
        ↓
⑦ 小样本 Smoke Test
        ↓
⑧ 开发集 Benchmark
        ↓
⑨ 自动收集失败样本和证据图
        ↓
⑩ GPT/Codex 做失败模式分析
        ↓
⑪ 参数或算法修正
        ↓
⑫ Full Regression
        ↓
⑬ 独立验证集验证
        ↓
⑭ RK3576 实机验证
        ↓
⑮ 工程师评审
        ↓
⑯ 冻结 Engine Version / Algorithm Profile
```

如果任何一道门禁失败，就回到对应步骤继续迭代，而不是跳过问题发布。

---

## 6.4 第一步：一次只定义一个明确问题

不要给 Codex 一个模糊任务：

> “把牛仔布识别算法做好。”

应该把问题缩成一个可以验证的假设，例如：

> 当前 Baseline 在竹节牛仔上经密误差明显升高，怀疑 FFT 选择了谐波而不是基频。本轮只验证“增加自相关校验是否能够降低竹节样本的周期误判率”。

一个合格的研发任务至少包含：

```text
Measurement Target：warp density
Problem：slub denim harmonic selection
Baseline：FFT + Projection
Hypothesis：Autocorrelation can reject harmonic peaks
Dataset：golden_v1 / slub subset
Primary Metric：warp density MAE
Guardrail：normal denim accuracy must not regress
```

这样 Codex 才是在解决工程问题，而不是自由发挥。

---

## 6.5 第二步：先跑 Baseline，不允许直接改代码

每一轮修改前先保存 Baseline 结果：

```text
experiments/EXP-0023/
├── baseline_profile.yaml
├── baseline_metrics.json
├── baseline_samples.csv
├── baseline_evidence/
└── experiment.md
```

建议至少记录：

```text
Warp MAE
Weft MAE
P95 Error
Failure Rate
Mean Latency
P95 Latency
Peak Memory
各面料类型误差
```

工程师只有拿到 Baseline 后，才能知道后续 Patch 的真实收益。

---

## 6.6 第三步：让 GPT/Codex 先分析，不要立即写代码

第一轮给 Codex/GPT 的任务应该是**分析模式**。

推荐任务模板：

```text
目标：分析 Fabric Measurement Engine 当前经密算法在竹节牛仔上的失败原因。

请先不要修改代码。

输入：
1. 当前算法代码路径：src/periodicity、src/density；
2. Algorithm Profile：profiles/denim_baseline_v01.yaml；
3. Benchmark：experiments/EXP-0023/baseline_samples.csv；
4. 失败样本证据图：experiments/EXP-0023/baseline_evidence/；
5. Ground Truth：datasets/golden_v1/ground_truth.csv。

要求：
1. 归类失败样本；
2. 判断误差来自方向、粗周期、Peak 精定位还是 px/mm 换算；
3. 提出不超过3个可验证候选方案；
4. 每个方案说明预期收益、风险、计算成本和验证方法；
5. 不允许建议放宽现有精度门禁来掩盖问题；
6. 输出推荐验证顺序。
```

这一阶段的产物不是代码，而应该是：

```text
Failure Classification
Hypothesis A
Hypothesis B
Hypothesis C
Recommended Experiment
```

工程师审核后只选择其中值得验证的方案。

---

## 6.7 第四步：Codex 只实现“最小可验证 Patch”

确定候选方案以后，再要求 Codex 修改代码。

建议模板：

```text
基于已确认的 Hypothesis A，实现最小可验证版本。

约束：
1. 不修改 Camera Profile、Gate 1 基线；
2. 不修改 mm/px ≤0.015 和 P10 ≥12px 两项正式门禁；
3. 不重构无关模块；
4. 新算法必须通过 Algorithm Profile 开关启用；
5. 保留原 Baseline，可随时切回；
6. 补充单元测试；
7. 对关键中间结果增加 Evidence 输出；
8. 不执行正式 Profile 发布。

完成后请给出：
- 修改文件；
- 核心逻辑；
- 新增参数；
- 新增测试；
- 预期验证指标。
```

推荐形成：

```text
profiles/
├── denim_baseline_v01.yaml
└── exp_0024_autocorr_validator.yaml
```

而不是直接修改 `denim_standard_v1.yaml`。

---

## 6.8 第五步：先做 Unit Test 和 Smoke Test

不要每修改一次就跑完整 Golden Dataset。

### Unit Test

验证算法本身的基本数学正确性，例如：

- 已知周期合成信号能否找到正确周期；
- 旋转 10° 后方向检测结果是否正确；
- `mm/px` 换算是否正确；
- P10/P50/P90 是否计算正确；
- 异常输入是否按预期失败。

### Smoke Test

选取约 5～10 个代表样本：

```text
普通样本
细纱样本
粗纱样本
竹节样本
毛羽样本
历史失败样本
```

只有 Smoke Test 未出现明显回归，才进入开发集全量 Benchmark。

---

## 6.9 第六步：自动 Benchmark，不靠肉眼判断

运行候选算法：

```bash
python benchmark/runner.py \
  --dataset datasets/golden_v1/dev \
  --profile profiles/exp_0024_autocorr_validator.yaml \
  --baseline experiments/EXP-0023/baseline_metrics.json \
  --output experiments/EXP-0024/
```

结果至少自动生成：

```text
summary.json
samples.csv
comparison_vs_baseline.csv
failure_cases.csv
latency.csv
evidence/
report.md
```

### 推荐比较方式

不能只看平均误差，要同时看：

| 指标 | 作用 |
|---|---|
| MAE | 总体精度 |
| Median Error | 典型样本表现 |
| P95 Error | 尾部风险 |
| Failure Rate | 算法可用率 |
| 子类型误差 | 防止某类面料被平均值掩盖 |
| Latency | RK3576后续可运行性 |
| Peak RAM | 50MP处理内存风险 |

例如新算法：

```text
总体 MAE：1.4% → 1.1%   ✅
竹节 MAE：5.8% → 2.0%   ✅
普通牛仔 MAE：0.9% → 1.0% ⚠ 轻微回归
Failure Rate：4.0% → 2.5% ✅
Latency：1.1s → 2.9s       ⚠
```

不能因为“精度更高”就立即采用，还要判断性能代价是否值得。

---

## 6.10 第七步：自动生成失败样本包

Benchmark 结束以后，不要让工程师人工翻几百张图找问题。

系统自动建立：

```text
experiments/EXP-0024/failures/
│
├── D017/
│   ├── input_transmission.jpg
│   ├── input_reflection.jpg
│   ├── orientation.png
│   ├── fft_spectrum.png
│   ├── projection_peaks.png
│   ├── centerlines.png
│   ├── result.json
│   └── ground_truth.json
│
└── D031/
    └── ...
```

每个失败 Case 必须尽量包含完整“证据链”，这样 GPT/Codex 才能分析：

> 错在输入 → 方向 → 周期 → Peak → 中心线 → 密度换算中的哪一步。

如果只有“GT=42，预测=38”两个数字，GPT 很难做可靠根因分析。

---

## 6.11 第八步：让 GPT/Codex 做“失败模式聚类”，而不是逐张修参数

推荐任务模板：

```text
请分析 experiments/EXP-0024/failures 中全部失败样本。

不要逐样本给出独立阈值。

目标：
1. 将失败样本归并为有限的 Failure Pattern；
2. 找出每个 Pattern 的共同视觉特征和算法中间异常；
3. 判断是算法设计问题、参数问题、图片质量问题还是当前能力边界；
4. 给出每个 Pattern 最小修改方案；
5. 判断哪些样本应由 Gate 2/Gate 3 拒绝，而不是强行计算；
6. 说明修改可能造成的回归风险。
```

希望得到类似：

```text
Pattern F01：FFT二次谐波误选
Pattern F02：透射背光不均造成Projection漂移
Pattern F03：毛羽导致Width Edge Pair错误
Pattern F04：纱线有效宽度不足12px，应由Gate 3拒绝
```

这样系统是在积累**通用失败模式**，而不是越来越多的 if/else 特例。

---

## 6.12 第九步：参数优化和算法优化必须分开

研发中非常容易把二者混在一起。

### 参数优化

例如：

```text
peak_prominence
strip_count
gabor_sigma
fft_band_limit
```

算法结构不变，只搜索合理参数范围。

可以让 Codex 编写参数扫描：

```text
Parameter Grid
     ↓
Benchmark Runner
     ↓
Accuracy / Fail Rate / Latency
     ↓
Pareto Candidates
```

### 算法优化

例如：

```text
FFT only
→
FFT + Projection
→
FFT + Projection + Autocorrelation Validator
```

这是算法结构变化，必须创建新的 Experiment。

禁止一边改算法一边大范围改参数，然后无法解释收益来自哪里。

---

## 6.13 第十步：设置明确的“停止迭代条件”

否则 GPT/Codex 可以无限提出新方案。

每个研发目标应预先定义 Stop Criteria。

以 Density MVP 为例，内部目标可暂定：

```text
经密 MAE ≤ 2%
纬密 MAE ≤ 2%
```

同时必须满足：

- 独立验证集不明显回归；
- Failure Rate 达到阶段目标；
- 没有新的系统性失败类型；
- 结果确定性一致；
- 性能仍有 RK3576 落地可能。

一旦达到阶段目标，不应该为了从 1.0% 优化到 0.9% 无限增加复杂度。

**工程可维护性也是优化目标。**

---

## 6.14 第十一步：Full Regression 是每次合并的硬门禁

候选算法通过开发集后，必须运行完整 Regression：

```text
unit tests
      ↓
synthetic tests
      ↓
Golden Dataset dev
      ↓
Golden Dataset validation
      ↓
historical failure cases
      ↓
PASS / FAIL
```

任何历史已解决 Case 再次失败：

> **禁止合并到主分支。**

因此每解决一个真实失败样本，都建议把它加入：

```text
tests/regression/cases/
```

让一次解决的问题永久变成自动门禁。

---

## 6.15 第十二步：x86 通过以后，再进入 RK3576 验证

Codex 在 x86 环境帮助把算法做准之后，才进入 ARM/RK3576。

RK3576 验证分三步：

### A. 数值一致性

同一输入在：

```text
x86 reference
vs
RK3576 ARM64
```

应获得相同或在允许浮点容差内一致的 Measurement JSON。

### B. 性能 Profile

记录：

```text
JPEG/RAW Decode
Normalization
Resize
Orientation
FFT
Projection
Width Tiles
Total Latency
Peak RSS
CPU Utilization
```

### C. 再决定是否优化

只有 Profile 证明某模块是真正热点，才让 Codex 优化：

```text
Python → C++
普通循环 → OpenCV vectorized
CPU → NEON优化
必要时 → GPU/OpenCL/RGA
```

一期**不得因为 RK3576 有 NPU 就主动把确定性算法改成神经网络。**

---

## 6.16 RK3576 性能优化时给 Codex 的任务模板

```text
当前 Fabric Measurement Engine 在 RK3576 上已经通过精度回归，禁止修改计量数学逻辑。

性能数据：
- Total：8.4s
- FFT：0.9s
- Gabor：3.7s
- Width Tiles：2.1s
- Peak RSS：1.8GB

目标：在不改变 Measurement JSON 结果和 Algorithm Profile 的前提下优化性能。

要求：
1. 先根据 Profile 判断真正热点；
2. 不允许先假设 NPU/GPU 一定更快；
3. 优先减少不必要的50MP全图运算和内存复制；
4. 优先评估多尺度、Tile、缓存复用、OpenCV NEON、多线程；
5. 每个优化必须提供前后 Benchmark；
6. 若数值结果超出允许容差则回退。
```

这可以避免 Codex 为了“优化代码”改变算法本身。

---

## 6.17 第十三步：Algorithm Profile 冻结流程

只有以下条件全部满足，实验 Profile 才能升级为 Approved Profile：

```text
Accuracy Gate       PASS
Failure Rate Gate   PASS
Regression Gate     PASS
Validation Gate     PASS
RK3576 Numeric Gate PASS
RK3576 Perf Gate    PASS
Evidence Review     PASS
Engineer Review     PASS
```

冻结后形成：

```text
Engine Version：1.0.0
Algorithm Profile：denim_standard_v1
Dataset Version：golden_v1.2
Camera Contract Version：camera_input_v1
```

并生成：

```text
release/
├── engine_manifest.json
├── denim_standard_v1.yaml
├── benchmark_report.md
├── known_limitations.md
├── regression_summary.json
└── release_notes.md
```

**GPT/Codex 不拥有“批准发布”动作。**

---

## 6.18 每次实验必须留下 Experiment Card

建议在 `experiments/EXP-XXXX/experiment.md` 采用固定模板：

```markdown
# EXP-0024

## Problem
竹节牛仔经密FFT出现二次谐波误选。

## Baseline
Engine: 0.3.2
Profile: denim_baseline_v01
Dataset: golden_v1.1

## Hypothesis
增加Autocorrelation Validator可以区分基频和二次谐波。

## Code Change
- src/periodicity/autocorr.py
- src/density/pipeline.py

## Parameter Change
无。

## Expected Result
降低slub subset经密MAE，不明显影响普通牛仔。

## Result
Warp MAE: 1.40% → 1.08%
Slub MAE: 5.80% → 2.05%
Failure Rate: 4.0% → 2.5%
Latency: 1.10s → 1.35s

## New Failures
D031、D044

## Decision
ACCEPT / REJECT / CONTINUE

## Reason
...
```

这样三个月后仍然能够知道某个参数和算法为什么存在。

---

## 6.19 推荐的 Codex 日常工作方式

工程师每天不应以“聊天”方式随意让 Codex 改代码，而建议按以下顺序：

### 任务 A：读取当前状态

```text
请读取：
- 当前 Engine 版本；
- 当前 Algorithm Profile；
- 最近一次 Benchmark；
- 当前未解决 failure cases。

先给出状态摘要，不修改任何代码。
```

### 任务 B：本轮问题定义

工程师确认一个 Problem Statement。

### 任务 C：候选方案分析

Codex 只提出 1～3 个候选。

### 任务 D：工程师选择

不让 Codex 自动决定所有候选全部实现。

### 任务 E：最小 Patch

Codex 修改代码并补测试。

### 任务 F：自动 Benchmark

程序跑结果，不靠 Codex 主观评价。

### 任务 G：失败样本分析

Codex 根据 Evidence 做根因归类。

### 任务 H：Regression

通过后才进入下一轮。

这样的节奏可以避免代码逐渐演变成无法解释的“AI调出来的参数集合”。

---

## 6.20 建议建设一个内部 `dev-loop` 自动命令

为了让工程师真正按闭环执行，建议把常用动作封装成脚本，而不是全靠人工拼命令。

例如：

```bash
./dev-loop baseline EXP-0024
./dev-loop smoke EXP-0024
./dev-loop benchmark EXP-0024
./dev-loop collect-failures EXP-0024
./dev-loop regression EXP-0024
./dev-loop rk3576-benchmark EXP-0024
./dev-loop release-check EXP-0024
```

甚至可以实现：

```text
Codex修改代码
      ↓
./dev-loop smoke
      ↓
PASS
      ↓
./dev-loop benchmark
      ↓
自动生成 failure package
      ↓
Codex分析
```

Codex负责研发效率，脚本负责流程确定性。

---

## 6.21 推荐的阶段闭环示例：Density MVP

为了让工程师更容易理解，下面给出一轮完整示例。

### Round 0：建立Baseline

```text
Gradient orientation
+
FFT coarse period
+
Projection peak refine
```

跑 30～50 块开发样布。

输出：

```text
Warp MAE = 1.6%
Weft MAE = 2.7%
Failure Rate = 6%
```

发现纬密不达标。

### Round 1：失败分析

Codex分析失败包，发现主要两类：

```text
F01：纬纱投影对洗水纹理敏感
F02：竹节导致FFT谐波误选
```

### Round 2：分别设计实验

不要一次同时解决 F01/F02。

先建：

```text
EXP-0011：验证Autocorrelation处理F02
```

通过后再：

```text
EXP-0012：验证Transmission normalization处理F01
```

### Round 3：全量回归

如果最终：

```text
Warp MAE = 1.3%
Weft MAE = 1.8%
Failure Rate = 2.5%
```

达到 Density MVP 阶段目标。

### Round 4：独立验证集

只运行，不再调参。

如果验证集依旧通过，才进入 RK3576。

### Round 5：RK3576

先证明结果一致，再做性能优化。

### Round 6：冻结

生成：

```text
Engine 0.5.0
Profile density_mvp_v1
```

然后才允许团队进入 Yarn Width Measurement。

这就是一个完整的：

> **问题 → 假设 → 实现 → 数据验证 → 失败分析 → 回归 → 边缘验证 → 冻结**

闭环。

---

## 6.22 工程师必须遵守的十条研发纪律

1. **一次实验只解决一个主要问题。**
2. **任何修改前必须保存 Baseline。**
3. **不允许只凭单张图片肉眼判断算法更好。**
4. **不允许为了让失败样本通过而不断增加样本级 if/else。**
5. **门禁阈值不能由 GPT/Codex 随意放宽。**
6. **所有真实失败 Case 解决后必须进入 Regression。**
7. **开发集可以调参，独立验证集不能调参。**
8. **x86先解决精度，RK3576再解决性能。**
9. **任何性能优化不得悄悄改变计量结果。**
10. **只有工程师和正式发布门禁可以批准 Algorithm Profile。**

---

## 6.23 本章最终落地要求

完成本章建设后，团队应该具备的不只是“能用 Codex 写算法”，而是下面这条可持续研发流水线：

```text
Golden Dataset / Ground Truth
            ↓
      Problem Statement
            ↓
      GPT/Codex Analysis
            ↓
     Candidate Experiment
            ↓
         Code Patch
            ↓
       Unit / Smoke Test
            ↓
         Benchmark
            ↓
      Failure Package
            ↓
     GPT/Codex RCA
            ↓
         Regression
            ↓
    Independent Validation
            ↓
      RK3576 Validation
            ↓
      Release Gate
            ↓
 Approved Algorithm Profile
```

最终原则是：

> **Codex让算法研发更快，Benchmark让算法研发更可信，Regression让已经解决的问题不再回来，RK3576验证让实验算法真正成为产品算法。**

### 禁止的生产运行方式

```text
图片
↓
GPT 临时决定算法
↓
GPT 临时写 Python
↓
输出计量值
```

正式生产环境必须使用：

```text
Approved Algorithm Profile
+
固定 Engine Version
```


# 7. 推荐代码结构

```text
fabric-measurement-engine/
│
├── README.md
├── pyproject.toml
├── profiles/
│   └── denim_standard_v1.yaml
│
├── src/
│   ├── input/
│   ├── quality/
│   ├── normalization/
│   ├── registration/
│   ├── pyramid/
│   ├── orientation/
│   ├── periodicity/
│   │   ├── fft.py
│   │   ├── autocorr.py
│   │   ├── projection.py
│   │   └── gabor.py
│   ├── centerline/
│   ├── density/
│   ├── width/
│   ├── weave/
│   ├── statistics/
│   ├── gates/
│   └── evidence/
│
├── benchmark/
│   ├── runner.py
│   ├── metrics.py
│   └── reports/
│
├── tests/
│   ├── unit/
│   ├── regression/
│   └── golden/
│
└── tools/
    ├── inspect_sample.py
    ├── generate_evidence.py
    └── compare_algorithms.py
```

研发期建议 Python 优先。

---

# 8. RK3576 生产化步骤

不要在算法还没稳定时提前优化 ARM。

## 8.1 第一步：x86/Python 把算法做准

关注：

- Accuracy；
- Failure Rate；
- 可解释性；
- Regression。

先不关注极限性能。

## 8.2 第二步：建立 x86 性能基线

记录：

```text
总耗时
各阶段耗时
Peak RAM
解码时间
FFT时间
Gabor时间
Width Tile时间
```

必须先 Profile，再决定优化点。

## 8.3 第三步：ARM64 直接迁移

先跑：

```text
Python + ARM64 OpenCV/NumPy/SciPy
```

确认结果与 x86 完全一致或在数值容差内一致。

## 8.4 第四步：优化热点

一期优先级：

```text
CPU + NEON
```

确认 OpenCV 构建启用 ARM NEON。

只有 Profiling 明确发现瓶颈后，再考虑：

- C++ 重写热点；
- 多线程；
- Memory Pool；
- Tile 并行；
- RGA Resize；
- GPU/OpenCL。

### NPU

V1 不使用。

不要为了 RK3576 有 6TOPS NPU 而引入神经网络。

---

# 9. 建议的内部验收门槛

以下用于研发和 PoC，不建议现在直接写成客户合同承诺。

### Density MVP

建议目标：

```text
经密 MAE ≤ 2%
纬密 MAE ≤ 2%
```

同时关注：

```text
P95 error
Failure Rate
不同面料类型误差
```

### Repeatability

同一张图重复运行：

```text
结果必须确定性一致
```

同一位置重复采集：

建议观察：

```text
经/纬密度 CV
表观宽度 CV
```

真实阈值在采集硬件确定后由实验数据冻结。

### Width Measurement

第一轮不要先要求“绝对误差≤X mm”。

先验证：

1. 与显微/人工宽度的相关性；
2. 重复测量稳定性；
3. 不同粗细样本是否能稳定排序；
4. P10/P50/P90 是否具有可解释性。

Ground Truth 方法稳定以后再冻结绝对误差指标。

---

# 10. 推荐里程碑

## M0 — 数据与基础框架

完成：

- Golden Dataset；
- Ground Truth；
- 输入契约；
- Measurement JSON；
- Benchmark Runner。

**没有 Benchmark，不进入算法竞选。**

---

## M1 — Density MVP

完成：

- Gate 2；
- Normalization；
- Direction；
- FFT / Projection / Autocorrelation 候选；
- Centerline；
- 经密/纬密；
- Benchmark。

### M1 退出条件

Density 达到内部精度和失败率目标。

---

## M2 — Width Measurement

完成：

- Reflection/Transmission Registration；
- 高分辨率 Tile；
- 1D Profile；
- Edge Pair；
- Width P10/P50/P90；
- Gate 3。

---

## M3 — Twill / Weave

完成：

- 左/右斜；
- 斜纹角度；
- 组织识别基础能力。

---

## M4 — RK3576 Productionization

完成：

- ARM64运行；
- NEON验证；
- 性能 Profile；
- 热点优化；
- 内存优化；
- 服务化；
- 稳定性测试。

---

## M5 — Release Candidate

完成：

- Golden Regression 全通过；
- Algorithm Profile冻结；
- Engine Version冻结；
- Evidence完整；
- RK3576性能门禁通过；
- API与上层业务联调。

---

# 11. 推荐开发优先级

按照重要程度排序：

```text
1. Golden Dataset / Ground Truth
2. Benchmark Runner
3. Density MVP
4. Gate 2 / Gate 3
5. Width Measurement
6. Evidence / JSON
7. Twill / Weave
8. RK3576优化
9. 云端集成
```

不要反过来。

尤其不要先做：

- 漂亮GUI；
- GPT报告；
- RK3576 GPU优化；
- Yarn Count Estimator。

这些都不应该阻塞核心计量能力。

---

# 12. 关键风险与控制建议

## 风险 1：Ground Truth 不可信

如果人工经密/纬密本身有误，算法 Benchmark 没有意义。

**措施：**

- 同一批样布采用统一人工方法；
- 关键样本双人复核；
- 记录计量物理长度与方法；
- 保留 Ground Truth 来源。

## 风险 2：反射图与透射图不是同一区域

将直接影响中心线映射和宽度测量。

**措施：**

- 机械结构要求布不动，只切换灯；
- 软件只允许小范围配准补偿；
- 配准过大直接 Gate 3 降级。

## 风险 3：FFT 把谐波当主周期

**措施：**

- FFT 只作为粗周期；
- Projection 精定位；
- Autocorrelation 校验；
- 双路径密度计算。

## 风险 4：毛羽和交织点污染宽度

**措施：**

- 不直接对全图 Canny；
- 使用中心线约束；
- 只选择有效测宽段；
- 多 Profile + 稳健统计。

## 风险 5：过早针对 RK3576 优化

**措施：**

- x86 先把精度做稳定；
- Profiling 后再优化；
- 不为 GPU/NPU 而改算法。

## 风险 6：GPT 参与生产计量

**措施：**

- GPT 只参与研发和结果解释；
- Engine Version + Algorithm Profile 固化；
- 所有正式结果由确定性代码生成。

---

# 13. 最终交付物建议

一期 Fabric Measurement Engine 至少应形成：

1. `fabric-measurement-engine` 源码仓库；
2. `denim_standard_v1.yaml` Algorithm Profile；
3. Input Contract；
4. Measurement JSON Schema；
5. Golden Dataset；
6. Ground Truth 数据集；
7. Benchmark Runner；
8. Benchmark 报告；
9. Gate 2 规则；
10. Gate 3 规则；
11. Density Measurement 模块；
12. Yarn Width Measurement 模块；
13. Twill Analysis 模块；
14. Evidence 生成模块；
15. x86回归测试；
16. RK3576 ARM64构建；
17. RK3576性能测试报告；
18. Engine Version / Profile Version 发布机制；
19. 算法设计说明；
20. 已知边界与失败样本清单。
21. `YarnCountAdvisoryRules` V1 规则表、规则版本和粗略 Ne/tex 输出契约。

---

# 14. 建议立即启动的第一个开发任务

不要直接创建完整 Fabric Measurement Engine。

第一项真正的开发任务建议定义为：

## `Density MVP V0.1`

范围：

```text
标准透射图
+
Camera Profile / mm_per_px
        ↓
Gate 2
        ↓
几何归一化
        ↓
方向检测
        ↓
FFT / Projection / Autocorrelation 三组候选
        ↓
粗周期
        ↓
多 Strip Peak 精定位
        ↓
中心线
        ↓
经密 / 纬密
        ↓
Benchmark
```

完成这个 MVP 后再决定：

1. 哪套周期算法进入 `denim_standard_v1`；
2. 哪些面料类型属于当前失败边界；
3. 经/纬密度内部精度门槛是否合理；
4. 是否开始开发 Yarn Width Measurement；
5. 是否需要对算法策略进行分类 Profile。

这一步跑通以后，Fabric Measurement Engine 才真正从“技术设想”进入“可工程化产品”阶段。

---

# 15. 附录：图片来源、手机选型与采集参数建议

本附录用于指导 PoC、Golden Dataset 建设以及后续手机采集端实施。这里的手机型号只是当前候选，不应成为 Fabric Measurement Engine 的永久绑定条件。正式判断一台手机是否可用，最终仍以 **实际输出图片 + FOV + mm/px + 清晰度 + 稳定性** 是否通过认证为准。

## 15.1 图片来源建议

图片来源需要区分为两类：**生产计量图片**和**算法研发/Golden Dataset 图片**。两者都不能采用来源不受控的网络图片作为正式计量依据。

### 15.1.1 生产计量图片来源优先级

推荐优先级如下：

```text
一级：固定手机 + 固定工位 + 专用采集 App 直接产生的原始计量图片
  ↓
二级：固定手机 + 厂商专业/高分辨率模式直接拍摄的原始图片（PoC阶段）
  ↓
三级：经过人工确认、保留完整原文件和采集参数的临时测试图片
  ↓
禁止：微信/企业微信/IM压缩图、截图、视频帧、网络下载图、二次编辑图、AI超分图
```

正式生产应只接受一级来源。

原因是 Fabric Measurement Engine 输出的是 `ends/cm`、`picks/cm`、`mm` 等计量值，因此图片必须能够追溯到：

- 哪一台手机；
- 哪一颗物理摄像头；
- 哪一个 Camera Profile；
- 哪一个工位；
- 哪一个采样位置；
- 哪一种光源状态；
- 哪一组曝光/焦点参数。

如果图片经过社交软件压缩、缩放、截图或二次编辑，像素与物面的对应关系可能发生变化，不能继续作为正式计量输入。

### 15.1.2 Golden Dataset 图片来源

算法研发阶段建议优先由**同一套或少量受控采集工位自行采集**，而不是从网络收集牛仔布图片。

Golden Dataset 建议至少保存：

```text
Sample_ID
Fabric_SKU
Position_ID (P1/P2/P3)
Reflection_Image
Transmission_Image
Camera_Profile_ID
mm_per_px_x / mm_per_px_y
Warp_Axis_Hint
Ground_Truth_Warp_Density
Ground_Truth_Weft_Density
Ground_Truth_Width（如有）
Known_Weave（如有）
Capture_Metadata
```

网络公开图片可以用于：

- 观察特殊牛仔结构；
- 收集算法失败类型；
- 辅助研发人员理解场景；

但不应进入正式精度 Benchmark，因为其真实 FOV、mm/px、压缩过程和 Ground Truth 通常不可追溯。

### 15.1.3 PoC 阶段建议保留 RAW + JPEG 对照

PoC 前期建议同一位置同时保存：

```text
RAW/DNG（如果设备支持）
+
最高质量全分辨率 JPEG/HEIF
```

目的不是长期坚持 RAW，而是验证：

- 手机 ISP 锐化是否影响中心线；
- 降噪是否吞掉细纱边缘；
- JPEG 压缩是否影响宽度 P10/P50/P90；
- RAW 和 JPEG 的经密/纬密结果是否存在系统偏差。

如果实验表明最高质量 JPEG 与 RAW 在核心计量指标上的差异可忽略，则正式生产优先 JPEG，以降低 RK3576 的内存、缓存、传输和存储压力。

---

## 15.2 手机类型建议

### 15.2.1 手机不是按品牌认证，而是按“摄像头工位能力”认证

正式选型不建议写成：

> “系统只支持某一款手机。”

更合理的是形成：

> **Certified Camera / Phone List**

任何候选手机只要最终满足以下条件，都可以进入认证清单：

1. 有效主摄或中长焦摄像头达到约 48/50MP 级；
2. 实际计量图可获得约 8000×6000 级有效分辨率；
3. 在目标工位下可以形成约 100×75 mm FOV；
4. `mm/px ≤ 0.015`，推荐约 `0.0125 mm/px`；
5. 检测区整体清晰，不只是画面中心清晰；
6. 能够固定同一物理摄像头，不发生自动切镜头；
7. 能够固定或受控设置焦点、曝光、ISO；
8. 不依赖数字变焦获得目标 FOV；
9. 可以获得未经 IM/社交软件二次压缩的原文件；
10. 连续重复拍摄具有可接受的一致性。

### 15.2.2 当前 PoC 候选机型

| 候选手机 | 摄像头特点 | 建议定位 | 主要原因 / 注意事项 |
|---|---|---|---|
| **Xiaomi 15** | 50MP 主摄；另有 50MP 60mm 浮动长焦 | **优先 PoC 候选** | 60mm 中长焦有利于在较舒适工作距离下获得较小 FOV；正式使用前必须验证第三方 App 能否取得所需物理摄像头和全分辨率输出 |
| **OPPO Find X9** | 50MP 主摄；50MP 73mm 潜望长焦 | **优先 PoC 候选** | 73mm 长焦在固定工位上具有较好的 FOV 潜力；同样需要验证 Camera API 对高分辨率、焦点和曝光的开放程度 |
| **iPhone 15** | 48MP 26mm 主摄 | **可用于 PoC / 条件认证** | 48MP 本身不构成问题；关键是 1× 主摄在约 100mm FOV 下是否能清晰对焦并获得满足 mm/px 的有效原图；不要把 2× 裁切模式当作 48MP 光学长焦使用 |
| **HONOR Magic V2** | 50MP 广角主摄；另有 50MP 超广角和 20MP 长焦 | **已有设备可测试** | 硬件像素满足候选条件，但折叠形态对固定工位没有额外价值；新采购不作为优先项，必须实测 Camera API 和目标 FOV 下对焦能力 |

当前官方规格显示：Xiaomi 15 配备 50MP 主摄；OPPO Find X9 配备 50MP 主摄和 50MP 73mm 长焦；iPhone 15 主摄为 48MP 并支持 48MP 超高分辨率照片；HONOR Magic V2 系列公开规格为 50MP 广角主摄。上述参数只用于候选筛选，**不能替代实际 Camera Qualification Test**。

### 15.2.3 主摄还是长焦：不要预先固定

对于固定工位，不能简单认为“主摄一定最好”。

23～26mm 广角主摄的优点：

- 通常传感器质量较高；
- 高分辨率模式支持相对成熟；

但为了把 FOV 压到约 100mm，可能需要手机离布面较近，从而遇到最近对焦距离限制。

60～75mm 左右的 50MP 中长焦可能更适合固定工位：

- 手机可以放得更高；
- 灯光和压布框更容易布置；
- 在不使用数字变焦的前提下更容易获得较小 FOV。

但必须确认：

> **对应长焦物理摄像头确实可以输出足够高的静态分辨率，并能被采集 App 固定调用。**

因此最终应该由 Camera Qualification Test 在候选镜头之间做实测选择，而不是仅根据等效焦距决定。

---

## 15.3 手机工位设定建议

### 15.3.1 固定关系

正式计量时必须固定：

```text
手机
↓
手机支架
↓
物理摄像头
↓
工作距离
↓
约 100×75 mm FOV
↓
压布框 / 牛仔布
↓
透射背光板
```

**工作距离本身不需要在所有手机上统一。**

不同手机的焦距和最近对焦距离不同，因此应该固定：

> **最终 FOV 和 mm/px，而不是统一规定手机必须距离布面多少毫米。**

例如不同认证工位可以是：

```text
Station A：工作距离 180 mm → FOV 99.2 mm
Station B：工作距离 235 mm → FOV 101.0 mm
```

只要两者最终都满足 Camera Profile 和 mm/px 门禁即可。

### 15.3.2 建议固定的相机参数

正式采集 App 应尽量控制并记录：

| 参数 | 建议 | 原因 |
|---|---|---|
| Physical Camera ID | **固定** | 防止系统自动切换主摄/超广角/长焦 |
| 输出分辨率 | **固定为认证模式** | 保证像素尺度不变化 |
| 数字 Zoom | **1.0 / 禁止数字变焦** | 数字裁切会破坏真实物面分辨率 |
| Focus | **标定后固定或锁定** | 防止每次自动对焦产生细节漂移 |
| Exposure Time | **固定或受控固定档** | 保证纹理和边缘稳定 |
| ISO | **固定或限定在极小范围** | 防止不同噪声水平影响边缘与周期 |
| White Balance | **固定即可** | 当前不做颜色，但固定可降低通道漂移 |
| HDR | **关闭** | 避免多帧融合改变局部纹理和边缘 |
| Night Mode | **关闭** | 避免长曝光/多帧计算摄影 |
| AI Scene Enhancement | **关闭** | 避免算法自动改变锐化、对比度和纹理 |
| Beauty/Filter | **关闭** | 计量图片不得经过美化处理 |
| Auto Macro / Auto Lens Switch | **关闭或锁定物理相机** | 防止手机自动切换镜头 |
| Flash | **关闭** | 使用外部固定反射光/背光体系 |
| File Rotation | **固定并记录方向** | 保证经向提示和算法坐标一致 |

其中曝光时间、ISO、Focus Distance 的具体数值**不要在本文预先写死**，而应在 Gate 1/工位认证时通过样布和标定板实验得到，并进入 Camera Profile。

### 15.3.3 反射光拍摄设定

拍摄正面反射图时：

```text
上方漫射 LED：ON
底部透射背光：OFF
手机闪光灯：OFF
```

目标是：

- 图像整体均匀；
- 无明显方向性阴影；
- 无局部强高光；
- 纱线表面边界和斜纹结构清晰。

### 15.3.4 透射图拍摄设定

拍摄透射图时：

```text
上方反射 LED：OFF（或降到不影响透射结构）
底部均匀背光：ON
手机闪光灯：OFF
```

目标是强化：

```text
纱线主体 ↔ 纱线间隙
```

之间的亮度差异，让周期和中心线更容易被确定性算法检测。

### 15.3.5 建议的拍摄顺序

单个位置 P1：

```text
1. 放置并压平牛仔布
2. 确认经向与工位标记一致
3. 反射光 ON / 背光 OFF
4. 拍 P1-Reflection
5. 保持手机和布完全不动
6. 反射光 OFF / 背光 ON
7. 拍 P1-Transmission
8. 上传两张原始图 + Capture Metadata
```

如果需要 P2/P3：

```text
手机、支架、相机参数、光源参数全部不动
↓
只移动样布到新的物理区域
↓
重复反射 + 透射两张采集
```

### 15.3.6 建议记录的 Capture Metadata

每张图片建议附带：

```json
{
  "station_id": "ST001",
  "phone_model": "Xiaomi 15",
  "physical_camera_id": "rear_tele_01",
  "camera_profile_id": "ST001_CAM01_V3",
  "capture_type": "reflection",
  "position_id": "P1",
  "image_width_px": 8192,
  "image_height_px": 6144,
  "mm_per_px_x": 0.0124,
  "mm_per_px_y": 0.0124,
  "focus_mode": "locked",
  "iso": 100,
  "exposure_time": "profile_value",
  "digital_zoom": 1.0,
  "warp_axis_hint": "vertical"
}
```

示例中的 ISO 等仅用于表示数据结构，实际值以对应 Camera Profile 为准。

---

## 15.4 PoC 手机与图片认证建议

对于每一种候选手机/镜头组合，建议至少完成以下试验后再进入正式 Golden Dataset：

1. **FOV 测试**：是否能稳定达到约 100×75 mm；
2. **mm/px 测试**：是否满足 ≤0.015 mm/px；
3. **对焦测试**：中央及主要 80×60 mm ROI 是否同时清晰；
4. **重复拍摄测试**：同一位置连续拍摄 10 次，图像质量指标和 Measurement 结果是否稳定；
5. **RAW/JPEG 对比**：是否存在可观测的计量偏差；
6. **反射/透射切换测试**：切灯后图像是否保持空间对齐；
7. **温升/长时间运行测试**：固定供电和连续拍摄后是否发生明显热降频、相机异常或参数漂移；
8. **API 能力测试**：能否固定 Physical Camera、分辨率、Focus、Exposure、ISO 和 Zoom；
9. **图片完整性测试**：采集端上传后是否保留原始像素尺寸和必要 Metadata；
10. **Fabric Measurement Benchmark**：至少对一批 Ground Truth 样布验证经密、纬密和表观宽度结果。

最终通过的组合形成：

```text
Certified Phone / Camera Profile
```

Fabric Measurement Engine 只接受绑定认证 Profile 的正式生产图片。

---

## 15.5 本附录的最终建议

当前阶段可以把手机和图片采集原则压缩成以下几句话：

> 1. **优先使用固定 48/50MP 手机作为视觉传感器，而不是人工手持拍摄。**  
> 2. **标准计量图应由受控采集端直接产生，禁止使用社交软件压缩图、截图和网络图进行正式计量。**  
> 3. **手机型号不是最终门槛，真正门槛是约 100×75 mm FOV、≤0.015 mm/px、整体清晰和稳定重复。**  
> 4. **固定 Physical Camera、Focus、Exposure、ISO 和 Zoom；关闭 HDR、夜景、AI增强、自动切镜头和手机闪光灯。**  
> 5. **每个位置依次采集正面反射图和透射图，切换光源时手机和布都不移动。**  
> 6. **PoC 保留 RAW/JPEG 对照；正式生产格式通过 Benchmark 决定，不为了“RAW更专业”而无条件承担约几十 MB/张的存储和计算成本。**

