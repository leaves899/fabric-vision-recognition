"""Geometry-first exploratory textile evidence detector for multiple photos.

Important: Outputs are direction/ribbon/landmark HYPOTHESES, NOT ground truth yarns.
Images are analysed as grayscale ONLY; no RGB thresholds or color segmentation.
No image generation, training or external assets.
"""
from __future__ import annotations
import argparse, json, math
from pathlib import Path
import cv2
import numpy as np
from scipy.ndimage import gaussian_filter
from scipy.optimize import linear_sum_assignment

SCALES_FINE = ((0.65, 1.5, 0.75), (0.9, 2.1, 1.0), (1.3, 3.3, 0.8))
SCALES_COARSE = ((4.2, 11.0, 1.0), (7.5, 18.0, 0.7))


def angular_distance(a, b):
    return abs((float(a) - float(b) + 90) % 180 - 90)


def gray(im):
    if im.ndim==2: return im
    return cv2.cvtColor(im,cv2.COLOR_BGR2GRAY)


def tensor_votes(image, scales):
    g=gray(image).astype(np.float32)
    hist=np.zeros(180,np.float64)
    for s, integ, w in scales:
        z=cv2.GaussianBlur(g,(0,0),s)
        dx=cv2.Sobel(z,cv2.CV_32F,1,0,ksize=3)
        dy=cv2.Sobel(z,cv2.CV_32F,0,1,ksize=3)
        jxx=cv2.GaussianBlur(dx*dx,(0,0),integ)
        jxy=cv2.GaussianBlur(dx*dy,(0,0),integ)
        jyy=cv2.GaussianBlur(dy*dy,(0,0),integ)
        theta=(np.degrees(0.5*np.arctan2(2*jxy, jxx-jyy))+90)%180
        coh=np.hypot(jxx-jyy,2*jxy)/(jxx+jyy+1.e-6)
        weight=np.clip(coh,0,1)*np.sqrt(np.maximum(jxx+jyy,0)+1.e-5)*w
        m=max(14,int(image.shape[0]*.06))
        hist+=np.bincount(np.floor(theta[m:-m,m:-m]+.5).astype('int32').ravel()%180,
                          weights=weight[m:-m,m:-m].ravel(),minlength=180)
    return gaussian_filter(hist,2.5,mode='wrap')


def orientation_pair(image):
    fine=tensor_votes(image,SCALES_FINE)
    coarse=tensor_votes(image,SCALES_COARSE)
    found=[]
    for i in np.argsort(fine)[::-1]:
        if all(angular_distance(i,x)>=38 for x in found):found.append(int(i))
        if len(found)==2:break
    found.sort()
    distractor=int(np.argmax(coarse))
    support=[round(float(fine[x]/(np.max(fine)+1e-8)),4) for x in found]
    return found,distractor,support,fine,coarse


def ribbon_segments(im,theta,allow_colors=False):
    """Opposite Sobel edge pairs across a candidate axis, in grayscale only.
    Width hypotheses are *image-scale search values*, not measured yarn diameters.
    """
    g=gray(im).astype(np.float32)
    h,w=g.shape
    center=((w-1)/2,(h-1)/2)
    rot=cv2.getRotationMatrix2D(center,float(theta),1)
    inv=cv2.invertAffineTransform(rot)
    aligned=cv2.warpAffine(g,rot,(w,h),flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT_101)
    aligned=cv2.GaussianBlur(aligned,(0,0),1.7)
    dy=cv2.Sobel(aligned,cv2.CV_32F,0,1,ksize=3)
    response=np.zeros((h,w),np.float32)
    width=np.zeros((h,w),np.uint8)
    for half in (5,8,12,17,23):
        e1=np.roll(dy,half,axis=0);e2=np.roll(dy,-half,axis=0)
        z=np.where(e1*e2<0,np.minimum(np.abs(e1),np.abs(e2)),0)
        z[:half+2,:]=0;z[-half-2:,:]=0
        z=cv2.GaussianBlur(z,(0,0),sigmaX=7,sigmaY=1.0)
        hit=z>response
        response[hit]=z[hit];width[hit]=half
    vals=response[20:-20,20:-20];pos=vals[vals>0]
    if len(pos)<100:return []
    cutoff=np.percentile(pos,74)
    maxima=response >= cv2.dilate(response,np.ones((9,1),np.uint8))-1e-5
    detected=(maxima&(response>cutoff)).astype(np.uint8)
    detected[:25,:]=0;detected[-25:,:]=0
    detected[:,:20]=0;detected[:,-20:]=0
    detected=cv2.morphologyEx(detected,cv2.MORPH_CLOSE,np.ones((1,9),np.uint8))
    n,lab,stats,c=cv2.connectedComponentsWithStats(detected,8)
    segments=[]
    for i in range(1,n):
        x,y,bw,bh,area=stats[i]
        if bw<17 or bh>18 or area<13:continue
        sub=lab[y:y+bh,x:x+bw]==i
        yy,xx=np.where(sub); yy=yy+y;xx=xx+x
        weights=response[yy,xx]+1.e-5
        cy=float(np.average(yy,weights=weights))
        a=inv@np.array([float(x),cy,1]);b=inv@np.array([float(x+bw-1),cy,1])
        cp=inv@np.array([float(np.average(xx,weights=weights)),cy,1]);
        segments.append(dict(start=np.round(a,1).tolist(),end=np.round(b,1).tolist(),
                      center=np.round(cp,1).tolist(),length_px=int(bw),
                      width_hypothesis_px=round(float(2*np.median(width[yy,xx])),1),
                      boundary_score=round(float(np.median(weights)),2)))
    return segments


