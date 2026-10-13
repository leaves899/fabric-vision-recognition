"""G1 morphology, crossing cues and competing hypotheses. IMAGE EVIDENCE ONLY.
A1/A2/intervals calibrate; A3 and B references are excluded from inference.
PHYSICAL_YARN_REFERENCE is not a visible pixel mask. Original camera pixels only.
"""
import argparse, hashlib, json, csv, math
from pathlib import Path
import cv2
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
IDS=["U20261013_01","U20261013_02","U20261013_03","U20261013_05","U20261013_06"]

def native(ann, role):
    assert ann["coordinate_space"]=="ZOOM_2X_NATIVE_PIXELS"
    assert ann["enlargement_scale"]==2
    return np.asarray(ann["segments"][role],dtype=float)/2+np.asarray(ann["crop_original_xyxy"][:2],dtype=float)

def source(root,ann):
    for f,h in [("original_image_path","original_image_sha256"),("image_path","image_sha256")]:
        b=(root/ann[f]).read_bytes()
        if hashlib.sha256(b).hexdigest()!=ann[h]:raise ValueError("SHA256 mismatch "+f)
    im=cv2.imread(str(root/ann["original_image_path"]),cv2.IMREAD_COLOR)
    if im is None:raise ValueError("Cannot decode source original")
    return im

def geometry(im,a1,a2,n):
    v=a1[1]-a1[0]
    theta=float(np.degrees(np.arctan2(v[1],v[0]))%180)
    h,w=im.shape[:2];side=min(560,h,w)
    cx,cy=np.mean(np.vstack([a1,a2]),axis=0)
    ox=int(np.clip(round(cx-side/2),0,w-side))
    oy=int(np.clip(round(cy-side/2),0,h-side))
    crop=im[oy:oy+side,ox:ox+side]
    m=cv2.getRotationMatrix2D((side/2,side/2),theta,1)
    rot=cv2.warpAffine(crop,m,(side,side),borderMode=cv2.BORDER_CONSTANT)
    mask=cv2.warpAffine(np.ones((side,side),np.uint8),m,(side,side),
                        flags=cv2.INTER_NEAREST,borderMode=cv2.BORDER_CONSTANT).astype(bool)
    def transform(a):
        return cv2.transform((a-[ox,oy]).reshape(1,2,2),m)[0]
    ra,rb=transform(a1),transform(a2)
    pitch=float(abs(np.mean(rb[:,1])-np.mean(ra[:,1]))/n)
    return rot,mask,ra,pitch,{"raw_crop_xyxy":[ox,oy,ox+side,oy+side],
                              "human_direction_deg":round(theta,4),"pitch_original_px":round(pitch,4)}

def feature_maps(im,mask):
    lab=cv2.cvtColor(im,cv2.COLOR_BGR2LAB).astype(np.float32)
    g=cv2.GaussianBlur(lab[:,:,0],(0,0),.85)
    gx=cv2.Sobel(g,cv2.CV_32F,1,0,ksize=3)
    gy=cv2.Sobel(g,cv2.CV_32F,0,1,ksize=3)
    edge=cv2.magnitude(gx,gy)
    return lab,gx,gy,max(2.,float(np.median(edge[mask])))

def valid(mask,x,y,rx,ry):
    h,w=mask.shape
    if x-rx<1 or y-ry<1 or x+rx>=w-1 or y+ry>=h-1:return False
    return bool(mask[y-ry:y+ry+1,x-rx:x+rx+1].mean()>=.96)

def morphology(maps,mask,x,y,p):
    lab,gx,gy,scale=maps
    x,y=round(x),round(y)
    r=max(2,round(.34*p));t=max(3,round(.75*p));half=max(6,round(1.1*p))
    if not valid(mask,x,y,half,t):return None
    profile=lab[y-t:y+t+1,x-half:x+half+1,0].mean(axis=1)
    grad=np.diff(profile)
    left=grad[max(0,t-r):t];right=grad[t:min(len(grad),t+r)]
    if not len(left) or not len(right):return None
    lv=left[np.argmax(abs(left))];rv=right[np.argmax(abs(right))]
    paired=float(np.tanh(min(abs(lv),abs(rv))/scale/3)) if lv*rv<0 else 0.
    center=float(np.mean(profile[t-1:t+2]))
    flank=.5*(float(np.mean(profile[:max(1,t-r)]))+float(np.mean(profile[t+r:])))
    contrast=float(np.tanh(abs(center-flank)/scale/3))
    e1=float(np.abs(gy[y-r:y+r+1,x-half:x+half+1]).mean())
    e2=float(np.abs(gx[y-r:y+r+1,x-half:x+half+1]).mean())
    alignment=(e1-e2)/(e1+e2+.2*scale)
    return {"paired_edges":round(paired,4),"center_flank":round(contrast,4),
            "fiber_direction_cue":round(float(alignment),4),
            "appearance":round(.4*paired+.3*contrast+.3*max(0,alignment),5)}

