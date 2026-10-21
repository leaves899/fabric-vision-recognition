from __future__ import annotations
"""No comparison results are fabricated; aggregate the two GitHub Actions JSON.

A single generated image provides 9 correlated measurement windows. The
reported F1 describes local physical-yarn centres, not yarn identity or the
full ten-parameter industrial acceptance test.
"""
import argparse,json,shutil
from pathlib import Path


EXPECTED={"plain_photo_flat":"plain","twill31_photo_flat":"twill_3_1"}
ARMS=("V063_FULL","INTEGER_LOCAL","FLOAT_LOCAL","SHARED_SEVEN","INDIVIDUAL_SEVEN")


def publish(src,dest):
    files=sorted(src.rglob("comparison.json"))
    cases={}
    for p in files:
        row=json.loads(p.read_text(encoding="utf-8"))
        name=row.get("case")
        if name not in EXPECTED or name in cases:
            raise RuntimeError("UNEXPECTED_OR_DUPLICATE_CASE")
        if row.get("status")!="MEASURED":
            raise RuntimeError("INCOMPLETE_MEASUREMENT: "+name+" "+str(row.get("status")))
        if row.get("GT_only_weave")!=EXPECTED[name]:
            raise RuntimeError("SCENE_GT_WRONG")
        if len(row["windows"])!=9:
            raise RuntimeError("NINE_IDENTICAL_ROI_WINDOWS_REQUIRED")
        if len(row["input_hash_sha256"]["reflection"])!=64 or len(row["input_hash_sha256"]["transmission"])!=64:
            raise RuntimeError("INPUT_HASH_MISSING")
        cases[name]=(row,p)
    if set(cases)!=set(EXPECTED):raise RuntimeError("BOTH_FIXED_CASES_REQUIRED")
    dest.mkdir(parents=True,exist_ok=True)
    lines=[
        "# 真实照片颜色参考合成的平铺8K双图：原版V0.6.3 vs 优化算法",
        "",
        "**两组均使用上一轮已冻结的原生8000×6000反射/透射照片，无图像旋转；一组平纹、一组3/1斜纹，纱线真实标签只在全部方法推理完成后读取。**",
        "反射外观来自实拍参考U20261013_05.jpg的颜色统计及细粒度噪声；透射为模拟，不能称作实物工位拍照。",
        "",
        "统一评分：标定框同一九个520px局部窗口，中心截面上与真实物理纱线的**门限内最大一对一**匹配。",
        "容许差=0.32倍真实纱距。宏平均为九个窗口F1的平均，Micro-F1按所有窗口匹配根数之和计算。",
        "V0.6.3保留原有全图自动方向入口；局部优化法使用工位0°对齐已知方向，因此不应声称自动方向精度提升。",
        "",
        "## 同区域纱线中心正确率",
        "",
        "| 样本 | 经/纬 | 原版V0.6.3 | 原整数局部 | 浮点局部 | 7截线共同相位 | 逐根局部追踪 |",
        "|---|---|---:|---:|---:|---:|---:|"]
    for scene,(row,p) in cases.items():
        for fam in ("warp","weft"):
            byarm=row["summaries"][fam]
            lines.append("| "+scene+" | "+("经" if fam=="warp" else "纬")+" | "+
                " | ".join(f"{byarm[v]['mean_f1_9_windows']:.4f}" for v in ARMS)+" |")
    lines+=["","## 自动经纬密度对照","",
            "| 样本 | 方向 | 合成物理真值(根/cm) | 原版输出(根/cm) | 原版相对误差 | 优化浮点候选(根/cm) | 优化候选相对误差 |",
            "|---|---|---:|---:|---:|---:|---:|"]
    for scene,(row,p) in cases.items():
        d=row["density"]
        for fam in ("warp","weft"):
            gt=d["truth_per_cm"][fam]
            old=d["V063_FULL"][fam]
            new=d["FLOAT_LOCAL"][fam]
            oe=d["V063_FULL_abs_pct_error"][fam]
            ne=d["FLOAT_LOCAL_abs_pct_error"][fam]
            lines.append(f"| {scene} | {fam} | {gt:.2f} | "
                f"{old if old is not None else '未输出'} | "
                f"{str(oe)+'%' if oe is not None else '—'} | "
                f"{new if new is not None else '未输出'} | "
                f"{str(ne)+'%' if ne is not None else '—'} |")
    lines+=["","## 原版全图门禁/能力区分",""]
    for name,(row,p) in cases.items():
        orig=row["original"]
        lines.append(f"- **{name}**：V0.6.3状态`{orig['status']}`；原版全图耗时{orig['runtime_seconds']}秒；优化各局部候选总耗时{row['optimized_window_inference_seconds']}秒。")
        if orig.get("reasons"):lines.append("  - 原版原因："+str(orig["reasons"]))
        angle=orig.get("orientation") or {}
        lines.append("  - 原版自动方向："+str({k:v for k,v in angle.items() if "direction_deg" in k}))
        tw=orig.get("twill") or {}
        lines.append("  - 原版组织诊断（未做规范归类准确率验证）："+json.dumps(tw,ensure_ascii=False)[:1400])
    lines+=["","## 质量控制与结论边界","",
        "- 所有覆盖图都使用真实算法计算出来的中心线，并与物理真值画在**同一个中央窗口**；全图9窗口统计同时保留在JSON中。",
        "- 若原版输出FAIL，应视作拒识，不以内部未通过门禁的候选作为业务正确结果。",
        "- 九个窗口来自同一张图，不是九张独立实拍照片；本报告只有两组**合成场景**。",
        "- 原版自动经纬角、组织类型及优化版的纱线中心不能简单加权为系统整体10项正确率。",
        "- 若某方法无候选，其F1记为0而非跳过；只有算法真实输出可被评分。",
        "- 实体追踪身份在遮挡后的正确与否，需要额外使用严格物理ID轨迹评分；本报告的中心线F1不代表同根追踪可靠性。",
        "- 图像真实纱线外观尚不充分，真实相机8000×6000双光工位的泛化精度**未知**。",
        ""]
    packaged={}
    for name,(row,p) in cases.items():
        for fn in ("actual_algorithm_same_region_AB.jpg",
                   "input_R_center_520px.jpg","input_T_center_520px.jpg"):
            im=p.parent/fn
            if not im.is_file():raise RuntimeError("MISSING_ACTUAL_PREDICTION_IMAGE_"+str(im))
            shutil.copy2(im,dest/(name+"_"+fn))
        packaged[name]={k:v for k,v in row.items() if k!="windows"}
        shutil.copy2(p,dest/(name+"_all_nine_windows.json"))
    (dest/"AB_REPORT.md").write_text("\n".join(lines),encoding="utf-8")
    (dest/"summary.json").write_text(json.dumps(packaged,indent=2,ensure_ascii=False),encoding="utf-8")
    print("FLAT_AB_VERIFIED "+json.dumps({
        "cases":list(cases),
        "outcomes":{scene:{fam:{arm:row["summaries"][fam][arm]["mean_f1_9_windows"]
                               for arm in ARMS} for fam in ("warp","weft")}
                    for scene,(row,p) in cases.items()}},ensure_ascii=False),flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--artifacts",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    a=parser.parse_args()
    publish(a.artifacts,a.out)
