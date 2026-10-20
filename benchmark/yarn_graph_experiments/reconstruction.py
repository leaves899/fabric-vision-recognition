"""Experiment 3: evidence-bearing regions -> candidate paths -> sparse crossings."""
from __future__ import annotations
import argparse
import collections
import time
from pathlib import Path
import cv2
import numpy as np
from PIL import Image,ImageDraw
from .common import ROOT,PALETTE,center_crop,decision,panel,read_json,read_rgb,save_json,sha
from .graph import angle_delta,connect,feature
from .connections import dashed
from .single_rgb import load_student,predict
from .weave import match


def fragments(labels):
    """Retain full region boundaries and observed-mask-supported local center paths."""
    segments=[];rejected=collections.Counter();instance_map=np.zeros(labels.shape,np.int32)
    for cls,family in ((0,'A'),(2,'B')):
        count,cc,stats,_=cv2.connectedComponentsWithStats((labels==cls).astype(np.uint8),8)
        for k in range(1,count):
            x,y,w,h,area=map(int,stats[k])
            if area<24:rejected['small_region']+=1;continue
            mask=(cc[y:y+h,x:x+w]==k).astype(np.uint8);yy,xx=np.nonzero(mask)
            pts=np.column_stack((xx+x,yy+y)).astype(float);f=feature(pts);u=f['tangent'];normal=np.array([-u[1],u[0]])
            t=(pts-f['center'])@u;v=(pts-f['center'])@normal
            eigen=np.linalg.eigvalsh(np.cov(pts.T));aspect=float(np.sqrt(eigen[-1]/max(eigen[0],1e-5)))
            if aspect<1.5 or f['length']<6:rejected['nonelongated_region']+=1;continue
            bins=np.floor((t-t.min())/2).astype(int);path=[];widths=[]
            for b in np.unique(bins):
                p=pts[bins==b];mid=p.mean(0)
                # An actual region pixel closest to transverse centroid; never snap to a virtual lattice.
                path.append(p[np.linalg.norm(p-mid,axis=1).argmin()])
                nv=v[bins==b];widths.append(float(nv.max()-nv.min()+1))
            runs=[];run=[path[0]]
            for a,b in zip(path,path[1:]):
                steps=max(2,int(np.ceil(np.linalg.norm(b-a)*2)));samples=np.rint(np.linspace(a,b,steps)).astype(int)
                supported=float(np.mean(cc[samples[:,1],samples[:,0]]==k))
                if np.linalg.norm(b-a)<=6 and supported>=.95:run.append(b)
                else:
                    if len(run)>=2:runs.append(np.array(run))
                    run=[b]
            if len(run)>=2:runs.append(np.array(run))
            if not runs:rejected['no_supported_center_path']+=1;continue
            longest=max(runs,key=lambda r:np.linalg.norm(np.diff(r,axis=0),axis=1).sum())
            if np.linalg.norm(np.diff(longest,axis=0),axis=1).sum()<6:rejected['short_center_path']+=1;continue
            contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
            idx=len(segments)+1;instance_map[cc==k]=idx
            segments.append({'id':f'{family}{idx:04d}','family':family,'points':longest.tolist(),
                'observed_runs':[p.tolist() for p in runs],'contours':[(c[:,0,:]+[x,y]).tolist() for c in contours],
                'bbox_xywh':[x,y,w,h],'area_px':area,'aspect_ratio':aspect,
                'apparent_mask_width_px_median':float(np.median(widths)),
                'apparent_mask_width_px_p10':float(np.quantile(widths,.1)),
                'angle_image_y_down_deg':float(np.degrees(np.arctan2(u[1],u[0]))%180),
                'evidence':'MODEL_VISIBLE_REGION_CANDIDATE','physical_identity_verified':False})
    return segments,instance_map,dict(rejected)


def direction(segments):
    if not segments:return None
    fs=[feature(s['points']) for s in segments];cov=sum(f['length']*np.outer(f['tangent'],f['tangent']) for f in fs)
    ev,vec=np.linalg.eigh(cov);u=vec[:,-1]
    if u[0]<0:u=-u
    return {'angle_image_y_down_deg':float(np.degrees(np.arctan2(u[1],u[0]))%180),
            'concentration':float(ev[-1]/ev.sum()),'unit':u.tolist(),'physical_direction_verified':False}


