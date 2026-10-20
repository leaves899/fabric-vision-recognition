from __future__ import annotations

"""Independent local transverse-profile pitch proof of concept.

NO ground truth enters the estimator. It uses the angles predicted by shibie,
then separately evaluates predicted pixel pitch against previously user-confirmed
physical-yarn interval labels.  This does NOT draw/claim synthetic individual yarns.
"""

import csv
import json
import math
import sys
from pathlib import Path

import cv2
import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.signal import find_peaks

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
sys.path.insert(0,str(HERE))
from evaluate_labeled_yarn_pitch import physical_reference, source_working_scale, delta

RUNS=ROOT/"experiments/shibie-acf-holdout-20261020"
SRC=ROOT/"datasets/user_contributed/2026-10-13-six-fabric-images/images"
OUT=ROOT/"experiments/shibie-multistrip-pitch-20261020"
DEV=("U20261013_01","U20261013_03","U20261013_05")
HOLDOUT=("U20261013_02","U20261013_06")
TYPES=("intensity","edge_energy")


def get_profiles(image,theta):
    h,w=image.shape[:2]
    center=(w/2.,h/2.)
    mat=cv2.getRotationMatrix2D(center,float(theta)-90.0,1.0)
    aligned=cv2.warpAffine(image,mat,(w,h),flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REFLECT101)
    h,w=aligned.shape
    x0,x1=int(w*.19),int(w*.81)
    y0,y1=int(h*.19),int(h*.81)
    cropped=aligned[y0:y1,x0:x1]
    n=7
    samples=[]
    for j in range(n):
        yy0=int(cropped.shape[0]*(j+.06)/(n+1))
        yy1=int(cropped.shape[0]*(j+1.06)/(n+1))
        block=cropped[yy0:yy1,:].astype(np.float64)
        if block.size==0:continue
        profile=np.median(block,axis=0)
        samples.append(profile)
    return samples


def profile_acf(profile,feature):
    q=profile.astype(np.float64)
    if feature=="edge_energy":
        q=np.abs(gaussian_filter1d(q,0.8,order=1))
        q=q-gaussian_filter1d(q,6.0)
    else:
        q=q-gaussian_filter1d(q,60.0)
    q-=np.mean(q)
    n=len(q)
    den=np.dot(q,q)
    if den<1e-6:return np.zeros(125)
    # Use FFT correlation to avoid O(n^2) for raw camera photos.
    N=1<<int(math.ceil(math.log2(2*n)))
    fft=np.fft.rfft(q,n=N)
    acf=np.fft.irfft(fft*np.conj(fft),n=N)[:min(n,125)]
    acf=acf/(acf[0]+1e-9)
    return acf


def candidate_pitch(profiles,kind):
    acfs=[profile_acf(profile,kind) for profile in profiles]
    if not acfs:return {"pitch_px":None,"reason":"NO_PROFILES"}
    hi=min(min(len(a) for a in acfs)-1,110)
    lo=4
    if hi<=lo+3:return {"pitch_px":None,"reason":"IMAGE_TOO_SMALL"}
    matrix=np.vstack([a[:hi+1] for a in acfs])
    robust=np.median(matrix,axis=0)
    peaks,_=find_peaks(robust[lo:hi+1],distance=3,prominence=max(.025,float(np.std(robust[lo:hi+1]))*.37))
    if len(peaks)==0:return {"pitch_px":None,"reason":"NO_SHARED_PERIOD"}
    peaks=peaks+lo
    scores=[]
    for p in peaks:
        strength=float(robust[p])
        if strength<=0:continue
        local=np.array([max(0,float(np.max(row[max(0,p-2):min(hi+1,p+3)]))) for row in matrix])
        support=float(np.mean(local>=max(.035,strength*.40)))
        # Penalize period peaks present in only one strip.
        weighted=strength*(.30+.70*support)
        scores.append((int(p),float(weighted),strength,support))
    if not scores:return {"pitch_px":None,"reason":"NO_POSITIVE_PEAK"}
    best=max(x[1] for x in scores)
    # Prefer the earliest supported fundamental, not a later repetition.
    eligible=[item for item in scores if item[1]>=best*.70 and item[3]>=.55]
    selected=min(eligible or scores,key=lambda x:x[0])
    return {"pitch_px":float(selected[0]),"strength":round(selected[2],4),
            "cross_strip_support":round(selected[3],3),
            "peaks":[{"lag":t[0],"weighted":round(t[1],4),"support":round(t[3],3)} for t in scores[:16]]}


