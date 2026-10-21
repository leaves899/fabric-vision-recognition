#!/usr/bin/env python3
"""Pre-registered paired 130-photo ablation analysis with bootstrap CIs.

The 2x2 comparisons isolate 'fixed angle' and 'input rotation to horizontal
detector' on the same frozen single-direction engine. An extra 270-deg rotated
horizontal control audits reverse orientation instability.
"""
from __future__ import annotations
import argparse
import csv
import json
from pathlib import Path

import cv2
import numpy as np
from scipy.stats import binomtest

ARMS=("DIRECT_FIXED","ROT90_FIXED","DIRECT_ESTIMATED",
      "ROT90_ESTIMATED","ROT270_FIXED")
CASES=("W120","W115","W119","W035","W067","W095","W105","W112",
       "W032","W037","W008","W068","W070","W071","W092","W069",
       "W109","W108","W096","W028")
def csv_rows(filename):
    with Path(filename).open("r",encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f))
def nn(x):
    try:
        z=float(x)
        return z if np.isfinite(z) else None
    except (TypeError,ValueError):
        return None
def boot_ci(diffs,seed):
    # Paired bootstrap over image IDs; intervals for mean(new-old) changes.
    vals=np.asarray(diffs,dtype=np.float64)
    if not len(vals):return None
    rng=np.random.default_rng(seed)
    n=len(vals)
    out=np.empty(5000,dtype=float)
    for j in range(len(out)):
        out[j]=float(np.mean(vals[rng.integers(n,size=n)]))
    return [round(float(np.quantile(out,0.025)),5),round(float(np.quantile(out,0.975)),5)]
def overall(rs):
    valid=[r for r in rs if nn(r.get("warp_abs_error")) is not None
           and nn(r.get("weft_abs_error")) is not None]
    f=lambda name:round(float(np.mean([nn(r[name]) for r in valid])),5) if valid else None
    return {"n_total":len(rs),"n_scored":len(valid),
      "warp_mae":f("warp_abs_error"),"weft_mae":f("weft_abs_error"),
      "warp_mape":f("warp_abs_pct"),"weft_mape":f("weft_abs_pct"),
      "both10":sum(r.get("both10")=="1" for r in rs),
      "pass":sum(r.get("status")=="PASS" for r in rs),
      "pass_both10":sum(r.get("status")=="PASS" and r.get("both10")=="1" for r in rs),
      "failed":sum(r.get("status")=="FAIL" for r in rs)}
def comparison(left,right,seed):
    # left/new minus right/old: negative delta MAE denotes improvement
    ids=sorted(set(left)&set(right))
    if len(ids)!=130:raise RuntimeError("NOT_ALL_130_SHARED")
    result={}
    for dim in ("warp","weft"):
        ds=[]
        for k in ids:
            a,b=nn(left[k].get(dim+"_abs_error")),nn(right[k].get(dim+"_abs_error"))
            if a is not None and b is not None:
                ds.append(a-b)
        result[dim+"_mae_delta_new_minus_old"]=round(float(np.mean(ds)),5) if ds else None
        result[dim+"_mae_delta_95pct_bootstrap_ci"]=boot_ci(ds,seed)
        result[dim+"_n_scored"]=len(ds)
        result[dim+"_improved_n"]=sum(z<0 for z in ds)
        result[dim+"_worsened_n"]=sum(z>0 for z in ds)
    success=[int(left[k].get("both10")=="1")-int(right[k].get("both10")=="1") for k in ids]
    result["both10_delta_count"]=sum(success)
    result["both10_delta_percentage_points"]=round(100*float(np.mean(success)),4)
    result["both10_delta_95pct_bootstrap_ci_percentage_points"]=[
        round(100*z,4) for z in boot_ci(success,seed+2)]
    result["both10_improved_n"]=sum(x==1 for x in success)
    result["both10_worsened_n"]=sum(x==-1 for x in success)
    discordant=result["both10_improved_n"]+result["both10_worsened_n"]
    result["mcnemar_exact_p"]=float(binomtest(min(result["both10_improved_n"],
                                                 result["both10_worsened_n"]),
                              n=discordant,p=.5).pvalue) if discordant else 1.0
    return result