def group_paths(segments,result):
    paths=[]
    for gi,members in enumerate(result['groups']):
        lines=[];observed=[]
        for i in members:
            p=np.asarray(segments[i]['points']);lines.extend(zip(p[:-1],p[1:]));observed.extend([True]*(len(p)-1))
        for a,b in result['edges']:
            if a not in members:continue
            pa,pb=feature(segments[a]['points'])['ends'],feature(segments[b]['points'])['ends']
            _,i,j=min((np.linalg.norm(x-y),i,j) for i,x in enumerate(pa) for j,y in enumerate(pb))
            # Use actually observed path endpoints for the inferred occlusion bridge.
            ap=np.asarray(segments[a]['points']);bp=np.asarray(segments[b]['points'])
            ea=min([ap[0],ap[-1]],key=lambda p:np.linalg.norm(p-pa[i]));eb=min([bp[0],bp[-1]],key=lambda p:np.linalg.norm(p-pb[j]))
            lines.append((ea,eb));observed.append(False)
        arr=np.asarray(lines);allpoints=np.concatenate([np.asarray(segments[i]['points']) for i in members])
        paths.append({'id':f'G{gi+1:04d}','members':members,'family':segments[members[0]]['family'],
            'lines':arr,'observed':np.array(observed),'center':allpoints.mean(0),
            'bounds':[arr.min((0,1)),arr.max((0,1))]})
    return paths


def intersections(a,b):
    if np.any(a['bounds'][1]<b['bounds'][0]) or np.any(b['bounds'][1]<a['bounds'][0]):return []
    aa=a['lines'];bb=b['lines'];p=aa[:,0,None,:];r=aa[:,1,None,:]-p
    q=bb[None,:,0,:];s=bb[None,:,1,:]-q
    cross=lambda x,y:x[...,0]*y[...,1]-x[...,1]*y[...,0]
    den=cross(r,s);valid=abs(den)>1e-9;safe=np.where(valid,den,1.)
    t=cross(q-p,s)/safe;u=cross(q-p,r)/safe
    ii,jj=np.where(valid&(t>=0)&(t<=1)&(u>=0)&(u<=1));found=[]
    for i,j in zip(ii,jj):
        point=aa[i,0]+t[i,j]*(aa[i,1]-aa[i,0])
        if any(np.linalg.norm(point-f['xy'])<2 for f in found):continue
        found.append({'xy':point,'a_visible_path':bool(a['observed'][i]),'b_visible_path':bool(b['observed'][j])})
    return found


def sparse_crossings(segments,inst,result,dirs):
    paths=group_paths(segments,result);by_family={}
    for family in ('A','B'):
        d=dirs[family];unit=np.asarray(d['unit']) if d else np.array([1.,0.]);normal=np.array([-unit[1],unit[0]])
        by_family[family]=sorted([p for p in paths if p['family']==family],key=lambda p:float(p['center']@normal))
    aa,bb=by_family['A'],by_family['B'];matrix=np.full((len(aa),len(bb)),-1,np.int8);cells=[]
    for i,a in enumerate(aa):
        for j,b in enumerate(bb):
            hits=intersections(a,b)
            if len(hits)!=1:continue
            hit=hits[0];x,y=np.rint(hit['xy']).astype(int)
            if x<1 or y<1 or x>=inst.shape[1]-1 or y>=inst.shape[0]-1:continue
            support=inst[y-1:y+2,x-1:x+2]
            a_support=float(np.isin(support,np.array(a['members'])+1).mean())
            b_support=float(np.isin(support,np.array(b['members'])+1).mean())
            value=-1
            if hit['a_visible_path'] and not hit['b_visible_path'] and a_support>=.75:value=1
            if hit['b_visible_path'] and not hit['a_visible_path'] and b_support>=.75:value=0
            if value>=0:
                matrix[i,j]=value;cells.append({'row':i,'col':j,'xy':hit['xy'].tolist(),'A_over_B_candidate':value,
                   'A_group':a['id'],'B_group':b['id'],'visible_region_support':max(a_support,b_support),
                   'evidence':'VISIBLE_MODEL_REGION_PLUS_INFERRED_CROSSING_PATH','physical_verified':False})
    return matrix,cells,paths,by_family


