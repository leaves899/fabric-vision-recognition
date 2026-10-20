from __future__ import annotations

"""Label-free transmission polarity estimation via foreground topology.

Cloth yarns may form a connected two-axis network while transmitted pores
usually form isolated apertures. This is ONLY a hypothesis; abstain whenever
the topological difference is small or both polarities are similarly connected.
No weave labels, known yarn angles or synthetic physical centers are used.
"""
import json
import sys
from pathlib import Path
import cv2
import numpy as np

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
sys.path.insert(0,str(HERE))
from synthetic_physical_fabric import SCENES,HOLDOUT_SCENES,synthesize

OUT=ROOT/"experiments/shibie-polarity-topology-20261020"
PAIRED=HERE/"tmp/pair_test"

def _connected_topology(mask):
    # Use 8-neighborhood: physical filaments cross under other yarns.
    count,_,stats,_=cv2.connectedComponentsWithStats(mask.astype(np.uint8),connectivity=8)
    foreground=int(np.sum(mask!=0))
    if count<=1 or foreground==0:
        return {"largest_fraction":0.0,"span_x":0.0,"span_y":0.0,"area_fraction":0.0}
    idx=int(np.argmax(stats[1:,cv2.CC_STAT_AREA])+1)
    box=stats[idx]
    h,w=mask.shape
    return {
        "largest_fraction":float(box[cv2.CC_STAT_AREA])/foreground,
        "span_x":float(box[cv2.CC_STAT_WIDTH])/w,
        "span_y":float(box[cv2.CC_STAT_HEIGHT])/h,
        "area_fraction":foreground/(w*h),
    }