def from_old(rows,origin):
    normalized={}
    for r in rows:
        new=dict(r)
        new["image"]=r["image"]
        if origin=="V063":
            new["warp_abs_pct"]=r["warp_rel_error_pct"]
            new["weft_abs_pct"]=r["weft_rel_error_pct"]
            new["warp_abs_error"]=r["warp_abs_error"]
            new["weft_abs_error"]=r["weft_abs_error"]
            new["both10"]=r["both_within_10pct"]
            new["sha256"]=r["source_sha256"]
        if origin=="H2":
            new["warp_abs_pct"]=r["warp_rel_error_pct"]
            new["weft_abs_pct"]=r["weft_rel_error_pct"]
            new["both10"]=r["both_within_10pct"]
            new["sha256"]=r["source_sha256"]
        normalized[r["image"]]=new
    return normalized

def map_curves(args,results):
    p=Path(args.inputs)
    folder=Path(args.out)/"visual_4arm"
    folder.mkdir(parents=True,exist_ok=True)
    for sample in CASES:
        name=sample+".jpg"
        image_paths={
         "DF":p/"fabricnet-ablate-DIRECT_FIXED"/"overlays"/name,
         "RF":p/"fabricnet-ablate-ROT90_FIXED"/"overlays"/name,
         "DE":p/"fabricnet-ablate-DIRECT_ESTIMATED"/"overlays"/name,
         "RE":p/"fabricnet-ablate-ROT90_ESTIMATED"/"overlays"/name,
        }
        ims=[]
        for label,path in image_paths.items():
            image=cv2.imread(str(path))
            if image is None:raise RuntimeError("MISSING_ABLATION_IMAGE:"+str(path))
            if image.shape[:2]!=(480,640):
                raise RuntimeError("NONORIGINAL_IMAGE_COORDINATES:"+str(path))
            cv2.rectangle(image,(0,0),(639,27),(30,30,30),-1)
            cv2.putText(image,sample+" "+label+" RED=warp CYAN=weft",
                        (6,19),cv2.FONT_HERSHEY_SIMPLEX,.51,(255,255,255),1,cv2.LINE_AA)
            ims.append(image)
        out=np.vstack([np.hstack(ims[:2]),np.hstack(ims[2:])])
        cv2.imwrite(str(folder/(sample+"_4arm.jpg")),out,[cv2.IMWRITE_JPEG_QUALITY,92])

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--inputs",required=True,type=Path)
    ap.add_argument("--out",required=True,type=Path)
    ap.add_argument("--baseline",required=True,type=Path)
    ap.add_argument("--previous-h2",required=True,type=Path)
    args=ap.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    all_data={}
    for arm in ARMS:
        folder=args.inputs/("fabricnet-ablate-"+arm)
        rows=csv_rows(folder/"metrics.csv")
        if len(rows)!=130 or set(x["image"] for x in rows)!={f"W{i:03d}.jpg" for i in range(1,131)}:
            raise RuntimeError("INCOMPLETE_DATASET:"+arm)
        summ=json.loads((folder/"summary.json").read_text(encoding="utf8"))
        if summ["arm"]!=arm or summ["n"]!=130:
            raise RuntimeError("SUMMARY_MISMATCH:"+arm)
        all_data[arm]={r["image"]:r for r in rows}
    old=from_old(csv_rows(args.baseline),"V063")
    h2=from_old(csv_rows(args.previous_h2),"H2")
    all_data["V063"]=old;all_data["H2_PREVIOUS"]=h2
    for name in old:
        if name not in h2:raise RuntimeError("OLD_H2_MISSING_IMAGE:"+name)
        for arm in ARMS+("H2_PREVIOUS",):
            target=all_data[arm].get(name)
            if target is None or target["sha256"]!=old[name]["sha256"]:
                raise RuntimeError("SHA_OR_FILE_MISMATCH:"+name+":"+arm)
            if arm in ARMS:
                base=old[name]
                if (str(target["truth_warp"]),str(target["truth_weft"])) != (
                    str(float(base["truth_warp"])),str(float(base["truth_weft"]))):
                    raise RuntimeError("TRUTH_MISMATCH:"+name+":"+arm)
    # Frozen run F1 should reproduce previous H2: the same input and _run_direction
    # with only per-image overlays/extra CSV metadata added.
    diffs=[]
    for name in old:
        for fam in ("warp","weft"):
            a=nn(all_data["ROT90_FIXED"][name].get(fam+"_density"))
            b=nn(h2[name].get(fam+"_density_per_cm"))
            if a is not None and b is not None:
                diffs.append(abs(a-b))
    valid_repro=max(diffs) if diffs else None
    if valid_repro is None or valid_repro>0.005:
        raise RuntimeError("REPRODUCIBILITY_FAILURE_H2_ROT90_FIXED max_delta="+str(valid_repro))
    result={"image_n":130,"arm_summary":{},"comparisons":{},
       "previous_h2_reproduction_max_abs_density_per_cm":valid_repro,
       "interpretation_limits":[
           "Ablation on image-aligned 640x480 FabricNET microscope photos, NOT real 8K R/T",
           "DIRECT and ROTATED forms use the same _run_direction code but rotating may change crops/CLAHE and internal warp edges",
           "FIXED vs ESTIMATED uses tensor candidate nearest to image axis, no GT-guided selection",
           "V063 full pipeline includes pair scoring and Gate3; simple-axis confidence PASS not directly comparable",
           "None of the arms is per-physical-yarn identity accuracy or an out-of-sample generalization test",
           "Do not choose best arm per image based on truth"]}
    for arm in ("V063","H2_PREVIOUS")+ARMS:
        vals=list(all_data[arm].values())
        if arm=="V063":
            result["arm_summary"][arm]={
             "n_total":len(vals),
             "warp_mae":round(float(np.mean([float(z["warp_abs_error"]) for z in vals])),5),
             "weft_mae":round(float(np.mean([float(z["weft_abs_error"]) for z in vals])),5),
             "both10":sum(z["both10"]=="1" for z in vals),
             "pass":sum(z["status"]=="PASS" for z in vals)}
        elif arm=="H2_PREVIOUS":
            result["arm_summary"][arm]={
             "n_total":len(vals),
             "warp_mae":round(float(np.mean([float(z["warp_abs_error"]) for z in vals])),5),
             "weft_mae":round(float(np.mean([float(z["weft_abs_error"]) for z in vals])),5),
             "both10":sum(z["both10"]=="1" for z in vals),
             "pass":sum(z["status"]=="PASS" for z in vals)}
        else:result["arm_summary"][arm]=overall(vals)
    trials=[
        ("rotation_effect_fixed","ROT90_FIXED","DIRECT_FIXED"),
        ("rotation_effect_estimated","ROT90_ESTIMATED","DIRECT_ESTIMATED"),
        ("fixed_angle_effect_direct","DIRECT_FIXED","DIRECT_ESTIMATED"),
        ("fixed_angle_effect_rotated","ROT90_FIXED","ROT90_ESTIMATED"),
        ("reverse_rotation_effect","ROT270_FIXED","ROT90_FIXED"),
        ("gain_from_frozen_full_v063","ROT90_FIXED","V063"),
        ("gain_from_previous_h2","ROT90_FIXED","H2_PREVIOUS")]
    for i,(key,new,old_arm) in enumerate(trials):
        result["comparisons"][key]=dict(new=new,old=old_arm,
             **comparison(all_data[new],all_data[old_arm],seed=20261021+i*41))
    result["by_weave"]={}
    for category in ("plain","twill","satin"):
        result["by_weave"][category]={}
        for arm in ARMS:
            grp=[x for x in all_data[arm].values() if x["truth_texture"]==category]
            result["by_weave"][category][arm]=overall(grp)
    # Per-image combined evidence table, including status, angles, prediction & error
    rows=[]
    for name in sorted(old):
        d={"image":name,"truth_texture":old[name]["truth_texture"],
            "warp_gt":old[name]["truth_warp"],"weft_gt":old[name]["truth_weft"]}
        for arm in ("V063","H2_PREVIOUS")+ARMS:
            x=all_data[arm][name]
            d[arm+"_status"]=x.get("status")
            for fam in ("warp","weft"):
                key=(fam+"_density_per_cm") if arm in ("V063","H2_PREVIOUS") else (fam+"_density")
                d[arm+"_"+fam+"_density"]=x.get(key)
                d[arm+"_"+fam+"_abs_pct"]=x.get(fam+"_abs_pct")
            d[arm+"_both10"]=x.get("both10")
        rows.append(d)
    with (args.out/"ablation_per_image.csv").open("w",newline="",encoding="utf-8-sig") as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]))
        writer.writeheader();writer.writerows(rows)
    map_curves(args,result)
    (args.out/"summary.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf8")

    lines=[
      "# FabricNET 双次横向算法消融：真实130张、固定与自动方向、旋转与非旋转",
      "",
      "所有方法对相同真实130张照片执行；Excel仅独立评分，不参与角度、纱距候选决策。低置信度及失败记录也计入统计。",
      "",
      "## 实验臂",
      "",
      "- V063 原版双方向自动候选/联合评分（以前已独立运行）",
      "- H2_PREVIOUS 既有双次横向固定0°（先前已独立跑完，重跑一致性验证）",
      "- DIRECT_FIXED：原图固定竖直测经+固定水平测纬；无双方向联合候选",
      "- ROT90_FIXED：原图固定水平测纬+转90°固定水平测经；即所提方案",
      "- DIRECT_ESTIMATED：原图使用结构张量分别选择最近垂直/水平的方向，不作方向pair排序",
      "- ROT90_ESTIMATED：原图水平测纬+转90°水平测经，两次分别由结构张量选最接近水平的候选",
      "- ROT270_FIXED：原图转180°测纬水平+转270°测经水平，核验反向旋转影响",
      "",
      "## 130张指标",
      "|方法|经密MAE 根/cm|纬密MAE 根/cm|双向误差≤10%|PASS（不同方法质量门不完全等价）|",
      "|---|---:|---:|---:|---:|"
    ]
    for arm,val in result["arm_summary"].items():
        lines.append(f"|{arm}|{val['warp_mae']}|{val['weft_mae']}|{val['both10']}/130|{val['pass']}/130|")
    lines+=["","## 预设成对对照（新-旧；负的MAE差表示改善，正的达标数差表示改善）",
            "|比较|经密MAE差[95% bootstrap CI]|纬密MAE差[95% bootstrap CI]|双向10%达标差[95% CI, 百分点]|改善/退化张数|精确配对p|",
            "|---|---|---|---|---|---|"]
    for key,x in result["comparisons"].items():
        wp=x["warp_mae_delta_new_minus_old"];wc=x["warp_mae_delta_95pct_bootstrap_ci"]
        fp=x["weft_mae_delta_new_minus_old"];fc=x["weft_mae_delta_95pct_bootstrap_ci"]
        dc=x["both10_delta_95pct_bootstrap_ci_percentage_points"]
        lines.append(f"|{key} {x['new']} vs {x['old']}|{wp} {wc}|{fp} {fc}|"
           f"{x['both10_delta_count']}张; {x['both10_delta_percentage_points']}pp {dc}|"
           f"{x['both10_improved_n']}/{x['both10_worsened_n']}|{x['mcnemar_exact_p']:.4f}|")
    lines+=["",
        "## 视觉结果",
        "- [visual_4arm/](visual_4arm/) 原始图片上对比4种关键算法（固定/估计 × 原图/旋转）；红=经，青=纬；共20张困难案例",
        "- [ablation_per_image.csv](ablation_per_image.csv) 130张每个对照臂的预测值、原真值、误差和status；可独立查验",
        "",
        "## 结论限制",
        "1. 准确性改善仅基于FabricNET图像级密度真值，不能冒充纱线身份F1。",
        "2. 本测试的固定0/90°角假定FabricNET采集时布面大致轴向对齐；不是现实任意倾斜自拍的泛化保证。",
        "3. 图像整体旋转可能改变中心裁剪与内部Keep-Size旋转插值/边界，不能把其影响完全归因于横向滤波器更好。",
        "4. 原版完整联合Gate与单轴联合PASS的含义不同，只有物理真值数值误差的比较严格同口径。",
        "5. CI按130张图像独立配对bootstrap（5000次，固定seed）；p针对同图二元双密度10%判定的discordant pairs精确二项式McNemar。",
        "6. 请先视觉确认线是否对应真实物理纱线，进一步用真实配对R/T Golden Dataset做盲测，才能考虑正式替换。",
    ]
    (args.out/"REPORT.md").write_text("\n".join(lines)+"\n",encoding="utf8")
    print("ABLATION_COMPARISON "+json.dumps({k:v for k,v in result.items() if k not in ("by_weave",)},ensure_ascii=False),flush=True)

if __name__=="__main__":
    main()