def b_candidates(gx,mask,p):
    h,w=gx.shape
    m=mask[h//4:3*h//4]
    prof=(abs(gx[h//4:3*h//4])*m).sum(axis=0)/np.maximum(1,m.sum(axis=0))
    prof=cv2.GaussianBlur(prof.astype(np.float32).reshape(1,-1),(0,0),max(.8,.11*p))[0]
    cand=[x for x in range(max(12,w//12),min(w-12,w*11//12))
          if prof[x]>=prof[x-2] and prof[x]>prof[x+2]]
    cand.sort(key=lambda x:(-prof[x],x))
    taken=[]
    for x in cand:
        if all(abs(x-z)>=max(5,.65*p) for z in taken):taken.append(x)
        if len(taken)==40:break
    return sorted(taken)

def crossing(gx,gy,mask,x,y,p):
    x,y=round(x),round(y);r=max(3,round(.36*p))
    if not valid(mask,x,y,3*r,3*r):return None
    def avg(a,x0,y0,x1,y1):
        return float(np.abs(a[y0:y1,x0:x1]).mean())
    ain=avg(gy,x-r,y-r//2,x+r,y+r//2+1)
    aside=.5*(avg(gy,x-3*r,y-r//2,x-r,y+r//2+1)+avg(gy,x+r,y-r//2,x+3*r,y+r//2+1))
    bin_=avg(gx,x-r//2,y-r,x+r//2+1,y+r)
    bside=.5*(avg(gx,x-r//2,y-3*r,x+r//2+1,y-r)+avg(gx,x-r//2,y+r,x+r//2+1,y+3*r))
    score=float(np.tanh((ain-aside)/(ain+aside+1e-6))-
                np.tanh((bin_-bside)/(bin_+bside+1e-6)))
    return {"delta_cue":round(score,4),
            "state":"A_OVER_B_CUE" if score>.3 else "B_OVER_A_CUE" if score<-.3 else "UNKNOWN"}

def evaluate(im,mask,maps,crosses,y0,p,phase,alias,slope,collect):
    h,w=mask.shape;step=p*alias
    rows=[];values=[];topos=[]
    k0=math.ceil((max(12,1.3*p)-y0-phase*p)/step)
    k1=math.floor((min(h-12,h-1.3*p)-y0-phase*p)/step)
    xs=np.linspace(.16*w,.84*w,11)
    for k in range(max(-180,k0),min(180,k1)+1):
        yc=y0+phase*p+k*step;obs=[];top=[]
        for x in xs:
            y=yc+slope*(x-w/2)
            f=morphology(maps,mask,x,y,p)
            if f is None:continue
            values.append(f["appearance"])
            if collect:obs.append({"x":round(float(x),2),"y":round(float(y),2),**f})
            nearest=[z for z in crosses if abs(z-x)<.4*p]
            if nearest:
                c=crossing(maps[1],maps[2],mask,nearest[0],y,p)
                if c is not None:top.append(c);topos.append(abs(c["delta_cue"]))
        if obs or top:rows.append({"k":k,"y":round(yc,2),"evidence":obs,"crossings":top[:12]})
    if not values:return {"status":"ABSTAIN_NO_OBSERVABLE_EVIDENCE","site_count":0}
    return {"status":"IMAGE_HYPOTHESIS_ONLY","site_count":len(rows),
            "observations":len(values),"appearance_median":round(float(np.median(values)),5),
            "topology_cue_count":len(topos),
            "topology_strength_median":round(float(np.median(topos)),4) if topos else None,
            "sites":rows if collect else []}

def infer(im,ann):
    # Strictly no A3 or B annotation read in this function.
    if not ann.get("reference_confirmed") or not ann.get("same_family_intervals_confirmed"):
        return {"decision":"ABSTAIN_MISSING_CALIBRATION"},None
    a1,a2=native(ann,"reference"),native(ann,"check_same")
    n=ann["same_family_intervals"]
    if type(n) is not int or n<=0:raise ValueError("unconfirmed physical intervals")
    im2,mask,ra,p,geo=geometry(im,a1,a2,n)
    base={"sample_id":ann["sample_id"],"annotation_semantics":"PHYSICAL_YARN_REFERENCE",
          "physical_yarn_count":None,"physical_identity_probability":None,
          "density_per_cm":None,"physical_identity_verified":False,
          "inference_uses_A3_or_B":False,**geo}
    if p<5:return {**base,"decision":"ABSTAIN_NATIVE_PITCH_UNRESOLVABLE"},(im2,mask,None,None)
    maps=feature_maps(im2,mask);bc=b_candidates(maps[1],mask,p)
    y0=float(np.mean(ra[:,1]))
    h={"ANCHOR_PHASE_YARN":(0,1,0),"HALF_PITCH_GAP_PHASE":(.5,1,0),
       "HALF_PITCH_ALIAS":(0,.5,0),"DIAGONAL_TEXTURE_PLUS":(0,1,.24),
       "DIAGONAL_TEXTURE_MINUS":(0,1,-.24)}
    results={name:evaluate(im2,mask,maps,bc,y0,p,*args,
                           collect=name in ("ANCHOR_PHASE_YARN","HALF_PITCH_GAP_PHASE"))
             for name,args in h.items()}
    ranking=sorted([(d["appearance_median"],name) for name,d in results.items()
                    if d.get("status")=="IMAGE_HYPOTHESIS_ONLY"],reverse=True)
    out={**base,"decision":"G1_NOT_EVALUATED_MISSING_INDEPENDENT_PHYSICAL_PATCH_GT",
         "hypotheses":results,"candidate_cross_count_NOT_B_YARN_COUNT":len(bc),
         "image_only_ranking":[name for score,name in ranking]}
    return out,(im2,mask,maps,bc)

def a3_post_audit(ann,out):
    # Only called AFTER infer freezes all candidate scores and decisions.
    if "pitch_original_px" not in out:return {"status":"NOT_EVALUATED"}
    a1,a2,a3=native(ann,"reference"),native(ann,"check_same"),native(ann,"holdout_same")
    v=a1[1]-a1[0];n=np.array([-v[1],v[0]])/np.linalg.norm(v)
    d=float(np.dot(a3.mean(axis=0)-a1.mean(axis=0),n))
    d12=float(np.dot(a2.mean(axis=0)-a1.mean(axis=0),n))
    p=out["pitch_original_px"] * (1 if d12>=0 else -1)
    z=d/p
    return {"status":"GEOMETRY_ONLY_NOT_VISIBLE_PIXEL_GT",
            "nearest_unknown_integer_index":round(z),
            "residual_fraction_pitch":round(abs(z-round(z)),4),
            "used_in_fitting":False}

def pictures(vis,out,folder,sid):
    img,mask,maps,bc=vis;h,w=img.shape[:2]
    overlay=img.copy();topo=img.copy()
    for name,color in [("HALF_PITCH_GAP_PHASE",(230,70,30)),
                       ("ANCHOR_PHASE_YARN",(0,180,240))]:
        for site in out["hypotheses"].get(name,{}).get("sites",[]):
            y=round(site["y"]);cv2.line(overlay,(0,y),(w-1,y),color,1)
            for e in site["evidence"]:
                if e["appearance"]>.3:cv2.circle(overlay,(round(e["x"]),round(e["y"])),2,color,-1)
    cv2.putText(overlay,"orange=anchor phase, blue=gap control; both UNVERIFIED",
                (9,19),cv2.FONT_HERSHEY_SIMPLEX,.42,(255,255,255),1)
    cv2.imwrite(str(folder/(sid+"_hypotheses.jpg")),overlay)
    counts={"A_OVER_B_CUE":0,"B_OVER_A_CUE":0,"UNKNOWN":0}
    colors={"A_OVER_B_CUE":(0,215,30),"B_OVER_A_CUE":(220,100,30),"UNKNOWN":(125,125,125)}
    for i,site in enumerate(out["hypotheses"]["ANCHOR_PHASE_YARN"]["sites"]):
        if i%2:continue
        for j,x in enumerate(bc):
            if j%2:continue
            f=crossing(maps[1],maps[2],mask,x,site["y"],out["pitch_original_px"])
            if f is None:continue
            counts[f["state"]]+=1
            cv2.circle(topo,(int(x),int(site["y"])),2,colors[f["state"]],-1)
    out["unverified_crossing_cue_counts"]=counts
    cv2.putText(topo,"green=A over, orange=B over, gray=UNKNOWN: only optical cues",
                (9,19),cv2.FONT_HERSHEY_SIMPLEX,.40,(255,255,255),1)
    cv2.imwrite(str(folder/(sid+"_topology.jpg")),topo)
    chart=np.full((310,720,3),255,np.uint8)
    cv2.putText(chart,"Optical hypothesis scores, NOT identity probability",
                (8,25),cv2.FONT_HERSHEY_SIMPLEX,.55,(40,40,40),1)
    for i,(name,result) in enumerate(out["hypotheses"].items()):
        y=75+i*48;val=result.get("appearance_median")
        cv2.putText(chart,name,(10,y),cv2.FONT_HERSHEY_SIMPLEX,.48,(30,30,30),1)
        if val is not None:
            cv2.rectangle(chart,(365,y-17),(365+int(np.clip(val,0,1)*260),y-4),(90,140,220),-1)
            cv2.putText(chart,str(val),(650,y-4),cv2.FONT_HERSHEY_SIMPLEX,.42,(30,30,30),1)
    cv2.imwrite(str(folder/(sid+"_competition.jpg")),chart)

def review_patches(vis,out,sid,folder):
    img=vis[0];r=max(10,min(40,int(out["pitch_original_px"]*1.15)))
    rows=[]
    for name in ("ANCHOR_PHASE_YARN","HALF_PITCH_GAP_PHASE"):
        candidates=[s for s in out["hypotheses"][name]["sites"] if s["evidence"]]
        indices=sorted(set(np.linspace(0,len(candidates)-1,min(6,len(candidates)),dtype=int))) if candidates else []
        for i in indices:
            s=candidates[i];e=s["evidence"][len(s["evidence"])//2]
            x,y=round(e["x"]),round(e["y"])
            if y-r<0 or x-r<0 or y+r>=img.shape[0] or x+r>=img.shape[1]:continue
            label=f'{sid}_{name}_{s["k"]:+04d}'
            file=label+".jpg"
            cv2.imwrite(str(folder/file),img[y-r:y+r+1,x-r:x+r+1])
            rows.append([sid,label,file,name,"UNREVIEWED","","",""])
    return rows

def run(root,out):
    out.mkdir(parents=True,exist_ok=True);patches=out/"review_patches";patches.mkdir(exist_ok=True)
    samples=[];review=[]
    for sid in IDS:
        path=root/"datasets/annotations/drafts"/(sid+".json")
        if not path.exists():
            samples.append({"sample_id":sid,"decision":"NOT_EVALUATED_MISSING_ANNOTATION"})
            continue
        ann=json.loads(path.read_text(encoding="utf-8"))
        pred,vis=infer(source(root,ann),ann)
        pred["post_inference_A3"]=a3_post_audit(ann,pred)
        if vis and vis[2] is not None:
            pictures(vis,pred,out,sid)
            review.extend(review_patches(vis,pred,sid,patches))
        (out/(sid+".json")).write_text(json.dumps(pred,ensure_ascii=False,indent=2)+"\n")
        samples.append(pred)
    with (out/"review_manifest.csv").open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.writer(f);w.writerow(["sample_id","patch_id","image_path","proposed_hypothesis",
                                   "review_status","human_label","gt_evidence_source","independent_reviewer"])
        w.writerows(review)
    brief={"g1_status":"G1_NOT_EVALUATED","sample_count":len(samples),
           "unreviewed_patch_count":len(review),
           "reason":"No independent visible-yarn and non-yarn patch ground truth",
           "samples":[{"sample_id":s["sample_id"],"decision":s["decision"],
                       "pitch_native_px":s.get("pitch_original_px"),
                       "image_only_ranking":s.get("image_only_ranking"),
                       "post_inference_A3":s.get("post_inference_A3"),
                       "crossing_cues":s.get("unverified_crossing_cue_counts")}
                      for s in samples]}
    (out/"summary.json").write_text(json.dumps(brief,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(brief,ensure_ascii=False,indent=2))
    return brief

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",type=Path,default=ROOT)
    ap.add_argument("--out",type=Path,default=Path("experiments/p0-g1"))
    args=ap.parse_args();root=args.root.resolve();target=args.out if args.out.is_absolute() else root/args.out
    run(root,target)
if __name__=="__main__":main()
