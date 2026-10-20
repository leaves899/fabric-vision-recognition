"""Experiment 2: fixed weak human segments, three geometry connection rules."""
import argparse
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
from .common import ROOT,panel,read_json,save_json,sha
from .graph import connect,score_same_only,feature
from benchmark.p0_operator_line_audit import _camera_image,convert_zoom_to_camera


def dashed(draw,a,b,fill,width=2):
    a=np.asarray(a);b=np.asarray(b);d=float(np.linalg.norm(b-a));steps=max(1,int(d/5))
    for i in range(0,steps,2):draw.line([tuple(a+(b-a)*i/steps),tuple(a+(b-a)*min(i+1,steps)/steps)],fill=fill,width=width)


def overlay(rgb,segments,result):
    im=Image.fromarray(rgb.copy());d=ImageDraw.Draw(im)
    groups={i:g for g,members in enumerate(result['groups']) for i in members}
    for i,s in enumerate(segments):
        p=np.asarray(s['points']);d.line([tuple(q) for q in p],fill='#27ddd3',width=3)
        d.text(tuple(p.mean(0)),f"{s['id']}/G{groups[i]+1}",fill='#ffe375',stroke_width=1,stroke_fill='#101924')
    for a,b in result['edges']:
        pa,pb=feature(segments[a]['points'])['ends'],feature(segments[b]['points'])['ends']
        _,i,j=min((np.linalg.norm(x-y),i,j) for i,x in enumerate(pa) for j,y in enumerate(pb))
        dashed(d,pa[i],pb[j],'#ff72ba')
    return np.asarray(im)


def transformed(segments,degrees=0,scale=1):
    rad=np.radians(degrees);r=np.array([[np.cos(rad),-np.sin(rad)],[np.sin(rad),np.cos(rad)]])*scale
    return [{**s,'points':(np.asarray(s['points'])@r.T).tolist()} for s in segments]


def run(out):
    rows=[]
    for number in (1,3,6):
        ident=f'U20261013_{number:02d}';path=ROOT/'datasets/physical_evidence_labels/manual_image_reviews'/f'{ident}.json'
        review=read_json(path);bgr,provenance=_camera_image(ROOT,review);rgb=bgr[...,::-1].copy()
        seg=[{'id':r['id'],'points':convert_zoom_to_camera(r['geometry']['points'],provenance['crop_original_xyxy']),
              'evidence':'DRAFT_OPERATOR_VISIBLE_STROKE','family':None}
             for r in review['regions'] if r['kind']=='APPARENT_VISIBLE_YARN']
        methods=[];images=[];titles=[]
        bounds=np.concatenate([np.asarray(s['points']) for s in seg]);lo=np.maximum(bounds.min(0).astype(int)-35,0)
        hi=np.minimum(bounds.max(0).astype(int)+35,np.array([rgb.shape[1],rgb.shape[0]]))
        for method in ('axis_nearest','local_tangent','assignment'):
            result=connect(seg,method)
            score=score_same_only(seg,result,review['relations'])
            original={tuple(sorted(e)) for e in result['edges']};checks=[]
            for degree,scale in ((45,1),(90,1),(180,1),(0,.5),(0,2)):
                alt=connect(transformed(seg,degree,scale),method)
                other={tuple(sorted(e)) for e in alt['edges']};union=original|other
                checks.append({'rotation_deg':degree,'coordinate_scale':scale,'edge_jaccard':len(original&other)/len(union) if union else 1,
                               'kind':'COORDINATE_MECHANICS_NOT_NEW_PHOTO'})
            methods.append({'method':method,'score':score,'transform_checks':checks})
            save_json(out/'experiment2'/f'{ident}_{method}.json',{'segments':seg,'connections':result,
                      'weak_reference_posthoc_score':score,'review_sha256':sha(path),'provenance':provenance})
            im=overlay(rgb,seg,result);images.append(im[lo[1]:hi[1],lo[0]:hi[0]]);titles.append(method+' / solid observed; dashed inferred')
        panel(out/'experiment2'/f'{ident}.png',images,titles,640)
        rows.append({'id':ident,'observed_segments':len(seg),'review_state':review['review_state'],
            'reference_quality':'DRAFT_PHONE_REVIEW_NOT_INDEPENDENT_PHYSICAL_GT','methods':methods})
        print(ident,methods,flush=True)
    save_json(out/'experiment2.json',{'status':'EXECUTED_FIXED_WEAK_SEGMENTS','rows':rows,
        'axis_baseline':'Axis-aligned nearest-neighbor style adapted to strokes; not exact upstream region-area routine',
        'not_evaluated':['pixel segmentation accuracy','false link precision','independent physical count'],
        'link_inputs':'geometry only; annotation relations used only after prediction'})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);run(p.parse_args().out)