def landmark_candidates(im):
    """Local raised/texton center proposals from intensity extrema at two spatial scales.
    Brightness determines an initial *landmark*, never yarn type or identity.
    """
    g=gray(im).astype(np.float32)
    local=cv2.GaussianBlur(g,(0,0),6)
    surround=cv2.GaussianBlur(g,(0,0),19)
    response=local-surround
    maxima=cv2.dilate(response,np.ones((34,34),np.uint8))
    good=(response >= maxima-1e-4)&(response>np.percentile(response,72))
    good[:20,:]=False;good[-20:,:]=False;good[:,:20]=False;good[:,-20:]=False
    ys,xs=np.where(good)
    return [[int(x),int(y)] for x,y in zip(xs,ys)]


def link_hypotheses(segments, theta):
    """Conservative, non-verified segment links; reject close competing alternatives.
    No cross-image fixed 'true yarn pitch' is asserted.
    """
    n=len(segments)
    if n<2:return []
    pts=np.array([s['center'] for s in segments]);angle=math.radians(theta)
    u=np.array([math.cos(angle),math.sin(angle)]);v=np.array([-math.sin(angle),math.cos(angle)])
    long=pts@u;cross=pts@v
    length=np.array([s['length_px'] for s in segments],float)
    width=np.array([s['width_hypothesis_px'] for s in segments],float)
    gap=long[None,:]-long[:,None]-0.5*(length[:,None]+length[None,:])
    drift=np.abs(cross[None,:]-cross[:,None]);width_tol=np.minimum(11.,.23*(width[:,None]+width[None,:]))
    valid=(gap>3)&(gap<50)&(drift<width_tol)
    score=drift/(width_tol+1e-4)+gap/50+np.abs(width[:,None]-width[None,:])/25
    score[~valid]=1e4
    np.fill_diagonal(score,1e4)
    rows,cols=linear_sum_assignment(score)
    links=[]
    for i,j in zip(rows,cols):
        if score[i,j]>0.75:continue
        alternatives=min(np.min(np.delete(score[i],j)),np.min(np.delete(score[:,j],i))) if n>1 else 1e4
        if alternatives-score[i,j]<0.2:continue
        links.append({'from':int(i),'to':int(j),'score':round(float(score[i,j]),3),
                      'type':'unverified_geometry_hypothesis'})
    return links


def draw_overlay(img,pair,distractor,segments,landmarks,draw_links=False,links=None):
    out=img.copy()
    colors=((10,235,255),(40,230,40))
    for j,sl in enumerate(segments):
        for s in sl:
            a=tuple(int(round(t)) for t in s['start']);b=tuple(int(round(t)) for t in s['end'])
            cv2.line(out,a,b,colors[j],2,cv2.LINE_AA)
    for x,y in landmarks:
        cv2.circle(out,(x,y),3,(255,90,180),1,cv2.LINE_AA)
    if draw_links and links:
        for group in range(2):
            for link in links[group]:
                a=np.array(segments[group][link['from']]['center'])
                b=np.array(segments[group][link['to']]['center'])
                diff=b-a
                for t in np.arange(0,.95,.2):
                    s=a+t*diff;e=a+min(1,t+.09)*diff
                    cv2.line(out,tuple(np.int32(np.round(s))),tuple(np.int32(np.round(e))),colors[group],1,cv2.LINE_AA)
    cv2.rectangle(out,(0,0),(out.shape[1],45),(25,25,25),-1)
    cv2.putText(out,f'GRAY geometry: {pair[0]}/{pair[1]} deg  coarse {distractor} deg',
                (8,28),cv2.FONT_HERSHEY_SIMPLEX,.55,(255,255,255),1,cv2.LINE_AA)
    return out


