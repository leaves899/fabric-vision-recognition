#!/usr/bin/env python3
"""Join four independent 130-photo GitHub Actions jobs into a reproducible report."""
from __future__ import annotations
import argparse
import csv
import json
import math
from pathlib import Path
import cv2
import numpy as np

ANGLES=(0,90,180,270)
IMPORTANT=("W120","W115","W119","W067","W068","W070","W071",
           "W035","W095","W092","W008","W112","W032","W069","W108")
def load_csv(path):
    with path.open("r",encoding="utf-8-sig",newline="") as stream:
        return list(csv.DictReader(stream))
def number(value):
    try:
        x=float(value)
        return x if math.isfinite(x) else None
    except (TypeError,ValueError):
        return None
def mean(values):
    z=[v for v in values if v is not None]
    return round(float(np.mean(z)),4) if z else None
def circ_diff(a,b):
    x,y=number(a),number(b)
    return round(abs((x-y+90)%180-90),3) if x is not None and y is not None else None
def metrics(row):
    if not row: return {}
    return {k: number(row.get(k)) if k not in ("status","failure_reasons") else row.get(k)
            for k in ("warp_density_per_cm","weft_density_per_cm","warp_rel_error_pct","weft_rel_error_pct",
                      "warp_direction_original","weft_direction_original",
                      "warp_lines","weft_lines","status","failure_reasons")}