def visualizations(rgb,segments,result,cells,matrix,folder):
    im=Image.fromarray(rgb);d=ImageDraw.Draw(im)
    group={i:g+1 for g,items in enumerate(result['groups']) for i in items}
    for i,s in enumerate(segments):
        color='#ff783c' if s['family']=='A' else '#21e3df'
        for run in s['observed_runs']:d.line([tuple(p) for p in run],fill=color,width=2)
        p=np.asarray(s['points']);d.text(tuple(p[len(p)//2]),f"{s['id']}/G{group[i]}",fill=color,stroke_width=1,stroke_fill='#12212f')
    for a,b in result['edges']:
        p=np.asarray(segments[a]['points']);q=np.asarray(segments[b]['points'])
        _,i,j=min((np.linalg.norm(x-y),i,j) for i,x in enumerate([p[0],p[-1]]) for j,y in enumerate([q[0],q[-1]]))
        dashed(d,[p[0],p[-1]][i],[q[0],q[-1]][j],'#fbd663')
    folder.mkdir(parents=True,exist_ok=True);im.save(folder/'yarns.png')
    cr=Image.fromarray(rgb);dr=ImageDraw.Draw(cr)
    for c in cells:
        x,y=c['xy'];col='#ff783c' if c['A_over_B_candidate'] else '#21e3df'
        dr.ellipse((x-4,y-4,x+4,y+4),outline=col,width=2)
    cr.save(folder/'crossings.png')
    if matrix.size:
        palette=np.array([[145,151,160],[38,204,212],[246,117,63]],np.uint8)
        mi=Image.fromarray(palette[matrix+1]);mi.resize((max(220,matrix.shape[1]*8),max(220,matrix.shape[0]*8)),Image.Resampling.NEAREST).save(folder/'matrix.png')
    else:
        blank=Image.new('RGB',(300,220),'#9299a3');ImageDraw.Draw(blank).text((12,20),'No supported matrix',fill='black');blank.save(folder/'matrix.png')
    Image.fromarray(rgb).save(folder/'original.png')
    return np.asarray(im)


def transect_measurements(rgb,segments,result,dirs,folder):
    """Intervals between observed candidates on a real transect; no completeness claim."""
    im=Image.fromarray(rgb);draw=ImageDraw.Draw(im);h,w=rgb.shape[:2];center=np.array([w/2,h/2]);length=np.hypot(h,w)
    paths=group_paths(segments,result);output={}
    for family in ('A','B'):
        if not dirs[family]:output[family]={'status':'NO_DIRECTION','intervals_px':[]};continue
        u=np.array(dirs[family]['unit']);normal=np.array([-u[1],u[0]])
        line=np.array([[center-normal*length,center+normal*length]])
        probe={'lines':line,'observed':np.array([True]),'bounds':[line.min((0,1)),line.max((0,1))]}
        hits=[]
        for path in paths:
            if path['family']!=family:continue
            intersections_found=intersections(path,probe)
            seen=[k for k in intersections_found if k['a_visible_path'] and 0<=k['xy'][0]<w and 0<=k['xy'][1]<h]
            if len(seen)==1:hits.append({'group':path['id'],'xy':seen[0]['xy'].tolist(),'position_px':float((seen[0]['xy']-center)@normal)})
        hits.sort(key=lambda p:p['position_px']);intervals=np.diff([p['position_px'] for p in hits])
        col='#ff783c' if family=='A' else '#21e3df'
        if hits:
            draw.line([tuple(hits[0]['xy']),tuple(hits[-1]['xy'])],fill=col,width=1)
            for k,hit in enumerate(hits):
                x,y=hit['xy'];draw.ellipse((x-3,y-3,x+3,y+3),outline=col,width=2)
                if k and k%2:
                    p=(np.array(hit['xy'])+np.array(hits[k-1]['xy']))/2
                    draw.text(tuple(p),f'{intervals[k-1]:.1f}px',fill='#fff08b',stroke_width=1,stroke_fill='#132131')
        output[family]={'status':'OBSERVED_CANDIDATE_INTERVALS_INCOMPLETE_ROOT_SET','hits':hits,'intervals_px':intervals.tolist(),
            'mean_interval_px':float(intervals.mean()) if len(intervals) else None,
            'interval_cv':float(intervals.std()/intervals.mean()) if len(intervals) and intervals.mean()>0 else None,
            'verified_adjacent_yarn_pitch':None,'physical_count':None}
    draw.rectangle((0,0,w,32),fill='#18232e');draw.text((8,8),'Observed candidate intervals only; missing yarns NOT filled',fill='white')
    im.save(folder/'spacing.png');return output


def analyze(rgb,probs,folder):
    labels=decision(probs);segments,inst,rejected=fragments(labels);result=connect(segments,'assignment')
    dirs={f:direction([s for s in segments if s['family']==f]) for f in ('A','B')}
    separation=angle_delta(np.array(dirs['A']['unit']),np.array(dirs['B']['unit'])) if all(dirs.values()) else None
    matrix,cells,paths,byfamily=sparse_crossings(segments,inst,result,dirs)
    weave=match(matrix)
    if separation is None or separation<30:weave.update(status='TWO_DIRECTIONS_UNSUPPORTED',coarse_candidate=None)
    widths={f:{'candidate_regions':sum(s['family']==f for s in segments),
          'median_visible_mask_width_px':float(np.median([s['apparent_mask_width_px_median'] for s in segments if s['family']==f])) if any(s['family']==f for s in segments) else None,
          'physical_width_verified':False} for f in ('A','B')}
    summary={'resolved_pixel_fraction':float((labels!=3).mean()),'class_fraction':[float((labels==k).mean()) for k in range(4)],
          'visible_region_candidates':len(segments),'inferred_links':len(result['edges']),
          'provisional_groups':len(result['groups']),'rejected_regions':rejected,'directions':dirs,'direction_separation_deg':separation,
          'widths':widths,'weave':weave,'physical_yarn_count':None,'warp_per_cm':None,'weft_per_cm':None,
          'root_index_continuity':'UNVERIFIED; no missing roots filled','coordinate_system':'native crop pixels, x right y down, angle modulo 180',
          'independent_physical_accuracy':None}
    overlay=visualizations(rgb,segments,result,cells,matrix,folder)
    summary['candidate_spacing']=transect_measurements(rgb,segments,result,dirs,folder)
    Image.fromarray(PALETTE[labels]).save(folder/'segmentation.png')
    np.savez_compressed(folder/'evidence.npz',probabilities=probs.astype(np.float16),instance_map=inst,sparse_matrix=matrix)
    save_json(folder/'evidence.json',{'summary':summary,'segments':segments,'graph':result,'crossings':cells,
        'matrix':matrix,'row_groups':[p['id'] for p in byfamily['A']],'col_groups':[p['id'] for p in byfamily['B']]})
    panel(folder/'panel.png',[rgb,PALETTE[labels],overlay],['Native crop','Model candidates; gray unknown','Solid: observed candidate / dash: inferred'],420)
    return summary


def run(out):
    data=read_json(out/'inputs.json');model=load_student(out);records=[]
    # Deliberately strip labels before calling any inference/reconstruction function.
    inputs=[{'id':r['id'],'image':r['image'],'sha256':r['sha256'],'domain':'FabricNET_microscope'} for r in data['fabricnet']]
    inputs.append({'id':'PHONE_ATTACHMENT','image':data['attachment'],'sha256':data['attachment_sha256'],'domain':'phone'})
    provenance=read_json(ROOT/'datasets/user_contributed/2026-10-13-six-fabric-images/image_provenance.json')
    for row in provenance['images']:
        inputs.append({'id':row['sample_id'],'image':str(ROOT/'datasets/user_contributed/2026-10-13-six-fabric-images'/row['original']),
                       'sha256':row['original_sha256'],'domain':'phone'})
    for row in inputs:
        started=time.perf_counter()
        if sha(row['image'])!=row['sha256']:raise ValueError('Source image changed: '+row['id'])
        rgb,box=center_crop(read_rgb(row['image']));probs=predict(model,rgb)
        summary=analyze(rgb,probs,out/'experiment3'/row['id'])
        record={**row,'source':'single_RGB_student','crop_original_xyxy':box,'summary':summary,'seconds':time.perf_counter()-started}
        records.append(record);save_json(out/'experiment3_predictions.json',{'rows':records,'labels_used_for_prediction':False})
        print(row['id'],summary['visible_region_candidates'],summary['inferred_links'],summary['weave']['status'],flush=True)
    # Paired-image structural control; no student is needed for these source pairs.
    for p in sorted((out/'paired').glob('*.npz')):
        started=time.perf_counter();z=np.load(p);ident='PAIRED_'+p.stem
        summary=analyze(z['rgb'],z['teacher_probs'].astype(np.float32),out/'experiment3'/ident)
        records.append({'id':ident,'domain':'paired_reference','source':'paired_FCN','source_npz_sha256':sha(p),
                        'summary':summary,'seconds':time.perf_counter()-started})
        save_json(out/'experiment3_predictions.json',{'rows':records,'labels_used_for_prediction':False})
        print(ident,summary['visible_region_candidates'],summary['inferred_links'],summary['weave']['status'],flush=True)
    # Coarse labels are used only after all predictions have been written.
    truth={r['id']:r['coarse_weave_label'] for r in data['fabricnet']};confusion={k:collections.Counter() for k in ('plain','twill','satin')}
    scored=[]
    for r in records:
        if r['id'] not in truth:continue
        pred=r['summary']['weave']['coarse_candidate'];gt=truth[r['id']];confusion[gt][pred or 'ABSTAIN']+=1
        scored.append({'id':r['id'],'label':gt,'conditional_candidate':pred,'correct_if_candidate':pred==gt if pred else None})
    accepted=[r for r in scored if r['conditional_candidate']]
    save_json(out/'experiment3.json',{'status':'EXECUTED','fabricnet_images':len(scored),'phone_images':sum(r['domain']=='phone' for r in records),
        'paired_controls':sum(r['domain']=='paired_reference' for r in records),'coarse_confusion_with_abstention':confusion,
        'conditional_template_coverage':len(accepted)/len(scored),'conditional_candidate_accuracy':sum(r['correct_if_candidate'] for r in accepted)/len(accepted) if accepted else None,
        'verified_physical_weave_accuracy':None,'subtype_accuracy':None,'scored_rows':scored,
        'limits':['Microscope data, not certified phone data','No subtype or pixel/instance truth','Template row/column adjacency unverified',
                  'Possible related FabricNET images; image-level counts are not independent fabric confidence intervals']})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);run(p.parse_args().out)