def calculate_rotation_consistency(p,ref_angles,rotation):
    center=((p.shape[1]-1)/2,(p.shape[0]-1)/2)
    mat=cv2.getRotationMatrix2D(center,float(rotation),1)
    turned=cv2.warpAffine(p,mat,(p.shape[1],p.shape[0]),flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT_101)
    observed,*_=orientation_pair(turned)
    expect=[(a-rotation)%180 for a in ref_angles]
    e1=max(angular_distance(expect[0],observed[0]),angular_distance(expect[1],observed[1]))
    e2=max(angular_distance(expect[0],observed[1]),angular_distance(expect[1],observed[0]))
    return round(min(e1,e2),2)


def direction_dispersion(vals,origin):
    return [round(float(np.median([min(angular_distance(a, rr[0]),angular_distance(a,rr[1])) for rr in vals])),2) for a in origin]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--input',default=str(Path(__file__).parent/'inputs'))
    parser.add_argument('--output',default=str(Path(__file__).parent/'outputs'))
    args=parser.parse_args()
    inp=Path(args.input);dst=Path(args.output);dst.mkdir(parents=True,exist_ok=True)
    names=sorted(inp.glob('*.jpg'))
    records={};thumbs=[]
    for pth in names:
        img=cv2.imread(str(pth));h,w=img.shape[:2]
        cx,cy=w//2,h//2
        center=img[cy-256:cy+256,cx-256:cx+256]
        pair,coarse,support,_,_=orientation_pair(center)
        seg=[ribbon_segments(center,angle) for angle in pair]
        marks=landmark_candidates(center)
        links=[link_hypotheses(seg[j],pair[j]) for j in range(2)]
        overlay=draw_overlay(center,pair,coarse,seg,marks)
        links_img=draw_overlay(center,pair,coarse,seg,marks,True,links)
        cv2.imwrite(str(dst/f'{pth.stem}_center_geometry.jpg'),overlay,[cv2.IMWRITE_JPEG_QUALITY,95])
        cv2.imwrite(str(dst/f'{pth.stem}_center_tentative_links.jpg'),links_img,[cv2.IMWRITE_JPEG_QUALITY,94])
        # Place original and output side by side to allow physical ground truth review.
        side=cv2.hconcat([center,overlay])
        cv2.imwrite(str(dst/f'{pth.stem}_comparison.jpg'),side,[cv2.IMWRITE_JPEG_QUALITY,95])
        thumbs.append(cv2.resize(side,(820,410)))
        # Distributed region sampling; do not validate on center ROI only.
        local=[]
        for yy in (int(h*.17),int(h*.5),int(h*.83)):
            for xx in (int(w*.17),int(w*.5),int(w*.83)):
                win=img[max(0,yy-256):yy+256,max(0,xx-256):xx+256]
                if win.shape[:2]!=(512,512):continue
                aa,co,ss,_,_=orientation_pair(win)
                local.append({'center':[xx,yy],'directions':aa,'coarse':co,'relative_support':ss})
        # Transform invariance is necessary but not sufficient for physical correctness.
        rot={str(k):calculate_rotation_consistency(center,pair,k) for k in (30,45,90,180)}
        grayscale_rep=cv2.cvtColor(gray(center),cv2.COLOR_GRAY2BGR)
        g_angles,*_=orientation_pair(grayscale_rep)
        inversion=cv2.cvtColor(255-gray(center),cv2.COLOR_GRAY2BGR)
        i_angles,*_=orientation_pair(inversion)
        rec=dict(image_size=[w,h],fine_angle_candidates_deg=pair,
                 coarse_main_texture_angle_deg=coarse,
                 candidate_peak_support=support,
                 angular_separation_deg=round(angular_distance(*pair),2),
                 boundary_pair_segments=[len(s) for s in seg],
                 bright_texture_landmarks=len(marks),
                 tentative_links=[len(ls) for ls in links],
                 rotation_max_angle_disagreement_deg=rot,
                 gray_angles_deg=g_angles,gray_inversion_angles_deg=i_angles,
                 spatial_median_deviation_deg=direction_dispersion([v['directions'] for v in local],pair),
                 tiles=local,
                 validation_status='UNVERIFIED: angle candidates/ribbon segments/links are not physical yarn truth')
        records[pth.stem]=rec
        print(pth.stem,'fine',pair,'large-scale',coarse,'segments',rec['boundary_pair_segments'],'rot errors',rot,'MAD',rec['spatial_median_deviation_deg'],flush=True)
    # 5 image atlas (column 1 source image crop, column 2 algorithm overlay).
    if thumbs:
        for item in thumbs:
            cv2.rectangle(item,(0,0),(item.shape[1],35),(20,20,20),-1)
        atlas=cv2.vconcat(thumbs)
        cv2.imwrite(str(dst/'five_photo_comparison.jpg'),atlas,[cv2.IMWRITE_JPEG_QUALITY,91])
    (dst/'results.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__': main()