def composite(src, filename, output):
    tiles=[]
    for angle in ANGLES:
        img=cv2.imread(str(src / f"fabricnet-rot-angle-{angle}" / "overlays_original_coords" / filename))
        if img is None:
            raise RuntimeError("MISSING_EVIDENCE:"+filename+":"+str(angle))
        if img.shape[:2]!=(480,640):
            raise RuntimeError("ROTATION_INVERSION_GEOMETRY_MISMATCH:"+filename+":"+str(angle))
        y=img.copy()
        title=f"{filename} input={angle} deg (overlays back in ORIGINAL coords)"
        cv2.rectangle(y,(0,0),(639,29),(10,10,10),-1)
        cv2.putText(y,title,(4,19),cv2.FONT_HERSHEY_SIMPLEX,.46,(255,255,255),1,cv2.LINE_AA)
        tiles.append(y)
    panel=np.concatenate((np.concatenate(tiles[:2],axis=1),
                          np.concatenate(tiles[2:],axis=1)),axis=0)
    output.parent.mkdir(parents=True,exist_ok=True)
    if not cv2.imwrite(str(output),panel,[cv2.IMWRITE_JPEG_QUALITY,94]):
        raise RuntimeError("COMPOSITE_WRITE_FAILED")
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--inputs",required=True,type=Path)
    ap.add_argument("--out",required=True,type=Path)
    args=ap.parse_args()
    args.out.mkdir(exist_ok=True,parents=True)
    sets={}
    sums={}
    for angle in ANGLES:
        path=args.inputs / f"fabricnet-rot-angle-{angle}"
        records=load_csv(path/"metrics.csv")
        summary=json.loads((path/"summary.json").read_text(encoding="utf-8"))
        if len(records)!=130 or summary["n_total"]!=130 or summary["angle"]!=angle:
            raise RuntimeError(f"INCOMPLETE_ROTATION_{angle}")
        if len({r["image"] for r in records})!=130:
            raise RuntimeError("DUPLICATE_IMAGE_ROWS_"+str(angle))
        if set(r["image"] for r in records)!=set(f"W{i:03d}.jpg" for i in range(1,131)):
            raise RuntimeError("INCORRECT_FABRICNET_IMAGE_SET_"+str(angle))
        sets[angle]={r["image"]:r for r in records}
        sums[angle]=summary
    for i in sets[0]:
        hashes={sets[angle][i]["source_sha256"] for angle in ANGLES}
        if len(hashes)!=1:
            raise RuntimeError("ROTATED_INPUT_MUST_DERIVE_FROM_SAME_ORIGINAL_"+i)
        gt={(sets[a][i]["truth_warp"],sets[a][i]["truth_weft"],sets[a][i]["truth_texture"]) for a in ANGLES}
        if len(gt)!=1:
            raise RuntimeError("TRUTH_SWAP_OR_MISMATCH_"+i)
    output=[]
    for name in sorted(sets[0]):
        baseline=sets[0][name]
        record={"image":name,"truth_texture":baseline["truth_texture"],
                "truth_warp":baseline["truth_warp"],"truth_weft":baseline["truth_weft"]}
        for angle in ANGLES:
            x=sets[angle][name]
            record.update({f"{k}_{angle}":x.get(k) for k in (
                "status","warp_density_per_cm","weft_density_per_cm",
                "warp_abs_error","weft_abs_error","warp_rel_error_pct","weft_rel_error_pct",
                "warp_direction_original","weft_direction_original","warp_lines","weft_lines",
                "both_within_10pct")})
        for angle in (90,180,270):
            for family in ("warp","weft"):
                error_0=number(baseline.get(family+"_rel_error_pct"))
                error_a=number(sets[angle][name].get(family+"_rel_error_pct"))
                density_0=number(baseline.get(family+"_density_per_cm"))
                density_a=number(sets[angle][name].get(family+"_density_per_cm"))
                record[f"{family}_relative_error_change_{angle}_minus_0_pct_points"]=(
                    round(error_a-error_0,4) if error_a is not None and error_0 is not None else None)
                record[f"{family}_density_rotation_delta_{angle}_minus_0_per_cm"]=(
                    round(density_a-density_0,4) if density_a is not None and density_0 is not None else None)
                record[f"{family}_axis_inconsistency_{angle}_vs_0_deg"]=circ_diff(
                    baseline.get(family+"_direction_original"),
                    sets[angle][name].get(family+"_direction_original"))
            original=float(baseline["both_within_10pct"]) if baseline["both_within_10pct"] else 0
            current=float(sets[angle][name]["both_within_10pct"]) if sets[angle][name]["both_within_10pct"] else 0
            record[f"both10_improvement_{angle}_minus_0"]=int(current-original)
        output.append(record)
    with (args.out/"rotation_comparison.csv").open("w",encoding="utf-8-sig",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=list(output[0].keys()))
        writer.writeheader();writer.writerows(output)
    summary={
        "n_images":130,
        "rotations":{str(a):sums[a] for a in ANGLES},
        "axis_diagnostics":{},
        "cautions":[
            "Physically same warp/weft across 90-degree turns, hint and axes swapped as required",
            "Original pixels rotated with OpenCV exact quarter turns without image resize",
            "The input is one microscope photo twice, NOT actual reflection/transmission",
            "No physical fiber-identity GT; matching track F1 cannot be computed",
            "Density and decision stability != correctness of underlying yarn centerlines",
            "Not a certified 8K 50mm frame test",
        ]}
    for angle in (90,180,270):
        summary["axis_diagnostics"][str(angle)]={
            "mean_abs_warp_density_change_per_cm":mean([abs(number(r[f"warp_density_rotation_delta_{angle}_minus_0_per_cm"])) for r in output if number(r[f"warp_density_rotation_delta_{angle}_minus_0_per_cm"]) is not None]),
            "mean_abs_weft_density_change_per_cm":mean([abs(number(r[f"weft_density_rotation_delta_{angle}_minus_0_per_cm"])) for r in output if number(r[f"weft_density_rotation_delta_{angle}_minus_0_per_cm"]) is not None]),
            "mean_warp_original_angle_diff_deg":mean([number(r[f"warp_axis_inconsistency_{angle}_vs_0_deg"]) for r in output]),
            "mean_weft_original_angle_diff_deg":mean([number(r[f"weft_axis_inconsistency_{angle}_vs_0_deg"]) for r in output]),
            "warp_error_reduced_n":sum(number(r[f"warp_relative_error_change_{angle}_minus_0_pct_points"]) is not None and number(r[f"warp_relative_error_change_{angle}_minus_0_pct_points"])<0 for r in output),
            "weft_error_reduced_n":sum(number(r[f"weft_relative_error_change_{angle}_minus_0_pct_points"]) is not None and number(r[f"weft_relative_error_change_{angle}_minus_0_pct_points"])<0 for r in output),
            "both10_improved_n":sum(r[f"both10_improvement_{angle}_minus_0"]>0 for r in output),
            "both10_worsened_n":sum(r[f"both10_improvement_{angle}_minus_0"]<0 for r in output),
        }
    (args.out/"rotation_summary.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding="utf-8")
    special=set(IMPORTANT)
    for name in sorted(special):
        composite(args.inputs, name+".jpg", args.out/"visual_4up"/(name+"_rot4.jpg"))
    def worst_max(x):
        return max(number(x.get("warp_rel_error_pct_0")) or 0, number(x.get("weft_rel_error_pct_0")) or 0)
    worst=sorted(output,key=worst_max,reverse=True)[:20]
    for row in worst:
        name=row["image"].split(".")[0]
        if name not in special:
            composite(args.inputs,row["image"],args.out/"visual_4up"/(name+"_rot4.jpg"))
    lines=[
      "# FabricNET 130 张 × 0°/90°/180°/270°旋转鲁棒性盲测",
      "",
      "基于同一GitHub仓库源算法、独立推理四组；原图物理纱线身份及密度真值在每个角度都不换名。所有覆盖图逆旋回原图坐标，可逐线对照。",
      "注意：单显微照片重复传历史双输入API，不是真R/T采集；无每根物理纱线的曲线GT，不计算单根线的物理F1。",
      "",
      "| 输入旋转角 | 有数值图数 | PASS | 经密MAE | 纬密MAE | 经密MAPE | 纬密MAPE | 双向≤10% | PASS且双向≤10% |",
      "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for a in ANGLES:
        s=sums[a]
        lines.append(f"| {a}° | {s['n_numeric']}/130 | {s['n_pass']} | {s['warp_mae']} | {s['weft_mae']} | {s['warp_mape']}% | {s['weft_mape']}% | {s['both_10']} | {s['pass_both_10']} |")
    lines.extend(["",
        "## 与0°对照：相同物理纱线保持同一身份；经纬名称不随屏幕横竖变更",
        "",
        "| 比较 | 经密绝对变化均值 根/cm | 纬密绝对变化均值 根/cm | 经向校正后角差 ° | 纬向校正后角差 ° | 纬密相对误差变小的图片数 | 双向≤10%新增/失去 |",
        "|---|---:|---:|---:|---:|---:|---:|"])
    for a in (90,180,270):
        v=summary["axis_diagnostics"][str(a)]
        lines.append(f"| {a}° vs 0° | {v['mean_abs_warp_density_change_per_cm']} | {v['mean_abs_weft_density_change_per_cm']} | {v['mean_warp_original_angle_diff_deg']} | {v['mean_weft_original_angle_diff_deg']} | {v['weft_error_reduced_n']}/130 | +{v['both10_improved_n']}/-{v['both10_worsened_n']} |")
    lines.extend(["","## 上一轮最差20张：旋转后误差变化 (百分比绝对值)",
                  "","负数=相对误差降低；正数=误差增加。",
                  "","| 图片 | 原图经/纬相对误差% | 90°经/纬相对误差% | 180°经/纬相对误差% | 270°经/纬相对误差% | 视觉对照 |",
                  "|---|---:|---:|---:|---:|---|"])
    for r in worst:
        name=r["image"].split(".")[0]
        vals=["{}/{}".format(r[f"warp_rel_error_pct_{angle}"],r[f"weft_rel_error_pct_{angle}"])
              for angle in ANGLES]
        lines.append(f"| {name} | {vals[0]} | {vals[1]} | {vals[2]} | {vals[3]} | [原图坐标四联图](visual_4up/{name}_rot4.jpg) |")
    lines+=["","## 文件",
        "- rotation_comparison.csv：130张逐图×4角度，方向、密度、质量门、旋转差值；保留全部低置信度与失败图",
        "- rotation_summary.json：四组汇总 + 相对0°的方向、密度稳定性统计",
        "- visual_4up：先前最差20张+关键案例四联图（每条线为原算法输出、逆旋回原始坐标）",
        "- 每个角度完整130张结果及覆盖图另存 GitHub Actions artifacts",
        "","## 判读规范",
        "若90°显著改善纬密但180°稳定，可能存在纵横流程方向偏置；若180°也大幅变化则同方向反向不稳定；若四角都在同一样本出现半周期/倍周期失效，则问题更可能是光学纹理与物理纱线混淆。**以上应由数据支持后才作为结论**。"
    ]
    (args.out/"rotation_summary.md").write_text("\n".join(lines)+"\n",encoding="utf8")
    print("AGGREGATED_ROTATION_SUMMARY "+json.dumps({k:v for k,v in summary.items() if k!="rotations"},ensure_ascii=False),flush=True)
    for a in ANGLES:
        print("ANGLE_METRIC "+str(a)+" "+json.dumps(sums[a],ensure_ascii=False),flush=True)

if __name__=="__main__":
    main()
