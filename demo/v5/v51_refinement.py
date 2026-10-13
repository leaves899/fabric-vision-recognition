"""Conservative image-only local refinement for frozen V5 candidate yarn tracks.

Only image pixels and V4 candidates enter inference. No operator labels, no
per-fabric tuning, no physical-yarn identity claim. Keeps IDs and counts.
"""
from __future__ import annotations
import cv2
import numpy as np

CONFIG = dict(max_shift_pitch=.43, offsets=17, longitudinal_samples=7,
              along_extent_pitch=.78, step_pitch=.95, center_flank_pitch=.23,
              anchor_weight=.27, continuity_weight=2.6,
              reliability_floor=.22, local_min_gain=.10,
              min_confident_windows=3)

def pitch_for_family(tracks, fallback=24.):
    mid=[]
    for tr in tracks:
        a=np.asarray(tr,float)
        if a.ndim==2 and a.shape[1]==2 and len(a)>=2 and np.isfinite(a).all():
            mid.append((a[len(a)//2],a[-1]-a[0]))
    if len(mid)<3: return float(fallback)
    dirs=np.asarray([d/(np.linalg.norm(d)+1e-12) for _,d in mid])
    normal=np.array([-np.median(dirs[:,1]),np.median(dirs[:,0])])
    if np.linalg.norm(normal)<.2: normal=np.array([-dirs[0,1],dirs[0,0]])
    normal/=max(np.linalg.norm(normal),1e-12)
    coords=np.sort(np.array([np.dot(p,normal) for p,_ in mid]))
    gaps=np.diff(coords)
    gaps=gaps[gaps>2.]
    if len(gaps)<2: return float(fallback)
    return float(np.clip(np.median(gaps),5.,160.))

def _arclength(poly):
    arclength=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(poly,axis=0),axis=1))]
    keep=np.r_[True,np.diff(arclength)>1e-5]
    return poly[keep],arclength[keep]

def _candidate_polyline(poly,pitch):
    poly,s=_arclength(poly)
    if len(poly)<2 or s[-1]<max(28.,2.5*pitch): return None
    n=max(7,int(np.ceil(s[-1]/max(7.,.95*pitch)))+1)
    t=np.linspace(0,float(s[-1]),n)
    pos=np.column_stack([np.interp(t,s,poly[:,k]) for k in range(2)])
    grad=np.gradient(pos,axis=0)
    tangent=grad/np.maximum(np.linalg.norm(grad,axis=1,keepdims=True),1e-8)
    normal=np.column_stack([-tangent[:,1],tangent[:,0]])
    return t,pos,tangent,normal

def _profile_scores(luma,pos,tangent,normal,pitch,offsets,cfg):
    k=len(pos)
    longitudinal=np.linspace(-cfg['along_extent_pitch'],cfg['along_extent_pitch'],
                              cfg['longitudinal_samples'],dtype=np.float32)*pitch
    side=float(cfg['center_flank_pitch']*pitch)
    pos=pos.astype(np.float32)
    tangent=tangent.astype(np.float32)
    normal=normal.astype(np.float32)
    base=pos[:,None,None,:]+normal[:,None,None,:]*offsets[None,:,None,None]
    base=base+tangent[:,None,None,:]*longitudinal[None,None,:,None]
    h,w=luma.shape
    valid=(base[...,0]>=side+2)&(base[...,0]<w-side-3)&(base[...,1]>=side+2)&(base[...,1]<h-side-3)
    def remap(delta):
        q=base+normal[:,None,None,:]*delta
        return cv2.remap(luma,q[...,0].astype(np.float32).reshape(k*len(offsets),-1),
                         q[...,1].astype(np.float32).reshape(k*len(offsets),-1),
                         cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT_101).reshape(k,len(offsets),-1)
    central,left,right=remap(0),remap(-side),remap(side)
    contrast=central-.5*(left+right)
    bilateral=np.minimum(np.abs(central-left),np.abs(central-right))
    two_sided=(central-left)*(central-right)>0
    bilateral=np.where(two_sided,bilateral,0.)
    scale=np.maximum(np.std(np.stack([left,central,right],axis=0),axis=(0,2,3)),1.5)
    signal=np.abs(contrast)/(scale[:,None,None]+1e-6)
    paired=bilateral/(scale[:,None,None]+1e-6)
    weighted=np.where(valid,(.5*np.minimum(signal,3)+.5*np.minimum(paired,3))*two_sided,0.)
    support=np.mean(valid,axis=2)
    scores=.75*np.median(weighted,axis=2)+.25*np.mean(weighted,axis=2)
    consistency=np.abs(np.mean(np.where(valid,np.sign(contrast),0),axis=2))
    scores*=np.sqrt(np.maximum(0.,consistency))*support
    return scores.astype(np.float32),support.astype(np.float32)

