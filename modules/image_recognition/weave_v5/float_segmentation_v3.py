#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Visible bright-yarn float instance segmentation v3 (real photo, no periodic grid).

Local threshold -> distance-field peaks -> foreground/background marker watershed
-> exclusive per-float instance masks -> independent quality audit.

This is VISIBLE bright-float segmentation, not a physical yarn-over/under 0/1 matrix.
In particular, dark gaps are NOT assigned a 0 label.

Usage:
  python float_segmentation_v3.py --image images/photo_05_crop.png --out results/v3_photo05
  python float_segmentation_v3.py --batch images --out results/v3_batch
  python float_segmentation_v3.py --image images/photo_05_crop.png --out tmp --self-check
"""
from __future__ import annotations
import argparse
import csv
import json
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import maximum_filter, label as cc_label, center_of_mass

HERE = Path(__file__).resolve().parent
FONT_REGULAR = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
FONT_BOLD = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'

def font(sz=20, bold=False):
    try:return ImageFont.truetype(FONT_BOLD if bold else FONT_REGULAR,sz)
    except OSError:return ImageFont.load_default()

def _prelim_shape(gray):
    """Estimate local float dimensions from high-intensity component shapes, not weave period."""
    h,w=gray.shape
    otsu,_=cv2.threshold(gray,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)
    high=otsu+.75*(float(np.percentile(gray,97))-otsu)
    core=np.uint8(gray>high)*255
    core=cv2.morphologyEx(core,cv2.MORPH_CLOSE,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(5,3)))
    core=cv2.morphologyEx(core,cv2.MORPH_OPEN,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(5,3)))
    n,lab,stats,cents=cv2.connectedComponentsWithStats(core,8)
    shapes=[]
    for i in range(1,n):
        x,y,bw,bh,area=map(int,stats[i]);cx,cy=cents[i]
        if (.00044*w*h<area<.0098*w*h and .021*w<bw<.195*w and
                .016*h<bh<.17*h and .029*w<cx<.971*w and .029*h<cy<.971*h):
            shapes.append((min(bw,bh),max(bw,bh)))
    # Fallback to image-scale statistics only if the old method returns no shapes
    minor=float(np.median([s[0] for s in shapes])) if shapes else max(15.,min(w,h)*.048)
    return minor,core,int(otsu),int(len(shapes)),float(high)

def segment_photo(rgb):
    arr=np.asarray(rgb.convert('RGB'))
    gray=cv2.cvtColor(arr,cv2.COLOR_RGB2GRAY)
    h,w=gray.shape
    minor,core,otsu,old_count,core_threshold=_prelim_shape(gray)
    hi=float(np.percentile(gray,95))
    broad_threshold=otsu+.12*(hi-otsu)
    broad=np.uint8(gray>broad_threshold)
    broad=cv2.morphologyEx(broad,cv2.MORPH_OPEN,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(3,3)))
    distance=cv2.GaussianBlur(cv2.distanceTransform(broad,cv2.DIST_L2,5),(5,5),0)
    # Image-derived minimum center separation: two thirds of the observed transverse float size.
    min_sep=max(12,min(34,round(.67*minor)))
    size=2*min_sep+1
    peaks=(distance>=maximum_filter(distance,size=size,mode='constant')-1e-6)&(distance>max(7.5,.23*minor))
    pad=max(8,round(min_sep*.48))
    peaks[:pad,:]=False;peaks[-pad:,:]=False;peaks[:,:pad]=False;peaks[:,-pad:]=False
    peak_comps,npeak=cc_label(peaks)
    peak_centers=center_of_mass(distance,peak_comps,np.arange(1,npeak+1)) if npeak else []
    pts=sorted([(float(x),float(y),float(distance[round(y),round(x)])) for y,x in peak_centers],key=lambda k:(k[1],k[0]))
    if not pts:
        return np.zeros_like(gray,dtype=np.int32),[],dict(status='no_bright_seeds',n_candidates=0)
    # True dark pixels are background marker only, never a physical '0' float.
    sure_background=gray < .72*otsu
    marks=np.zeros((h,w),dtype=np.int32)
    marks[sure_background]=1
    for tag,(x,y,r) in enumerate(pts,2):
        radius=max(2,min(5,int(round(r*.22))))
        cv2.circle(marks,(round(x),round(y)),radius,int(tag),-1)
    # Watershed is mutual exclusion: each ambiguous pixel belongs to at most one float.
    instance_map=cv2.watershed(cv2.cvtColor(arr,cv2.COLOR_RGB2LAB),marks)
    instance_map=np.where(instance_map>1,instance_map-1,0).astype(np.int32)
    instances=[]
    for tag,(px,py,radius) in enumerate(pts,1):
        local=np.uint8(instance_map==tag)
        area=int(local.sum())
        if area==0:continue
        m=cv2.moments(local,binaryImage=True)
        cx=float(m['m10']/m['m00']);cy=float(m['m01']/m['m00'])
        # snap the centroid back inside its own segmented pixels when necessary
        xi=int(round(cx));yi=int(round(cy))
        if not (0<=xi<w and 0<=yi<h and instance_map[yi,xi]==tag):
            yy,xx=np.where(local>0); k=int(np.argmin((xx-cx)**2+(yy-cy)**2));xi=int(xx[k]);yi=int(yy[k])
        contours,_=cv2.findContours(local,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        contours=sorted(contours,key=cv2.contourArea,reverse=True)
        largest=contours[0]
        bx,by,bw,bh=map(int,cv2.boundingRect(largest))
        contour=cv2.approxPolyDP(largest,1.0,closed=True).reshape(-1,2).astype(int).tolist()
        # Mean gray across the assigned whole float region, rather than bright seed only.
        mean_gray=float(np.mean(gray[local>0]))
        instances.append(dict(id=f'F{tag:03d}',tag=tag,seed_x=round(px,2),seed_y=round(py,2),
            center_x=round(cx,2),center_y=round(cy,2),label_x=xi,label_y=yi,
            bbox_x=bx,bbox_y=by,bbox_w=bw,bbox_h=bh,area_px=area,
            mean_gray=round(mean_gray,2),contour_xy=contour,
            connected_parts=len(contours),seed_radius=round(radius,2)))
    sizes=np.array([c['area_px'] for c in instances],dtype=float)
    med=float(np.median(sizes)) if len(sizes) else 1.0
    for c in instances:
        reasons=[]
        if c['area_px']>2.15*med:reasons.append('large_region_possible_merge')
        if c['area_px']<.40*med:reasons.append('small_region_possible_fragment')
        if c['connected_parts']>1:reasons.append('disconnected_pixels')
        if c['bbox_x']<=1 or c['bbox_y']<=1 or c['bbox_x']+c['bbox_w']>=w-2 or c['bbox_y']+c['bbox_h']>=h-2:
            reasons.append('image_edge_partial')
        c['review_reasons']=';'.join(reasons)
        c['quality']='review' if reasons else 'candidate'
    bright_pixels=(gray>broad_threshold)
    report=dict(status='processed',image_size=[w,h],preliminary_core_count=old_count,
        preliminary_core_threshold=round(core_threshold,2),otsu_gray=otsu,
        broad_brightness_threshold=round(broad_threshold,2),seed_min_separation_px=min_sep,
        float_candidate_count=len(instances),review_count=sum(c['quality']=='review' for c in instances),
        median_instance_area_px=round(med,1),
        old_core_foreground_coverage_pct=round(100*float(np.mean(core>0)),2),
        expanded_foreground_coverage_pct=round(100*float(np.mean(instance_map>0)),2),
        bright_pixel_coverage_pct=round(100*float(np.mean((instance_map>0)[bright_pixels])),2) if bright_pixels.any() else 0,
        physical_weave_matrix='not_extracted',dark_label_0_count=0,
        note='1 is a visible bright-float candidate; unknown dark does not imply physical 0; no fixed pitch/grid.')
    return instance_map,instances,report

def draw_mask_and_labels(rgb,inst_map,instances,path,scale=2.0):
    arr=np.asarray(rgb.convert('RGB'));h,w=arr.shape[:2]
    tint=arr.copy().astype(np.float32)
    fg=inst_map>0
    tint[fg]=tint[fg]*.65+np.array([8,196,235])*.35
    tint=np.uint8(np.clip(tint,0,255))
    # Exclusive per-instance boundary, not just global contour
    for c in instances:
        color=(255,190,15) if c['quality']=='review' else (0,238,238)
        region=np.uint8(inst_map==c['tag'])
        contours,_=cv2.findContours(region,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(tint,contours,-1,color,1,lineType=cv2.LINE_AA)
    # enlarge first, then draw label at measured region centroid
    dw,dh=round(w*scale),round(h*scale)
    pic=Image.fromarray(tint).resize((dw,dh),Image.Resampling.NEAREST)
    canvas=Image.new('RGB',(dw+340,dh+76),'#f7f9fc');canvas.paste(pic,(18,51))
    d=ImageDraw.Draw(canvas)
    d.text((18,13),'Float instance segmentation v3 | observed regions',font=font(23,True),fill='#111827')
    f=font(14,True)
    for c in instances:
        x=18+int(round(c['label_x']*scale));y=51+int(round(c['label_y']*scale))
        col='#d97706' if c['quality']=='review' else '#2563eb'
        rad=10
        d.ellipse((x-rad,y-rad,x+rad,y+rad),fill='white',outline=col,width=3)
        box=d.textbbox((0,0),'1',font=f)
        d.text((x-(box[2]-box[0])/2,y-(box[3]-box[1])/2-1),'1',font=f,fill=col)
    x=dw+47;y=65
    info=[('Photo observations',20,True),('1 : segmented bright float',15,False),('? : dark/background unresolved',15,False),('Cyan : independent float contour',14,False),('Yellow : review recommended',14,False),('',10,False),(f'Unique float candidates: {len(instances)}',17,True),(f'Review flags: {sum(c["quality"]=="review" for c in instances)}',17,True),('No synthetic crossing grid',15,False),('No physical 0 claimed',15,False)]
    for s,sz,b in info:
        d.text((x,y),s,font=font(sz,b),fill='#182336');y+=37
    canvas.save(path,optimize=True)

def save_compare(rgb,old_core,new_map,filename):
    arr=np.asarray(rgb.convert('RGB'));h,w=arr.shape[:2]
    frames=[]
    for mask,color in [(old_core>0,(255,180,0)),(new_map>0,(0,238,238))]:
        over=arr.copy().astype(float)
        over[mask]=over[mask]*.65+np.array(color)*.35
        over=np.uint8(over)
        outlines,_=cv2.findContours(np.uint8(mask),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(over,outlines,-1,color,1)
        frames.append(Image.fromarray(over).resize((w,h),Image.Resampling.NEAREST))
    canv=Image.new('RGB',(w*2+20,h+55),'#f7f9fc');canv.paste(frames[0],(0,55));canv.paste(frames[1],(w+20,55))
    d=ImageDraw.Draw(canv);d.text((15,12),'Before: bright core mask',font=font(21,True),fill='#111827')
    d.text((w+35,12),'After: seeded exclusive watershed',font=font(21,True),fill='#111827')
    canv.save(filename,optimize=True)

def run_photo(p,out):
    out.mkdir(parents=True,exist_ok=True)
    rgb=Image.open(p).convert('RGB')
    img=np.asarray(rgb);gray=cv2.cvtColor(img,cv2.COLOR_RGB2GRAY)
    _,old_core,_,_,_=_prelim_shape(gray)
    labels,items,summary=segment_photo(rgb)
    name=p.stem
    draw_mask_and_labels(rgb,labels,items,out/(name+'_v3_1_centers.png'))
    save_compare(rgb,old_core,labels,out/(name+'_before_after.png'))
    mask=np.uint8(labels>0)*255
    cv2.imwrite(str(out/(name+'_float_mask.png')),mask)
    # Save individual instance-ID pixels losslessly for algorithmic downstream use
    Image.fromarray(labels.astype(np.uint16)).save(out/(name+'_instance_ids.png'))
    keys=['id','center_x','center_y','label_x','label_y','seed_x','seed_y','bbox_x','bbox_y','bbox_w','bbox_h','area_px','mean_gray','quality','review_reasons']
    with (out/(name+'_floats.csv')).open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=keys);writer.writeheader();writer.writerows([{k:c[k] for k in keys} for c in items])
    with (out/(name+'_polygons.json')).open('w',encoding='utf-8') as f:
        json.dump(items,f,ensure_ascii=False,indent=1)
    summary['image']=p.name
    with (out/(name+'_report.json')).open('w',encoding='utf-8') as f:
        json.dump(summary,f,ensure_ascii=False,indent=2)
    print(name,summary['float_candidate_count'],summary['review_count'],summary['old_core_foreground_coverage_pct'],summary['expanded_foreground_coverage_pct'],summary['bright_pixel_coverage_pct'],flush=True)
    return summary

def main():
    ap=argparse.ArgumentParser()
    mode=ap.add_mutually_exclusive_group(required=True)
    mode.add_argument('--image',type=Path)
    mode.add_argument('--batch',type=Path)
    ap.add_argument('--out',type=Path,default=Path('v3_output'))
    ap.add_argument('--self-check',action='store_true')
    args=ap.parse_args()
    photos=[args.image] if args.image else sorted(x for x in args.batch.iterdir() if x.suffix.lower() in ('.png','.jpg','.jpeg'))
    if not photos:raise SystemExit('no input images')
    summary=[]
    for p in photos:
        r=run_photo(p,args.out/p.stem)
        summary.append(r)
    keys=['image','preliminary_core_count','float_candidate_count','review_count','seed_min_separation_px','old_core_foreground_coverage_pct','expanded_foreground_coverage_pct','bright_pixel_coverage_pct','physical_weave_matrix','dark_label_0_count']
    with (args.out/'batch_summary.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=keys);writer.writeheader();writer.writerows([{k:x[k] for k in keys} for x in summary])
    if args.self_check:
        rgb=Image.open(photos[0]).convert('RGB')
        map1,items1,_=segment_photo(rgb)
        map2,items2,_=segment_photo(rgb)
        assert np.array_equal(map1,map2),'non-deterministic label image'
        assert len(items1)==len(items2),'non-deterministic count'
        assert len({i['id'] for i in items1})==len(items1),'duplicate IDs'
        for c in items1:assert map1[c['label_y'],c['label_x']]==c['tag'],'label center not inside own float'
        print('PASS deterministic rerun, unique IDs and valid mask centers')
if __name__=='__main__':main()
