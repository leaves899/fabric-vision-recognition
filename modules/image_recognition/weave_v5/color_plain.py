#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unsupervised two-chroma-family plain-weave candidate detector.

Measures image-supported color-family rows and their half-period displacement.
No fabric class/known labels or fixed 39-pixel periods are inputs. This does
not claim a physically verified over/under matrix.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont
from scipy.signal import find_peaks
from scipy.ndimage import gaussian_filter1d

try:
    FONT='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
    BOLD='/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
    CJK='/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
except Exception:
    FONT=BOLD=CJK=None

def font(n=16,bold=False):
    try:return ImageFont.truetype(BOLD if bold else FONT,n)
    except Exception:return ImageFont.load_default()

def estimate_x_repeat(gray, min_pitch=15, max_pitch=120):
    """Shortest strong local cross-correlation peak, not max doubled period."""
    a=gray[60:-60,40:-40].astype(float)
    a=a-a.mean(axis=1,keepdims=True)
    lim=min(max_pitch,a.shape[1]//3)
    lags=np.arange(min_pitch,lim+1)
    scores=np.array([float((a[:,:-lag]*a[:,lag:]).mean()) for lag in lags])
    ids,_=find_peaks(scores,prominence=max(.01,.12*float(np.max(scores))))
    if len(ids)==0:return None,[]
    peaks=sorted([(int(lags[i]),float(scores[i])) for i in ids], key=lambda a:a[0])
    strong=[a for a in peaks if a[1]>.52*max(v for _,v in peaks) and a[1]>0]
    return (strong[0][0] if strong else peaks[max(range(len(peaks)),key=lambda i:peaks[i][1])][0]),peaks

def circular_phase(xs,pitch):
    z=np.exp(2j*np.pi*np.asarray(xs)/pitch).mean()
    return float(np.angle(z)*pitch/(2*np.pi)%pitch),float(abs(z))

def circular_gap(a,b,pitch):
    return float(abs((a-b+pitch/2)%pitch-pitch/2))

def analyze(image_path, out=None, prefix=None):
    image_path=Path(image_path)
    rgb=np.asarray(Image.open(image_path).convert('RGB'))
    h,w=rgb.shape[:2]
    if h<400 or w<400:
        raise ValueError('minimum 400x400 ROI required')
    # normalize input ROI to 640x640 for sampling, but resampling metadata retained
    if (h,w)!=(640,640):
        rgb=cv2.resize(rgb,(640,640),interpolation=cv2.INTER_AREA)
    lab=cv2.cvtColor(rgb,cv2.COLOR_RGB2LAB).astype(np.float32)
    L=lab[:,:,0]
    bright=L>max(47.,float(np.percentile(L,35)))
    chrom=lab[bright][:,1:].astype(np.float32)[::5]
    if len(chrom)<100:
        return {'status':'insufficient_bright_pixels','organization_candidate':None}
    cv2.setRNGSeed(11)
    _,labels,centroids=cv2.kmeans(chrom,2,None,(cv2.TERM_CRITERIA_MAX_ITER+cv2.TERM_CRITERIA_EPS,55,.1),5,cv2.KMEANS_PP_CENTERS)
    order=np.argsort(centroids[:,0]);centroids=centroids[order]
    sep=float(np.linalg.norm(centroids[1]-centroids[0]))
    report={'detector':'unsupervised_chroma_plain','status':'unresolved','organization_candidate':None,
        'image':str(image_path),'resized_for_analysis':list(rgb.shape[:2]),
        'lab_ab_centroids':np.around(centroids,2).tolist(),'chroma_separation':round(sep,2),
        'physical_crossings_verified':False,'truth_used':False}
    if sep<12.:
        report['reason']='no_independent_second_chromatic_yarn_family'
        if out:
            p=Path(out);p.mkdir(parents=True,exist_ok=True)
            (p/'color_plain_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        return report
    direction=(centroids[1]-centroids[0])/sep
    mid=(centroids[1]+centroids[0])/2
    proj=np.sum((lab[:,:,1:]-mid)*direction[None,None,:],axis=2)
    scale=np.clip((L-35)/70,0,2.3)
    channels=[np.maximum(0,-proj)*scale,np.maximum(0,proj)*scale]
    pitch,all_lags=estimate_x_repeat(cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY))
    report['x_repeat_candidates_px']=all_lags
    if pitch is None:
        report['reason']='x_repeat_not_found'
        return report
    report['horizontal_repeat_px']=pitch
    family_rows=[];markers=[]
    for family,score in enumerate(channels):
        vertical=gaussian_filter1d(score[:,60:580].mean(axis=1),2)
        base=float(np.median(vertical)); peak=float(vertical.max())
        ypeaks,_=find_peaks(vertical,distance=19,prominence=max(.4,.15*(peak-base)))
        ypeaks=[int(y) for y in ypeaks if vertical[y]>max(.37*peak,base+.27*(peak-base)) and 22<y<620]
        for y in ypeaks:
            xresp=gaussian_filter1d(score[y-6:y+7,35:605].mean(axis=0),2)
            prom=max(.35,.16*float(np.percentile(xresp,90)-np.percentile(xresp,10)))
            xpk,_=find_peaks(xresp,distance=max(12,int(.66*pitch)),prominence=prom)
            xs=xpk+35
            xs=xs[(xs>45)&(xs<595)]
            if len(xs)<7:continue
            phase,coh=circular_phase(xs,pitch)
            if coh<.50:continue
            family_rows.append({'family':family,'y':y,'peak_strength':round(float(vertical[y]),2),
                'points':int(len(xs)),'phase_px':round(phase,2),'phase_coherence':round(coh,3)})
            markers.extend([{'family':family,'x':int(x),'y':y} for x in xs])
    report['observed_color_rows']=family_rows
    report['color_instance_peaks']=len(markers)
    groups=[[r for r in family_rows if r['family']==i] for i in (0,1)]
    report['rows_per_family']=[len(g) for g in groups]
    if min(len(g) for g in groups)<4:
        report['reason']='insufficient_confirmed_rows_in_two_color_families'
        if out:write(out, report, rgb,markers,prefix)
        return report
    row_periods=[float(np.median(np.diff([r['y'] for r in g]))) for g in groups]
    report['same_family_row_periods_px']=[round(v,2) for v in row_periods]
    family_phase=[];phase_cons=[]
    for group in groups:
        z=np.exp(2j*np.pi*np.array([r['phase_px'] for r in group])/pitch).mean()
        family_phase.append(float(np.angle(z)*pitch/(2*np.pi)%pitch));phase_cons.append(float(abs(z)))
    gap=circular_gap(family_phase[0],family_phase[1],pitch)
    phase_error=abs(gap/pitch-.5)
    r_sorted=sorted(family_rows,key=lambda d:d['y'])
    alt=float(np.mean([r_sorted[i]['family']!=r_sorted[i-1]['family'] for i in range(1,len(r_sorted))]))
    ydiff=np.diff([r['y'] for r in r_sorted]);period_ratio=abs(row_periods[0]-row_periods[1])/max(row_periods)
    midgap=float(np.median(ydiff)); expected=float(np.mean(row_periods)/2)
    ygap_error=abs(midgap/expected-1)
    report.update(color_families_phase_px=[round(x,2) for x in family_phase],
        phase_coherence=[round(x,3) for x in phase_cons],x_phase_gap_px=round(gap,2),
        half_pitch_deviation_fraction=round(phase_error,3),
        family_row_alternation_fraction=round(alt,3),
        same_family_period_relative_difference=round(period_ratio,3),
        adjacent_row_gap_px=round(midgap,2),row_gap_deviation=round(ygap_error,3))
    evidence_ok=(sep>=12 and gap/pitch>.31 and gap/pitch<.69 and alt>=.75
        and period_ratio<.18 and ygap_error<.28 and min(phase_cons)>.70)
    if evidence_ok:
        report['status']='plain_candidate_from_color_topology';report['organization_candidate']='plain_1_1'
    else:report['reason']='alternating_row_or_half_pitch_checks_not_passed'
    if out:write(out,report,rgb,markers,prefix)
    return report

def write(out,report,rgb,markers,prefix=None):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    (out/'color_plain_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    image=Image.fromarray(rgb);up=image.resize((960,960),Image.Resampling.NEAREST)
    overlay=up.copy();d=ImageDraw.Draw(overlay)
    for p in markers:
        x,y=p['x']*1.5,p['y']*1.5
        col='#35b7ef' if p['family']==0 else '#ffcf45'
        d.ellipse((x-5,y-5,x+5,y+5),outline='black',width=3)
        d.ellipse((x-5,y-5,x+5,y+5),outline=col,width=2)
    can=Image.new('RGB',(1970,1040),'#f5f6f9');can.paste(up,(10,60));can.paste(overlay,(990,60))
    dr=ImageDraw.Draw(can)
    dr.text((10,12),'ORIGINAL FABRIC | 640x640',font=font(23,True),fill='#111827')
    dr.text((990,12),'DETECTED COLOR FAMILY CENTERS (IMAGE EVIDENCE)',font=font(21,True),fill='#111827')
    dr.rectangle((10,1020,1940,1037),fill='#f5f6f9')
    can.save(out/'color_family_overlay.png',optimize=True)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--image',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    r=analyze(a.image,a.out)
    print(json.dumps({k:r.get(k) for k in ('status','organization_candidate','chroma_separation','horizontal_repeat_px','rows_per_family','x_phase_gap_px','family_row_alternation_fraction','half_pitch_deviation_fraction','reason')},ensure_ascii=False,indent=2))
