#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unsupervised fabric FLOAT-TO-TOPOLOGY hypothesis recovery.

Inputs: RGB image plus v3 VISIBLE float instance map and candidates.
Outputs: measured 2-D translation lattice; typed float entities; competing
weave hypotheses; *hypothetical* crossings; physical coverage evidence.

Never uses known fabric weave class for inference. A white connected region is
not necessarily a full physical float, and lack of white is NOT a physical 0.
Missing independent evidence yields an unresolved classification.
"""
from __future__ import annotations
import argparse, csv, json, math
from pathlib import Path
import cv2, numpy as np, pandas as pd
from scipy.ndimage import gaussian_filter, maximum_filter
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parent
FONT='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
FONT_BOLD='/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
def font(n=18,bold=False):
    try: return ImageFont.truetype(FONT_BOLD if bold else FONT,n)
    except OSError:return ImageFont.load_default()

def fangle(v):return (math.degrees(math.atan2(v[1],v[0]))+90)%180-90

def principal_angles(instance_img, rows):
    angles=[]
    for _,r in rows.iterrows():
        if str(r.quality)!='candidate' or not (40<r.center_x<600 and 40<r.center_y<600):continue
        id_=int(r.id[1:]);y,x=np.where(instance_img==id_)
        if len(x)<100:continue
        cov=np.cov(np.stack([x,y])); w,v=np.linalg.eigh(cov)
        vec=v[:,1]; a=(np.degrees(np.arctan2(vec[1],vec[0]))+90)%180-90
        ratio=w[1]/max(w[0],1)
        if ratio>1.6:angles.append(a)
    if not angles:return 0.
    # Median preserves majority instance orientation, downweighting merged outliers.
    return np.radians(np.median(angles))

def lag_peaks(points,radius=180):
    diff=points[:,None,:]-points[None,:,:]
    delta=diff.reshape(-1,2)
    D=np.linalg.norm(delta,axis=1);delta=delta[(D>22)&(D<radius-5)]
    H=np.zeros((2*radius+1,2*radius+1),np.float32)
    xi=np.rint(delta[:,0]).astype(int)+radius
    yi=np.rint(delta[:,1]).astype(int)+radius
    np.add.at(H,(yi,xi),1)
    S=gaussian_filter(H,3.7)
    is_peak=(S==maximum_filter(S,size=17))&(S>max(.023,float(S.max())*.12))
    ys,xs=np.where(is_peak)
    peaks=sorted([(float(S[y,x]),np.array([float(x-radius),float(y-radius)])) for y,x in zip(ys,xs)],key=lambda v:-v[0])
    return peaks

def candidate_bases(points, orientation, min_repeat=64, max_repeat=142):
    peaks=lag_peaks(points)
    u_candidates=[]
    for score,v in peaks:
        if v[0]<0:continue
        d=np.linalg.norm(v)
        delta=abs(((fangle(v)-math.degrees(orientation)+90)%180)-90)
        # Repeat spacing should exceed one visible float's transverse width.
        if max(64,min_repeat)<d<max_repeat and delta<(26 if abs(math.degrees(orientation))>30 else 13):
            u_candidates.append((score,v))
    # For diagonally oriented yarns, the u vector may point up-left
    if not u_candidates:
        for score,v in peaks:
            d=np.linalg.norm(v)
            delta=abs(((fangle(v)-math.degrees(orientation)+90)%180)-90)
            if max(55,min_repeat)<d<max_repeat and delta<(35 if abs(math.degrees(orientation))>30 else 18) and v[0]>0:u_candidates.append((score,v))
    bases=[]
    for us,u in u_candidates[:6]:
        if u[0]<0:u=-u
        un=np.linalg.norm(u)
        for vs,v0 in peaks[:45]:
            v=v0.copy()
            if (u[0]*v[1]-u[1]*v[0])<0:v=-v
            # Adjacent row displacement must be geometrically independent.
            normal=float((u[0]*v[1]-u[1]*v[0])/un)
            tangential=float(np.dot(u,v)/(un*un))
            # normalize v by changing repeat index
            v=v-round(tangential)*u
            tangential=float(np.dot(u,v)/(un*un))
            normal=float((u[0]*v[1]-u[1]*v[0])/un)
            if 23<normal<117 and abs(tangential)<.48 and np.linalg.norm(v)<135:
                if abs(tangential)<.06:continue
                bases.append((us+vs,u.copy(),v.copy()))
    return sorted(bases,key=lambda p:-p[0])[:55]

def lattice_fit(points,bases):
    # Find coherent affine point lattice. Float centers are the observations;
    # no fixed grid is used in instance segmentation or point collection.
    best=None
    for _,u,v in bases:
        B=np.stack([u,v],axis=1)
        if abs(np.linalg.det(B))<900:continue
        inv=np.linalg.inv(B)
        # Multiple possible phases; choose the one that explains the most observed instances.
        for o in points[::max(1,len(points)//22)]:
            q=(points-o)@inv.T
            qr=np.rint(q)
            residual=np.linalg.norm((q-qr)@B.T,axis=1)
            close=(residual<min(15.,.21*np.linalg.norm(u)))
            count=int(close.sum())
            if count<10:continue
            support=float(np.sum(np.exp(-.5*(residual/9)**2)))
            val=support-0.18*np.median(residual)+.007*count
            if best is None or val>best['initial_score']:
                best=dict(initial_score=val, o=o.copy(), B=B.copy())
    if best is None:return None
    o=best['o'];B=best['B']
    for iteration in range(6):
        q=(points-o)@np.linalg.inv(B).T
        qr=np.rint(q).astype(int)
        residual=np.linalg.norm((q-qr)@B.T,axis=1)
        selected=residual<min(17.,.23*np.linalg.norm(B[:,0]))
        if selected.sum()<9:break
        M=np.column_stack([np.ones(selected.sum()),qr[selected]])
        coef=np.linalg.lstsq(M,points[selected],rcond=None)[0]
        no=coef[0];nB=coef[1:].T
        if abs(np.linalg.det(nB))<800:break
        if np.linalg.norm(nB-B)<10:
            o=no;B=nB
        else:break
    q=(points-o)@np.linalg.inv(B).T
    idx=np.rint(q).astype(int)
    residual=np.linalg.norm((q-idx)@B.T,axis=1)
    good=residual<min(17.,.23*np.linalg.norm(B[:,0]))
    return dict(origin=o,repeat_vector=B[:,0],advance_vector=B[:,1],pairs=idx,
        residual=residual,good=good,coverage=float(good.mean()),
        median_error=float(np.median(residual[good])) if good.any() else 999.)

def observed_float_lengths(instance_img,rows,u):
    along=u/np.linalg.norm(u)
    out=[]
    for _,r in rows.iterrows():
        if str(r.quality)!='candidate':continue
        if not (40<r.center_x<600 and 40<r.center_y<600):continue
        tag=int(str(r.id)[1:]);y,x=np.where(instance_img==tag)
        if len(x)<130:continue
        pos=x*along[0]+y*along[1]
        length=float(np.percentile(pos,99)-np.percentile(pos,1))
        out.append((tag,length))
    return out

def score_models(model,lengths):
    u=model['repeat_vector'];v=model['advance_vector'];u_len=np.linalg.norm(u)
    advance=float(np.dot(u,v)/np.dot(u,u))
    lengths_arr=np.array([l for _,l in lengths]); med=float(np.median(lengths_arr)) if len(lengths_arr) else 0
    # n=2..6 for broad unsupervised search; physical float length = on crossings
    # x pitch, with an edge concession of 0.2 pitches to account for fiber boundary.
    candidates=[]
    for n in range(2,7):
        # Photos can have small yarn skew; phase-advance alone is not proof.
        phase_error=abs(abs(advance)-1/n)
        for on in range(1,n):
            step=u_len/n
            predicted=(on-0.4)*step
            # Width error tolerance accounts for actual yarn morphology and uncertain segment edges.
            sigma=max(7., .35*step)
            width_error=abs(med-predicted)/sigma
            phase_z=phase_error/.022
            cost=float(np.sqrt(width_error**2+phase_z**2))
            candidates.append(dict(name=f'{on}/{n-on}',period=n,over_count=on,
                float_repeat_px=round(float(u_len),2),crossing_pitch_est_px=round(float(step),2),
                measured_float_length_px=round(med,2),predicted_float_length_px=round(predicted,2),
                phase_advance=round(advance,4),phase_residual=round(phase_error,4),
                length_residual=round(float(med-predicted),2),score=round(cost,4),
                # S/Z not reported without verified warp/weft identity and face orientation.
                diagonal_image='\\' if advance>0 else '/'))
    candidates.sort(key=lambda x:x['score'])
    return candidates

def latent_matrix(model, top, instance_img, img, instances):
    """One crossing-hypothesis per cell, placed relative to REAL FLOAT CENTERS.

    Unlike the old fixed-grid labeler, no candidate creates or splits an
    actual float instance. Physical 0 remains an unverified hypothesis until
    dark-yarn topology / opposing family is actually observed.
    """
    u=np.asarray(model['repeat_vector']);u=u/np.linalg.norm(u)
    pitch=top['crossing_pitch_est_px']; n=top['period']; on=top['over_count']
    h,w=instance_img.shape
    out=[]
    for i,(center,idx,error,good) in enumerate(zip(model['observations'],model['pairs'],model['residual'],model['good'])):
        if not good:continue
        tag=int(str(instances.iloc[i].id)[1:])
        for j in range(n):
            offset=(j-(on-1)/2)*pitch
            point=center+offset*u
            cx,cy=np.rint(point).astype(int)
            if not (8<cx<w-8 and 8<cy<h-8):continue
            rr=4; region=instance_img[cy-rr:cy+rr+1,cx-rr:cx+rr+1]
            patch=img[cy-rr:cy+rr+1,cx-rr:cx+rr+1]
            gray=float(cv2.cvtColor(patch,cv2.COLOR_RGB2GRAY).mean())
            own=float((region==tag).mean());any_bright=float((region>0).mean())
            model_bit=1 if j<on else 0
            evidence='own_float' if own>=.5 else ('other_bright' if any_bright>.5 else ('dark_optical' if gray<115 else 'ambiguous'))
            out.append(dict(float_id=instances.iloc[i].id,row=int(idx[1]),repeat_index=int(idx[0]),cell_index=j,
                x=round(float(point[0]),1),y=round(float(point[1]),1),
                model_bit=model_bit,evidence=evidence,own_float_coverage=round(own,3),
                all_bright_coverage=round(any_bright,3),mean_gray=round(gray,1),
                physical_bit_verified=False))
    return out

def candidate_weave_matrix(top,shift_sign=1):
    n=int(top['period']);on=int(top['over_count']);shift_sign=1 if shift_sign>=0 else -1
    return [[int((j-shift_sign*r)%n<on) for j in range(n)] for r in range(n)]

def plot_evidence(rgb, model, lengths, cands, out, measurements, named):
    arr=np.asarray(rgb.convert('RGB'));H,W=arr.shape[:2]
    scale=2; canvas=Image.new('RGB',(W*scale+380,H*scale+98),'#f5f7fb')
    photo=rgb.resize((W*scale,H*scale));canvas.paste(photo,(16,62))
    d=ImageDraw.Draw(canvas)
    d.text((16,14),f'{named} | measured float lattice + candidate topology',font=font(22,True),fill='#1f2937')
    u,v=model['repeat_vector'],model['advance_vector'];o=model['origin']
    # Measured center circles; link a few observed lattice sites at predicted repeat vectors
    for item,err,good in zip(model['observations'],model['residual'],model['good']):
        x=int(item[0]*scale+16);y=int(item[1]*scale+62)
        col='#22c55e' if good else '#f59e0b'
        d.ellipse((x-6,y-6,x+6,y+6),outline=col,width=2)
    # Only visualize the candidate crossings INSIDE measured bright floats, not inferred 0s
    for m in measurements:
        if m['model_bit']!=1 or m['evidence']!='own_float':continue
        x=int(m['x']*scale+16);y=int(m['y']*scale+62)
        d.ellipse((x-3,y-3,x+3,y+3),fill='#2563eb')
    xx=W*scale+36;yy=72
    blocks=[('Inferred repeat lattice',19,True),
        (f'float count: {len(model["observations"])}',15,False),
        (f'lattice support: {100*model["coverage"]:.1f}%',15,False),
        (f'median center error: {model["median_error"]:.1f}px',15,False),
        (f'u = ({u[0]:.1f}, {u[1]:.1f})',14,False),
        (f'v = ({v[0]:.1f}, {v[1]:.1f})',14,False),
        ('',14,False), ('Weave model candidates',18,True)]
    blocks.extend([(f'{r+1}. {x["name"]}: cost {x["score"]:.2f}',16,r==0) for r,x in enumerate(cands[:5])])
    blocks.extend([('',14,False), ('GREEN: measured float center',13,False),
        ('BLUE: modeled cells inside actual floats',13,False),
        ('ORANGE: off-lattice candidates',13,False),
        ('0/1 physical crossings NOT verified',14,True),
        ('Classification requires held-out truth',13,False)])
    for txt,sz,bold in blocks:
        d.text((xx,yy),txt,font=font(sz,bold),fill='#1f2937');yy+=36 if sz>=16 else 29
    canvas.save(out,optimize=True)

def run_one(image_path,source_path,outdir):
    outdir.mkdir(parents=True,exist_ok=True)
    rgb=Image.open(image_path).convert('RGB'); img=np.array(rgb)
    key=image_path.stem
    ids=np.array(Image.open(source_path/(key+'_instance_ids.png')))
    floats=pd.read_csv(source_path/(key+'_floats.csv'))
    fl=floats[(floats.quality=='candidate') & floats.center_x.between(32,608)& floats.center_y.between(32,608)]
    coords=fl[['center_x','center_y']].to_numpy(float)
    theta=principal_angles(ids,floats)
    majors=[]
    for _,row in fl.iterrows():
        ys,xs=np.where(ids==int(row.id[1:]))
        if len(xs)<200:continue
        xy=np.stack([xs,ys],axis=1)
        ev,evec=np.linalg.eigh(np.cov(xy.T))
        vals=xy@evec[:,1]
        majors.append(np.percentile(vals,99)-np.percentile(vals,1))
    min_repeat=1.2*float(np.median(majors)) if majors else 64
    max_repeat=(1.6 if abs(np.degrees(theta))>30 else 1.75)*float(np.median(majors)) if majors else 142
    bases=candidate_bases(coords,theta,min_repeat,max_repeat)
    fit=lattice_fit(coords,bases)
    if fit is None:
        res={'image':key,'status':'unresolved_no_lattice','fcn_float_count':len(floats)}
        (outdir/'report.json').write_text(json.dumps(res,indent=2),encoding='utf-8');return res
    lengths=observed_float_lengths(ids,floats,fit['repeat_vector'])
    ranks=score_models(fit,lengths)
    fit['observations']=coords
    best=ranks[0]; second=ranks[1]
    gap=second['score']-best['score']
    candidate_model_ok=fit['coverage']>=.6 and fit['median_error']<=13 and best['score']<=2.0 and gap>=.55
    state='distinct_model_candidate' if candidate_model_ok else 'ambiguous_organization'
    if fit['coverage']<.5:state='unresolved_lattice'
    values=latent_matrix(fit,best,ids,img,fl.reset_index(drop=True))
    with (outdir/'latent_crossings.csv').open('w',newline='',encoding='utf-8') as f:
        if values: w=csv.DictWriter(f,fieldnames=list(values[0]));w.writeheader();w.writerows(values)
    with (outdir/'float_entities.csv').open('w',newline='',encoding='utf-8') as f:
        keys=['float_id','row_lattice','repeat_k','center_x','center_y','lattice_residual_px','segmentation_quality','entity_meaning','physical_over_under']
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader()
        for i,(_,r) in enumerate(fl.iterrows()):
            rr=int(fit['pairs'][i,1]);k=int(fit['pairs'][i,0])
            w.writerow(dict(float_id=r.id,row_lattice=rr,repeat_k=k,center_x=r.center_x,center_y=r.center_y,
                lattice_residual_px=round(float(fit['residual'][i]),2),segmentation_quality=r.quality,
                entity_meaning='visible bright-yarn float candidate',physical_over_under='unverified'))
    matrix=candidate_weave_matrix(best,1 if best['phase_advance']>=0 else -1)
    evidence_stats={label:sum(x['evidence']==label for x in values) for label in ('own_float','other_bright','dark_optical','ambiguous')}
    over=[x for x in values if x['model_bit']==1]
    under=[x for x in values if x['model_bit']==0]
    support_over=sum(x['evidence']=='own_float' for x in over)/max(1,len(over))
    support_dark=sum(x['evidence']=='dark_optical' for x in under)/max(1,len(under))
    report=dict(image=key,status=state,float_count_total=int(len(floats)),centers_used=int(len(coords)),
        observed_floats_lattice_coverage=round(fit['coverage'],4),fit_median_error_px=round(fit['median_error'],3),
        observed_major_axis_deg=round(float(np.degrees(theta)),2),
        float_repeat_vector_xy=np.round(fit['repeat_vector'],3).tolist(),
        row_advance_vector_xy=np.round(fit['advance_vector'],3).tolist(),
        measured_float_length_med_px=round(float(np.median([l for _,l in lengths])),2) if lengths else None,
        inferred_candidate=best,runner_up=second,margin_to_runner_up=round(float(gap),3),
        hypothetical_binary_weave_matrix=matrix,
        evidence_statistics=evidence_stats,
        positive_crossing_photo_support=round(support_over,3),
        negative_crossing_dark_optical_fraction=round(support_dark,3),
        models=ranks,physical_over_under_matrix='not_observed',
        observed_top_yarn_identity='unknown_without_warp_weft_confirmation',
        observable_direction='photo-plane only; not fabric-face S/Z',
        source='real-photo segmentation, center lattice fit, candidate length/phase comparison',
        note='Candidate models are hypotheses. A dark pixel is not a physical under-crossing. No source labels or weave truth used.')
    (outdir/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    plot_evidence(rgb,fit,lengths,ranks,outdir/'float_topology_audit.png',values,key)
    return report

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--images',type=Path,default=ROOT/'batch_input');p.add_argument('--v3',type=Path,default=ROOT/'v3_results');p.add_argument('--out',type=Path,default=ROOT/'v4_results')
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    reports=[]
    for pic in sorted(a.images.glob('photo_*_crop.png')):
        src=a.v3/pic.stem
        try:r=run_one(pic,src,a.out/pic.stem)
        except Exception as e:
            r={'image':pic.stem,'status':'error','detail':str(e)}
            (a.out/pic.stem).mkdir(exist_ok=True)
            (a.out/pic.stem/'error.txt').write_text(str(e),encoding='utf-8')
        reports.append(r)
        print(pic.stem,r.get('status'),r.get('inferred_candidate',{}).get('name'),r.get('observed_floats_lattice_coverage'),flush=True)
    cols=['image','status','float_count_total','observed_floats_lattice_coverage','fit_median_error_px','measured_float_length_med_px','margin_to_runner_up']
    out=[]
    for r in reports:
        row={k:r.get(k) for k in cols};row.update(best_model=r.get('inferred_candidate',{}).get('name'),next_model=r.get('runner_up',{}).get('name'))
        out.append(row)
    pd.DataFrame(out).to_csv(a.out/'batch_summary.csv',index=False,encoding='utf-8-sig')
if __name__=='__main__':main()
