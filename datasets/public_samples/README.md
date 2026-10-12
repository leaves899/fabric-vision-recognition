# 公开织物实物图像样本集

**45 张开放许可织物实物图像已进入样本清单**，GitHub Actions 将真实源图下载到 `images/`；以 [sync_status.json](sync_status.json) 中 `available` 与 `complete` 为准确认已落库数量。样本包括普通相机、手机拍照、高分辨率扫描和馆藏织物记录。

- [图片目录](images/) · [来源与版权](sources.json) · [SHA-256 校验](checksums.sha256)
- [实时导入状态](sync_status.json)：`expected`、`available`、`pending_ids`
- 下载脚本：`scripts/fetch_public_samples.py`，仅保留 Wikimedia Commons 原始文件，不进行生成式加工。
- 本目录只适合算法**探索、候选标注和回归**，不是经纬密度的正式计量标定数据集。

## 图片列表（45）

### 平纹、不同颜色与纤维（19 张）

| 编号 | 图片 | 组织弱标签 | 来源/许可 | 用途限制 |
|---|---|---|---|---|
| P001 | [Simple-textile-magnified.jpg](images/plain/01_simple_textile_magnified.jpg) | 平纹候选 | Edal (Anton Lefterov) · [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/) | 放大平纹近景；物理纱线身份、经纬方向未标注 |
| P002 | [Plain Weaving Detail.JPG](images/plain/02_plain_weaving_detail.jpg) | 平纹候选 | Paulo Roberto C M Jr. · [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/) | 高分辨率平纹摄影；适用于粗细、排列候选 |
| P003 | [Close-up of plain weave (24293165153).jpg](images/plain/03_closeup_plain_weave.jpg) | 平纹候选 | terri_bateman · [CC BY 2.0](https://creativecommons.org/licenses/by/2.0/) | 公开页面标记为 plain weave；960×528，适合轻量测试 |
| P004 | [Blue chambray cloth.JPG](images/plain/04_blue_chambray_with_mm_scale.jpg) | 平纹候选 | Edward G. FitzGerald · [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/) | 水洗蓝色棉质青年布，图中有毫米刻度；用于方向/排列/尺度实验（并非5cm实物框） |
| P005 | [Blue end-on-cloth with white stripes.JPG](images/plain/05_striped_end_on_end_with_mm_scale.jpg) | 平纹候选 | Edward G. FitzGerald · [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/) | 蓝白条纹平纹候选，带毫米刻度；检测颜色条纹对经纬方向的干扰 |
| P006 | [Calico Sample.JPG](images/plain/06_calico_with_cm_scale.jpg) | 平纹候选 | Clem Rutter · [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/) | 印花袋用棉布，有厘米刻度；辅助标尺计算，不是标准5cm框 |
| P007 | [Leinengewebe.JPG](images/plain/07_linen_weave.jpg) | 平纹候选 | Dee.lite · [Public domain](https://commons.wikimedia.org/wiki/File:Leinengewebe.JPG) | 亚麻近景，天然不均匀粗纱排列 |
| P008 | [Greengingham.jpg](images/plain/08_green_gingham.jpg) | 平纹候选 | Kent Wang · [CC BY-SA 2.0](https://creativecommons.org/licenses/by-sa/2.0/) | 绿白方格布真实摄影；颜色方格并不等同组织结构 |
| P009 | [Blue cordura garment.jpg](images/plain/09_blue_cordura_closeup.jpg) | 平纹候选 | Apapadop · [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/) | 深蓝 Cordura 织物近景；低光、低饱和度检验 |
| P010 | [Linen canvas.jpg](images/plain/10_linen_canvas_reverse.jpg) | 平纹候选 | JohanahoJ · [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) | 亚麻油画布背面；明显经纬纱方向 |
| P011 | [Loosen Plain Weave.jpg](images/plain/11_loose_plain_weave.jpg) | 平纹候选 | Deepika Govindaraj · [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | 疏松平纹实拍；宽间隙和小样图 |
| P012 | [Plain Weave Using Dyed Yarns.jpg](images/plain/12_plain_weave_dyed_yarns.jpg) | 平纹候选 | Deepika Govindaraj · [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | 染色纱线平纹；颜色变化与真实纱线走向区分 |
| P013 | [Plain Weave Using Pink Yarn.jpg](images/plain/13_plain_weave_pink.jpg) | 平纹候选 | Deepika Govindaraj · [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | 粉色纱线平纹；彩色纱线细节回归 |
| P014 | [Selvage edge.jpg](images/plain/14_selvage_edge.jpg) | 平纹候选 | Dvortygirl · [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/) | 布料布边及印花干扰样本；边缘不应参与中心 ROI 统计 |
| P015 | [Glass fabric.jpg](images/plain/15_glass_fabric_with_ruler.jpg) | 平纹候选 | Cjp24 · [Public domain](https://commons.wikimedia.org/wiki/File:Glass_fabric.jpg) | 玻璃纤维平纹实物照片，附硬币及尺；可做附加尺度实验但非5cm实体框 |
| P016 | [Fibreglass fabric 1100g per m2.jpg](images/plain/16_fiberglass_high_density_scan.jpg) | 平纹候选 | Achim Hering · [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/) | 高分辨率扫描真实玻璃纤维布；扫描成像不代表手机摄影 |
| P017 | [Fukui Habutae Silk.jpg](images/plain/17_habutae_silk.jpg) | 平纹候选 | UFringo · [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) | 羽二重丝绸实拍；较细织物及高反光测试，若纱线未解析则仅作纹理测试 |
| P018 | [Carhartt logo tab Rugged Flex Duck fabric (2026-01-16).jpg](images/plain/18_iphone_cotton_duck_with_logo.jpg) | 平纹候选 | Olgierd Rudak · [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/) | iPhone17 Pro 拍摄厚棉帆布，包含商标织唛；必须裁剪织物 ROI |
| P019 | [Weave.jpg](images/plain/19_cotton_painter_canvas.jpg) | 平纹候选 | Henningklevjer~commonswiki · [CC BY-SA 2.5](https://creativecommons.org/licenses/by-sa/2.5/) | 棉质油画布真实相机近景，适合纹理与直交候选线 |

### 斜纹、牛仔、花呢与破斜纹（12 张）

| 编号 | 图片 | 组织弱标签 | 来源/许可 | 用途限制 |
|---|---|---|---|---|
| T001 | [Denim-closeup.jpg](images/twill/01_denim_closeup.jpg) | 斜纹候选 | Ultrasleeper2 · [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/) | 牛仔布斜纹近景；需警惕斜纹纹路干扰纱线方向 |
| T002 | [Tartan cloth closeup.jpg](images/twill/02_tartan_2x2_closeup.jpg) | 2/2斜纹 | SMcCandlish · [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/) | 来源页面说明为 2/2 斜纹格纹；可测试色条与真实纱线区分 |
| T003 | [Twill weave.JPG](images/twill/03_twill_blanket.jpg) | 斜纹候选 | Sfuarch480 · [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/) | 毛毯斜纹摄影，适合挑战样本 |
| T004 | [Close-up of Denim Fabric.jpg](images/twill/04_phone_denim_detail.jpg) | 斜纹候选 | Andreiflorea993 · [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) | Pixel 手机拍摄牛仔布近景，贴近手机场景；无 5cm 标定框 |
| T005 | [Undyed denim cotton broken twill.jpg](images/twill/05_undyed_broken_twill_iphone.jpg) | 破斜纹 | Olgierd Rudak · [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) | 来源明确标注未染色破斜纹牛仔布，iPhone14照片；检验斜向纹理误识别 |
| T006 | [Broken twill denim Wrangler 13MWZ jeans (2026-01-21).jpg](images/twill/06_wranger_broken_twill_inside_outside.jpg) | 破斜纹 | Olgierd Rudak · [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) | 同一图片展示破斜纹牛仔布内外面；并非两个独立配准文件 |
| T007 | [Jeansfabric.jpg](images/twill/07_jeans_fabric.jpg) | 斜纹候选 | Thegreenj · [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/) | 高分辨率牛仔织物摄影 |
| T008 | [Chino pants close-up - DSC02850.JPG](images/twill/08_chino_pants_closeup.jpg) | 待确认 | Daderot · [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/) | 棉布斜纹/斜纹候选需复核；不要将chino服装名称当作组织真值 |
| T009 | [Goudlaken keperbinding voorzijde.jpg](images/twill/09_gold_twill_front.jpg) | 斜纹候选 | Marikevanroon20 · [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/) | 金线斜纹正面；与T010为对应背面但未图像配准 |
| T010 | [Goudlaken keperbinding achterzijde.jpg](images/twill/10_gold_twill_back.jpg) | 斜纹候选 | Marikevanroon20 · [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/) | 金线斜纹背面；与T009同类正面记录，未做物理对应点标注 |
| T011 | [Genuine Irish Thornproof tweed jacket (2025-11-22) 2.jpg](images/twill/11_irish_tweed_phone_2.jpg) | 花呢（组织待确认） | Olgierd Rudak · [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) | iPhone14 花呢近景；明确标注花呢，不假设其组织规格 |
| T012 | [Genuine Irish Thornproof tweed jacket (2025-11-22) 3.jpg](images/twill/12_irish_tweed_phone_3.jpg) | 花呢（组织待确认） | Olgierd Rudak · [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) | 同种花呢不同取景；作为同布料组内鲁棒性样本，勿当独立布料 |

### 人字纹（3 张）

| 编号 | 图片 | 组织弱标签 | 来源/许可 | 用途限制 |
|---|---|---|---|---|
| H001 | [12 x 12 Herringbone.jpg](images/herringbone/01_harris_12x12_herringbone.jpg) | 人字纹 | Callicvol · [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/) | 12x12人字纹近景；结构反转对纹理估角形成挑战 |
| H002 | [HerringbonePatternCloth.jpg](images/herringbone/02_herringbone_pattern_cloth.jpg) | 人字纹 | Thermos · [CC BY-SA 2.5](https://creativecommons.org/licenses/by-sa/2.5/) | 人字纹布料实拍，适合测试真实纱线方向与表面V字纹的区分 |
| H003 | [Herringbone Twill .jpg](images/herringbone/03_herringbone_twill_jacket.jpg) | 人字纹 | Django Retroman · [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) | 旧军装人字斜纹织物特写；测试局部线方向与V型纹理区别 |

### 缎纹、条纹缎（4 张）

| 编号 | 图片 | 组织弱标签 | 来源/许可 | 用途限制 |
|---|---|---|---|---|
| S001 | [Goudlaken satijnbinding voorzijde.jpg](images/satin/01_gold_satin_front.jpg) | 缎纹候选 | Marikevanroon20 · [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/) | 金线缎纹正面；与S002为对应背面说明，未配准 |
| S002 | [Goudlaken satijnbinding achterzijde.jpg](images/satin/02_gold_satin_back.jpg) | 缎纹候选 | Marikevanroon20 · [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/) | 金线缎纹背面；无交织点真值 |
| S003 | [Textile (Lyons, France), 19th century (CH 18569575).jpg](images/satin/03_fancy_satin_lyons_historic.jpg) | 缎纹候选 | Cooper Hewitt Smithsonian Design Museum / artist unknown · [Public domain](https://creativecommons.org/publicdomain/mark/1.0/) | 素色丝织物平纹与变化缎纹条带、叶纹；馆藏平面摄影不等于手机近拍，供纹理及组织候选分析 |
| S004 | [Textile, 17th century (CH 18344851).jpg](images/satin/04_warp_faced_satin_historic.jpg) | 缎纹候选 | Cooper Hewitt Smithsonian Design Museum / artist unknown · [Public domain](https://creativecommons.org/publicdomain/mark/1.0/) | 亚麻纬纱被丝绸经纱遮盖的缎纹；花纹条带是明显干扰，馆藏摄影 |

### 复杂织物、织锦与干扰纹理（6 张）

| 编号 | 图片 | 组织弱标签 | 来源/许可 | 用途限制 |
|---|---|---|---|---|
| X001 | [Corduroy fabric.jpg](images/complex/01_corduroy_shirt.jpg) | 灯芯绒 | ArielGlenn · [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/) | 灯芯绒绒条不是经纬单根纱线；防误判挑战 |
| X002 | [5-wale.corduroy.(trenkercord).macro.jpg](images/complex/02_five_wale_corduroy_macro.jpg) | 灯芯绒 | Mariano-J · [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/) | 五条粗畦灯芯绒，存在拉链与饰边，建议裁剪有效ROI |
| X003 | [Glen Plaid aka Prince of Wales check pattern.JPG](images/complex/03_prince_of_wales_plaid.jpg) | 花格纹 | Garik 11 · [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/) | 威尔士亲王格纹，花纹周期不同于真实纱线周期 |
| X004 | [Coverlet weave.jpg](images/complex/04_woven_coverlet.jpg) | 复杂机织 | Paula Kate Marmor (PKM) · [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/) | 蓝白羊毛/棉复杂机织床罩，带提花效果；非严格提花组织真值 |
| X005 | [Brocade Textile MET 0950967.jpg](images/complex/05_metal_thread_brocade_met.jpg) | 织锦 | The Metropolitan Museum of Art / original artist unknown · [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/) | 丝/金属丝复杂织锦实物馆藏照片；低细节全幅仅可测试色纹及组织候选，不用于每根纱线定位 |
| X006 | [Brocade Textile MET 2823.jpg](images/complex/06_brocade_met_2823.jpg) | 织锦 | The Metropolitan Museum of Art / original artist unknown · [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/) | 丝/金属丝织锦馆藏摄影；不能当组织结构或经纬密度真值 |

### 待确认（1 张）

| 编号 | 图片 | 组织弱标签 | 来源/许可 | 用途限制 |
|---|---|---|---|---|
| U001 | [Fabric close up.jpg](images/unknown/01_fabric_close_up.jpg) | 待确认 | Mia Gaitanidis · [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) | 布料近景；组织未确认，不能当作训练真值 |

## 数据集标注与防误用

1. **核心近景样本**：真实织物/纱线纹理清晰时，可用于候选方向、排列、粗细、组织、色系的视觉测试。手机照片在 `capture_type=phone` 里标出（仅新增批次有此字段）。
2. **补充样本**：`capture_type=scan` 属于扫描实物织物，不等同手机相机采集；`capture_type=museum` 是**真实历史织物的整体记录照片**，主要适合图案、色系和组织类别候选，**不应用于单纱中心线或纱密计量**。
3. **弱标签不是组织真值**：`weave_candidate` 来自文件说明及类别；牛仔、花呢、缎纹等仅是来源层面候选，不可由视觉猜测 3/1 左右斜或直接当作测试真值。
4. **无正式标尺**：`has_5cm_calibration_frame=false` 的所有照片均未满足项目标准采集条件——实体方框与布料同平面、内径实测 5cm×5cm。P004/P005/P006/P015 的其它刻度信息只可做额外尺度研究。
5. **无经纬物理身份和密度真值**：`warp_weft_identity_confirmed=false`、`density_ground_truth=false`，不能用视觉数线替代人工测量；已有正反面相关图也未严格配准。
6. 原始图片允许真实织物不清晰、图样比纱线更醒目的情况；先用可见纹理质量筛选 ROI，再测算法，不能把原图元数据当人工校验结论。

## 十项目标与当前样本的关系

| 项目 | 当前用途 |
|---|---|
| 1–2 经/纬方向与角度 | 只能校核两组视觉纱向候选与人工参考方向；不能自动确认经/纬身份 |
| 3–4 经纬排列状态 | 近景 ROI 可人工比对排列规则 |
| 5–6 经纬纱粗细候选 | 可做相对粗细候选；没有对应纱支真值 |
| 7 组织结构候选 | 可进行平纹/斜纹/破斜/人字/缎纹/织锦等弱标签的人工复核 |
| 8–9 经密/纬密 | **不满足 5×5cm 同平面实体框要求，不可正式验收** |
| 10 表面纹理与色系 | 可以进行光照、颜色与图案干扰回归 |

## 复现与许可

```bash
python -m pip install Pillow
python scripts/fetch_public_samples.py
cd datasets/public_samples
sha256sum -c checksums.sha256
```

个别手机 `.jpg` 文件可能包含 MPO/JPEG 兼容结构。原图保留字节与 SHA-256，切勿隐式变更后仍称为源图。每张照片按 [sources.json](sources.json) 对应的第三方许可使用；CC BY/CC BY-SA 按许可署名、指向许可并注明改动，ShareAlike 衍生作品还须满足相同方式共享要求。仓库源码的 LICENSE 不覆盖第三方图片。