def analyze_polarity(bgr, make_masks=False):
    gray=cv2.cvtColor(bgr,cv2.COLOR_BGR2GRAY) if bgr.ndim==3 else bgr
    h,w=gray.shape
    # The center is shared by captured R/T, not the backlight fixture.
    img=gray[int(h*.10):int(h*.90),int(w*.10):int(w*.90)]
    if img.size==0:raise ValueError("INVALID_POLARITY_IMAGE")
    scale=min(1.,512./max(img.shape))
    if scale<1:
        img=cv2.resize(img,(int(round(img.shape[1]*scale)),int(round(img.shape[0]*scale))),interpolation=cv2.INTER_AREA)
    filtered=cv2.GaussianBlur(img,(3,3),sigmaX=.75)
    kernel=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(3,3))
    stats={}
    previews={}
    for mode in ("dark","bright"):
        readings=[]
        for occupancy in (.32,.40,.48,.56):
            if mode=="dark":
                limit=float(np.quantile(filtered,occupancy))
                foreground=(filtered<limit).astype(np.uint8)
            else:
                limit=float(np.quantile(filtered,1.0-occupancy))
                foreground=(filtered>limit).astype(np.uint8)
            foreground=cv2.morphologyEx(foreground,cv2.MORPH_CLOSE,kernel)
            t=_connected_topology(foreground)
            # Largest component needs to cover both dimensions, not merely
            # be one big diagonal/twill band or one horizontal highlight.
            score=t["largest_fraction"] * min(t["span_x"],t["span_y"])
            readings.append({"quantile":occupancy,"score":round(score,5),**t})
            if abs(occupancy-.48)<1e-6:
                previews[mode]=(foreground*255).astype(np.uint8)
        stats[mode]={"median_score":round(float(np.median([q["score"] for q in readings])),5),
                     "quantiles":readings}
    difference=stats["dark"]["median_score"]-stats["bright"]["median_score"]
    best="dark" if difference>0 else "bright"
    # Conservative topology discrimination; no automatic image-inference
    # deployment until independently verified using genuine R/T cloth samples.
    if abs(difference)<.15 or max(stats[best]["median_score"],0)<.40:
        decision="abstain"
    else:
        decision=best
    output={"decision":decision,"candidate":best,"margin":round(abs(difference),5),
            "scores":stats}
    return (output,previews) if make_masks else output


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    rows=[]
    scene_previews=[]
    for scene in SCENES+HOLDOUT_SCENES:
        _,t,_=synthesize(scene)
        for polarity in ("dark","bright"):
            input_frame=t if polarity=="dark" else 255-t
            stats,masks=analyze_polarity(input_frame,True)
            rows.append({"sample":scene.name,"split":"holdout" if scene in HOLDOUT_SCENES else "development",
                        "synthetic_true_mode":polarity,"image_pol_mode":polarity,**stats,
                        "correct":stats["decision"]==polarity,
                        "abstained":stats["decision"]=="abstain"})
            if scene.name in ("plain_neutral","satin_5_2") and polarity=="dark":
                scene_previews.append((scene.name,input_frame,masks))
    real=cv2.imread(str(PAIRED/"transmission.png"))
    if real is None:raise ValueError("EXISTING_REAL_TRANSMISSION_MISSING")
    real_stats,real_masks=analyze_polarity(real,True)
    rows.append({"sample":"REAL_RT_1280","split":"real_unlabeled","synthetic_true_mode":None,
                 "image_pol_mode":None,**real_stats,"correct":None,
                 "abstained":real_stats["decision"]=="abstain"})
    scene_previews.append(("real_unlabeled",real,real_masks))
    (OUT/"polarity_scores.json").write_text(json.dumps(rows,indent=2,ensure_ascii=False),encoding="utf-8")
    dev= [x for x in rows if x["split"]=="development"]
    hold=[x for x in rows if x["split"]=="holdout"]
    lines=["# 透射双图的无标注明暗极性拓扑诊断",
           "","使用同一输入图的暗区和亮区二值拓扑，寻找是否出现二维贯通的纱线网络。",
           "此指标不含真值纱线坐标、不含组织标签，先单独测试，不允许自动修改正式模型。",
           "对每一张合成图生成正常强度和反相强度两种模式，冻结场景参数。","",
           "| 场景 | 子集 | 已知合成极性 | 自动判断 | 暗网得分 | 亮网得分 |",
           "|---|---|---|---|---:|---:|"]
    for x in rows:
        lines.append(f"| {x['sample']} | {x['split']} | {x['synthetic_true_mode'] or '未知'} | {x['decision']} | {x['scores']['dark']['median_score']:.3f} | {x['scores']['bright']['median_score']:.3f} |")
    for label,items in (("development",dev),("holdout",hold)):
        lines.append(f"\n- {label}: 识别正确={sum(x['correct'] for x in items)}/{len(items)}，弃权={sum(x['abstained'] for x in items)}")
    lines.extend(["",
        "真实RT样本没有单根纱线实体标签，不宣称真实极性识别正确；如果出现弃权则应维持原版。",
        "如果这项独立证据在合成的明暗反相留出集都不可靠，就不应把自动极性接入主程序。"])
    (OUT/"report.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    tile=340
    sheet=np.full((len(scene_previews)*tile,3*tile,3),243,dtype=np.uint8)
    for i,(name,raw,masks) in enumerate(scene_previews):
        imgs=(raw,cv2.cvtColor(masks["dark"],cv2.COLOR_GRAY2BGR),cv2.cvtColor(masks["bright"],cv2.COLOR_GRAY2BGR))
        for k,img in enumerate(imgs):
            thumb=cv2.resize(img,(tile,tile),interpolation=cv2.INTER_AREA)
            sheet[i*tile:(i+1)*tile,k*tile:(k+1)*tile]=thumb
            cv2.rectangle(sheet,(k*tile,i*tile),(k*tile+tile-1,i*tile+22),(245,245,245),-1)
            cv2.putText(sheet,name+" "+("source","dark-mask","bright-mask")[k],
                  (k*tile+4,i*tile+15),cv2.FONT_HERSHEY_SIMPLEX,.43,(20,20,20),1,cv2.LINE_AA)
    cv2.imwrite(str(OUT/"review_sheet.jpg"),sheet,[cv2.IMWRITE_JPEG_QUALITY,94])


if __name__=="__main__":
    main()