def _select_displacements(scores,offsets,pitch,cfg):
    N,S=scores.shape
    scores=np.where(np.isfinite(scores),scores,0.)
    spread=np.percentile(scores,85,axis=1)-np.percentile(scores,15,axis=1)
    zero=int(np.argmin(np.abs(offsets)))
    best=np.argmax(scores,axis=1)
    strong=(spread>=cfg['reliability_floor'])&((scores[np.arange(N),best]-scores[:,zero])>=cfg['local_min_gain'])
    nstrong=int(np.count_nonzero(strong))
    if N<cfg['min_confident_windows'] or nstrong<cfg['min_confident_windows']:
        return np.zeros(N,float),dict(status='ABSTAIN_INSUFFICIENT_IMAGE_EVIDENCE',confident_windows=nstrong)
    z=offsets/pitch
    value=(scores-scores[:,zero,None])/np.maximum(spread[:,None],.35)
    value=np.clip(value,-2.,2.)
    value[~strong]*=.10
    cost=-value+cfg['anchor_weight']*z[None,:]**2
    jump=cfg['continuity_weight']*(z[:,None]-z[None,:])**2
    dp=np.zeros((N,S),float)
    back=np.zeros((N,S),np.int16)
    dp[0]=cost[0]
    for i in range(1,N):
        c=dp[i-1,:,None]+jump
        back[i]=np.argmin(c,axis=0)
        dp[i]=cost[i]+np.min(c,axis=0)
    ids=np.empty(N,np.int16)
    ids[-1]=np.argmin(dp[-1])
    for i in range(N-2,-1,-1): ids[i]=back[i+1,ids[i+1]]
    displacement=offsets[ids].astype(float)
    near=np.array([np.any(strong[max(0,i-1):min(N,i+2)]) for i in range(N)])
    displacement[~near]=0.
    cap=.21*pitch
    for i in range(1,N):displacement[i]=np.clip(displacement[i],displacement[i-1]-cap,displacement[i-1]+cap)
    for i in range(N-2,-1,-1):displacement[i]=np.clip(displacement[i],displacement[i+1]-cap,displacement[i+1]+cap)
    return displacement,dict(status='IMAGE_SUPPORTED_CANDIDATE_REFINEMENT',confident_windows=nstrong,
                             total_windows=N,image_support_fraction=round(nstrong/N,3),
                             median_abs_shift_px=round(float(np.median(abs(displacement))),3),
                             max_abs_shift_px=round(float(np.max(abs(displacement))),3))

def refine_family(image,tracks,*,pitch=None,config=None):
    cfg={**CONFIG,**(config or {})}
    if image.ndim==3:lum=cv2.cvtColor(image,cv2.COLOR_BGR2LAB)[:,:,0]
    elif image.ndim==2:lum=image
    else:raise ValueError('image must be gray or BGR')
    lum=cv2.GaussianBlur(lum.astype(np.float32),(0,0),.9)
    pitch=float(pitch if pitch is not None else pitch_for_family(tracks))
    if not 4<=pitch<=160:raise ValueError('invalid candidate pitch')
    offsets=np.linspace(-cfg['max_shift_pitch']*pitch,cfg['max_shift_pitch']*pitch,cfg['offsets'],dtype=np.float32)
    output=[];reports=[]
    for track in tracks:
        original=np.asarray(track,float)
        if original.ndim!=2 or original.shape[1]!=2 or len(original)<2:
            output.append(track);reports.append({'status':'UNCHANGED_SHORT_OR_INVALID'});continue
        sampled=_candidate_polyline(original,pitch)
        if sampled is None:
            output.append(track);reports.append({'status':'UNCHANGED_SHORT_OR_INVALID'});continue
        t,pos,tangent,normal=sampled
        scores,support=_profile_scores(lum,pos,tangent,normal,pitch,offsets,cfg)
        scores[support<.75]=0.
        displacement,info=_select_displacements(scores,offsets,pitch,cfg)
        if info['status'].startswith('ABSTAIN'):
            output.append(track);reports.append(info);continue
        if len(displacement)>=7:
            displacement=cv2.GaussianBlur(displacement.astype(np.float32)[None,:],(0,0),1.).ravel()
        # G1 repairs LOCAL curvature, not global lattice phase. Raw bright/dark
        # extrema cannot decide whether V4 is aligned to a real yarn or a gap.
        # Remove the full-track median shift (phase) and bound only deviations.
        # A separate P2 competition will evaluate phase without leaking labels.
        global_phase_shift=float(np.median(displacement))
        displacement=np.clip(displacement-global_phase_shift,-.17*pitch,.17*pitch)
        info['suppressed_global_phase_shift_px']=round(global_phase_shift,3)
        info['applied_median_abs_shift_px']=round(float(np.median(abs(displacement))),3)
        original_dedup,s=_arclength(original)
        d=np.interp(s,t,displacement)
        n=np.column_stack([np.interp(s,t,normal[:,c]) for c in range(2)])
        n/=np.maximum(np.linalg.norm(n,axis=1,keepdims=True),1e-6)
        refined=original_dedup+n*d[:,None]
        output.append(np.round(refined,3).tolist())
        reports.append(info)
    return output,dict(candidate_pitch_proxy_px=round(pitch,3),
                       input_count=len(tracks),output_count=len(output),
                       refined_count=sum(x['status']=='IMAGE_SUPPORTED_CANDIDATE_REFINEMENT' for x in reports),
                       abstained_count=sum(x['status'].startswith('ABSTAIN') for x in reports),
                       per_track=reports,physical_yarn_identity_verified=False,
                       note='Image-only candidate refinement. Operator labels are never localization inputs.')

def refine_v5_candidates(image,v4,config=None):
    first,A=refine_family(image,v4['first'],config=config)
    second,B=refine_family(image,v4['second'],config=config)
    return dict(first=first,second=second,family_A=A,family_B=B,
                status='EXPERIMENTAL_V51_G1_LOCALIZATION_ONLY',
                physical_yarn_count_verified=False,reuses_v4_candidate_ids=True)
