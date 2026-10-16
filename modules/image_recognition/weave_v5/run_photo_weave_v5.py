#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V5 multi-evidence weave candidate identification, input RGB fabric photo.

First finds chromatic families independently and checks alternating rows and
half-cycle phase (plain candidate). If no independent chroma-family signal,
falls back to V4 bright-float instance segmentation and geometric twill model.
No known fabric class is passed to either detector. Physical over/under remains
unverified until opposing yarn bodies and crossing occlusions are resolved.

  python run_photo_weave_v5.py --image images/fabric.png --out results --rois 3
"""
from __future__ import annotations
import argparse,json
from pathlib import Path
from PIL import Image
from color_plain import analyze as detect_color_plain
from float_segmentation_v3 import run_photo as segment
from weave_topology_v4 import run_one as topology


def choose_rois(img,n=3,tile=640):
    w,h=img.size
    if min(w,h)<tile:raise ValueError('each image dimension must be >= 640px')
    cx=w//2-tile//2;cy=h//2-tile//2
    if n==1:offs=[0]
    elif n==3:offs=[-min(500,w//5),0,min(500,w//5)]
    else:raise ValueError('rois must be 1 or 3')
    boxes=[];seen=set()
    for o in offs:
        x=max(0,min(w-tile,cx+o));y=max(0,min(h-tile,cy))
        if (x,y) not in seen:
            boxes.append((x,y,x+tile,y+tile));seen.add((x,y))
    return boxes


def summarize(regions):
    valid=[]
    for r in regions:
        if r['status']=='plain_candidate_from_color_topology':valid.append('plain_1_1')
        elif r['status']=='distinct_model_candidate':valid.append(r['inferred_candidate']['name'])
    counts={}
    for n in valid:counts[n]=counts.get(n,0)+1
    ranked=sorted(counts.items(),key=lambda a:(-a[1],a[0]))
    # Do not claim consensus when one ROI only; only mark as candidate
    min_votes=1 if len(regions)==1 else 2
    consensus=ranked[0][0] if ranked and ranked[0][1]>=min_votes and (len(ranked)==1 or ranked[0][1]>ranked[1][1]) else None
    return dict(organization_candidate=consensus,
                status=('multi_region_candidate' if len(regions)>1 else 'single_region_candidate') if consensus else 'unresolved',
                roi_count=len(regions),roi_valid=len(valid),votes=ranked,
                physical_0_1_verified=False,S_Z_direction='unresolved',
                note='Hypothesis only; known user label not used for inference.')


def run(image,out,rois=3):
    image=Path(image);out=Path(out);out.mkdir(parents=True,exist_ok=True)
    photo=Image.open(image).convert('RGB')
    boxes=choose_rois(photo,rois)
    regions=[]
    for i,b in enumerate(boxes):
        key=f'photo_{i:02d}_crop';tile=out/'tiles'/f'{key}.png';tile.parent.mkdir(exist_ok=True,parents=True)
        photo.crop(b).save(tile)
        color=detect_color_plain(tile,out/'color'/key)
        color['orientation_correction_deg']=0
        # For a chromatic textile whose yarn rows are vertical in the photo,
        # test the orthogonal orientation before reverting to V4 geometry.
        if (color['status']!='plain_candidate_from_color_topology'
            and color.get('chroma_separation',0)>=12):
            rotated=out/'tiles'/f'{key}_rot90.png'
            photo.crop(b).rotate(90,expand=True).save(rotated)
            rotated_evidence=detect_color_plain(rotated,out/'color'/f'{key}_rot90')
            if rotated_evidence['status']=='plain_candidate_from_color_topology':
                color=rotated_evidence
                color['orientation_correction_deg']=90
        if color['status']=='plain_candidate_from_color_topology':
            r={'image':key,'status':color['status'],'inferred_candidate':{'name':'plain_1_1'},
               'evidence_color_plain':color,'photo_box_xyxy':list(b),'topology_method':'two_chroma_family_alternating_rows',
               'hypothetical_binary_weave_matrix':[[1,0],[0,1]],'physical_over_under_matrix':'not_observed'}
        else:
            segdir=out/'v3'/key
            segment(tile,segdir)
            r=topology(tile,segdir,out/'v4'/key)
            r['evidence_color_plain']=color
            r['photo_box_xyxy']=list(b)
            r['topology_method']='visible_bright_float_geometry'
        regions.append(r)
        print(f'{key}: {r["status"]} / {r.get("inferred_candidate",{}).get("name")}',flush=True)
    result={'image':str(image),'image_size':photo.size,'summary':summarize(regions),'regions':regions}
    (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--image',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--rois',choices=[1,3],type=int,default=3)
    args=p.parse_args()
    out=run(args.image,args.out,args.rois)
    print(json.dumps(out['summary'],ensure_ascii=False,indent=2))
