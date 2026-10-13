"""G1.2: model+photo consensus only; preserve frozen V5 baseline otherwise.

Never read annotation JSON, user short strokes or holdouts during inference.
Scoring is of visual candidates, not certified physical-yarn identity.
"""
import cv2
import numpy as np
from v51_refinement import _candidate_polyline,_arclength,_profile_scores,pitch_for_family,CONFIG

PARAMS=dict(search_pitch=.16,offsets=13,min_model_gain=.13,
            min_model_confidence=.56,min_photo_gain=.08,
            min_strong_windows=3,max_normal_delta_pitch=.10,
            max_step_pitch=.12,smoothing=.8)

def _sample_field(field,pos,tangent,normal,offsets,pitch):
    k=len(pos); n=len(offsets)
    longitudinal=np.array([-.50,-.25,0.,.25,.50],np.float32)*pitch
    loc=(pos[:,None,None,:].astype(np.float32)+
         normal[:,None,None,:].astype(np.float32)*offsets[None,:,None,None]+
         tangent[:,None,None,:].astype(np.float32)*longitudinal[None,None,:,None])
    h,w=field.shape
    valid=(loc[...,0]>=1)&(loc[...,0]<w-2)&(loc[...,1]>=1)&(loc[...,1]<h-2)
    v=cv2.remap(field,loc[...,0].reshape(k*n,-1),loc[...,1].reshape(k*n,-1),
                cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT,borderValue=0)
    return np.median(v.reshape(k,n,-1),axis=2),np.mean(valid,axis=2)

def refine_family(photo,tracks,prob,pitch,*,params=None):
    cfg={**PARAMS,**(params or {})}
    lab=cv2.cvtColor(photo,cv2.COLOR_BGR2LAB)[:,:,0].astype(np.float32)
    lum=cv2.GaussianBlur(lab,(0,0),.9)
    prob=np.asarray(prob,np.float32)
    if prob.shape!=lum.shape:
        raise ValueError("Frozen V4 score field / ROI mismatch")
    offsets=np.linspace(-cfg["search_pitch"]*pitch,cfg["search_pitch"]*pitch,
                        cfg["offsets"],dtype=np.float32)
    zero=len(offsets)//2
    output=[];reports=[]
    for track in tracks:
        orig=np.asarray(track,float)
        if orig.ndim!=2 or orig.shape[1]!=2 or len(orig)<2:
            output.append(track);reports.append({"status":"ABSTAIN_INVALID"});continue
        sampled=_candidate_polyline(orig,pitch)
        if sampled is None:
            output.append(track);reports.append({"status":"ABSTAIN_SHORT"});continue
        arc,pos,tan,normal=sampled
        model,valid=_sample_field(prob,pos,tan,normal,offsets,pitch)
        optical,support=_profile_scores(lum,pos,tan,normal,pitch,offsets,CONFIG)
        good=(valid>=.99)&(support>=.75)&(
            model-model[:,zero,None]>=cfg["min_model_gain"]) & (
            model>=cfg["min_model_confidence"]) & (
            optical-optical[:,zero,None]>=cfg["min_photo_gain"])
        good[:,zero]=False
        winners=np.argmax(np.where(good,model-model[:,zero,None],-1e6),axis=1)
        eligible=np.any(good,axis=1)
        if int(eligible.sum())<cfg["min_strong_windows"]:
            output.append(track)
            reports.append({"status":"ABSTAIN_NO_CONSENSUS","windows":int(eligible.sum())})
            continue
        displacement=np.where(eligible,offsets[winners],0.).astype(np.float32)
        # Reject whole-track phase changes. G1.2 is a curvature/position
        # proposal, not a count/pitch/phase correction.
        displacement-=np.median(displacement)
        displacement=np.clip(displacement,-cfg["max_normal_delta_pitch"]*pitch,
                              cfg["max_normal_delta_pitch"]*pitch)
        delta=cfg["max_step_pitch"]*pitch
        for i in range(1,len(displacement)):
            displacement[i]=np.clip(displacement[i],displacement[i-1]-delta,
                                    displacement[i-1]+delta)
        for i in range(len(displacement)-2,-1,-1):
            displacement[i]=np.clip(displacement[i],displacement[i+1]-delta,
                                    displacement[i+1]+delta)
        if cfg["smoothing"]>0:
            displacement=cv2.GaussianBlur(displacement[None,:],(0,0),cfg["smoothing"]).ravel()
        if float(max(abs(displacement)))<.5:
            output.append(track);reports.append({"status":"ABSTAIN_SUBPIXEL"});continue
        pts,s=_arclength(orig)
        shift=np.interp(s,arc,displacement)
        norm=np.column_stack([np.interp(s,arc,normal[:,i]) for i in (0,1)])
        norm/=np.maximum(np.linalg.norm(norm,axis=1,keepdims=True),1e-8)
        updated=pts+norm*shift[:,None]
        output.append(np.round(updated,3).tolist())
        reports.append({"status":"MODEL_PHOTO_CONSENSUS_CANDIDATE",
                        "supported_windows":int(eligible.sum()),
                        "max_shift_px":round(float(max(abs(shift))),3)})
    return output,dict(input_count=len(tracks),output_count=len(output),
                       changed=sum(x["status"]=="MODEL_PHOTO_CONSENSUS_CANDIDATE" for x in reports),
                       abstained=sum(x["status"].startswith("ABSTAIN") for x in reports),
                       pitch_px=round(float(pitch),3),per_track=reports,
                       physical_yarn_identity_verified=False)

def refine_v5_g12(photo,tracks,scores,*,params=None):
    out={"status":"EXPERIMENTAL_G12_NOT_VALIDATED",
         "frozen_v4_sha256":scores["frozen_sha256"],
         "annotation_used_for_inference":False,
         "physical_yarn_identity_verified":False}
    for family in ("first","second"):
        pitch=pitch_for_family(tracks[family])
        output,info=refine_family(photo,tracks[family],scores[family],pitch,params=params)
        out[family]=output
        out[family+"_report"]=info
    return out