def evaluate(sample,variant,measurement,kind,raw):
    theta=[measurement.get("warp_dir"),measurement.get("weft_dir")]
    if None in theta:return None
    pitches,angles=physical_reference(sample)
    inferred=[]
    for direction in theta:
        prof=get_profiles(raw,direction)
        inferred.append(candidate_pitch(prof,kind))
    direct=delta(theta[0],angles[0])+delta(theta[1],angles[1])
    reverse=delta(theta[0],angles[1])+delta(theta[1],angles[0])
    assignment=(0,1) if direct<=reverse else (1,0)
    errors=[]
    for i,pick in enumerate(assignment):
        predicted=inferred[i].get("pitch_px")
        errors.append(abs(predicted-pitches[pick])/pitches[pick]*100 if predicted is not None else None)
    return {"sample":sample,"variant":variant,"family":"independent_two_axis_local_profiles",
       "split":"holdout" if sample in HOLDOUT else "development",
       "feature":kind,"operator_angle_error_deg":round(min(direct,reverse)/2,3),
       "truth_px":list(pitches),"estimated_px":[q.get("pitch_px") for q in inferred],
       "support":[q.get("cross_strip_support") for q in inferred],
       "relative_errors_pct":errors,
       "mean_error_pct":sum(errors)/2 if all(x is not None for x in errors) else None,
       "peak_data":inferred}


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    d=json.loads((RUNS/"comparison.json").read_text(encoding="utf-8"))
    data={item["name"]:item for item in d if item["variant"]=="baseline"}
    raw={}
    for name in DEV+HOLDOUT:
        image=cv2.imread(str(SRC/(name+".jpg")),cv2.IMREAD_GRAYSCALE)
        if image is None:raise ValueError("MISSING_SAMPLE "+name)
        raw[name]=image
    records=[]
    for kind in TYPES:
        for sample in DEV+HOLDOUT:
            row=evaluate(sample,"v063_angles",data[sample],kind,raw[sample])
            records.append(row)
            print(json.dumps({k:row[k] for k in ("sample","feature","estimated_px","relative_errors_pct")},ensure_ascii=False),flush=True)
    # The holdout is not used to choose the feature family.
    def avg(name,kind):
        vals=[x["mean_error_pct"] for x in records if x["split"]==name and x["feature"]==kind and x["mean_error_pct"] is not None]
        return sum(vals)/len(vals) if vals else None
    means={kind:avg("development",kind) for kind in TYPES}
    eligible={k:v for k,v in means.items() if v is not None}
    selected=min(eligible,key=eligible.get) if eligible else None
    report={
        "method":"multi_strip_local_evidence",
        "labels_are_post_inference_only":True,
        "development":DEV,"holdout":HOLDOUT,
        "feature_candidates":list(TYPES),
        "selected_using_development_only":selected,
        "development_mean_pitch_error_pct":means,
        "holdout_mean_pitch_error_pct":{kind:avg("holdout",kind) for kind in TYPES},
        "conclusion":"EXPERIMENTAL__NOT_AN_APPROVED_PHYSICAL_YARN_COUNT",
        "rows":records,
    }
    (OUT/"analysis.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    lines=["# 多截线独立物理周期实验（不合入基线）","",
        "使用原版自动预测方向，随后在不同纵向局部区域提取一维亮度/边缘能量并做跨区域 ACF 共识。",
        "候选周期不能直接当一根真实纱线；没有合成补线，也没有使用人工纱距初始化算法。",
        "仅开发集用于选择两种信号形式，留出集只做独立评估。","",
        "| 样本 | 原图局部强度：平均纱距误差 | 原图边缘能量：平均纱距误差 |",
        "|---|---:|---:|"]
    for sample in DEV+HOLDOUT:
        a,b=(next(x for x in records if x["sample"]==sample and x["feature"]==kind) for kind in TYPES)
        fmt=lambda x: "-" if x is None else f"{x:.2f}%"
        lines.append(f"| {sample} | {fmt(a['mean_error_pct'])} | {fmt(b['mean_error_pct'])} |")
    lines.extend(["",f"开发集上选中的方式：{selected}；其留出集平均误差：{report['holdout_mean_pitch_error_pct'].get(selected)}%。",
        "警告：本实验基于普通手机单图且角度来自当前原版算法，并不满足认证 R/T、mm/px、5cm实体框的计量条件。"])
    (OUT/"report.md").write_text("\n".join(lines)+"\n",encoding="utf-8")


if __name__=="__main__":
    main()
