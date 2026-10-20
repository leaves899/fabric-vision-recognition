from __future__ import annotations
"""Native 8000x6000 procedural capture simulator. NOT real camera photographs.

Physical yarn IDs, widths, continuous (possibly occluded) center curves and an
explicit over/under relation exist BEFORE pixels are rendered. Truth JSON is
never supplied to a measurement function. Rendering uses bounded-height strips
into on-disk uint8 arrays; full-resolution files are never upscaled thumbnails.
"""
import argparse
import hashlib
import json
import math
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
import cv2
import numpy as np

@dataclass(frozen=True)
class CaptureScene:
    name: str = "native8k_plain_30_25"
    width: int = 8000
    height: int = 6000
    mm_per_px: float = 0.0125
    warp_density_cm: float = 30.0
    weft_density_cm: float = 25.0
    weave: str = "plain"
    rotation_deg: float = 7.0
    fabric_rotation_deg: float = 0.0  # independent of fixture/camera rotation
    perspective: float = 0.002
    wave_fraction: float = 0.035
    contrast_polarity: str = "dark"
    diagonal_decoy: float = 9.0
    noise_sigma: float = 3.0
    shift_reflection_x: float = 0.8
    seed: int = 802601

def hash_file(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for chunk in iter(lambda:f.read(1048576),b""):
            h.update(chunk)
    return h.hexdigest()

def _warp_up(wi, fi, weave):
    if weave == "plain": return (wi+fi)%2==0
    if weave == "twill_2_1": return (wi-fi)%3!=0
    if weave == "twill_3_1": return (wi-fi)%4!=0
    if weave == "satin_5_2": return (wi-2*fi)%5==0
    raise ValueError("UNKNOWN_WEAVE")

def camera_matrices(s):
    w,h=s.width,s.height
    source=np.float32([[0,0],[w,0],[w,h],[0,h]])
    a=np.deg2rad(s.rotation_deg)
    cx,cy=w/2,h/2
    xy=source-np.float32([cx,cy])
    rot=np.float32([[np.cos(a),-np.sin(a)],[np.sin(a),np.cos(a)]])
    target=xy@rot.T+np.float32([cx,cy])
    p=s.perspective
    target+=np.float32([[-p*w,p*h],[p*w,p*h],[p*w,-p*h],[-p*w,-p*h]])
    H=cv2.getPerspectiveTransform(source,target.astype(np.float32))
    return H, np.linalg.inv(H)

def _curve_shift(value,index,pitch,fraction,period):
    return fraction*pitch*(np.sin(2*np.pi*value/period+index*.61)+.25*np.sin(2*np.pi*value/(period*.57)+index*.37))

def _stripe_features(xbase,ybase,s):
    # Relative cloth/fiducial rotation; frame remains in camera canonical plane.
    if s.fabric_rotation_deg:
        alpha=np.deg2rad(s.fabric_rotation_deg)
        xx=xbase-s.width*.5;yy=ybase-s.height*.5
        xbase=s.width*.5+np.cos(alpha)*xx+np.sin(alpha)*yy
        ybase=s.height*.5-np.sin(alpha)*xx+np.cos(alpha)*yy
    wp=10.0/(s.warp_density_cm*s.mm_per_px)
    fp=10.0/(s.weft_density_cm*s.mm_per_px)
    # Fixed-point iterations preserve persistent yarn ID despite sinusoidal curvature.
    wi=np.rint((xbase-s.width*.5)/wp).astype(np.int32)
    fi=np.rint((ybase-s.height*.5)/fp).astype(np.int32)
    wx=s.width*.5+wi*wp+_curve_shift(ybase,wi,wp,s.wave_fraction,410.0)
    fy=s.height*.5+fi*fp+_curve_shift(xbase,fi,fp,s.wave_fraction,520.0)
    wi=np.rint((xbase-s.width*.5-_curve_shift(ybase,wi,wp,s.wave_fraction,410.0))/wp).astype(np.int32)
    fi=np.rint((ybase-s.height*.5-_curve_shift(xbase,fi,fp,s.wave_fraction,520.0))/fp).astype(np.int32)
    wx=s.width*.5+wi*wp+_curve_shift(ybase,wi,wp,s.wave_fraction,410.0)
    fy=s.height*.5+fi*fp+_curve_shift(xbase,fi,fp,s.wave_fraction,520.0)
    # Physical width is not pitch; ID variation plus smooth longitudinal variation.
    ww=wp*(.62+.045*np.sin(wi*1.79)+.02*np.sin(ybase/130+wi))
    fw=fp*(.61+.047*np.sin(fi*1.53)+.022*np.sin(xbase/150+fi))
    wc=np.exp(-.5*np.power(np.abs((xbase-wx)/np.maximum(ww*.48,1)),4)).astype(np.float32)
    fc=np.exp(-.5*np.power(np.abs((ybase-fy)/np.maximum(fw*.48,1)),4)).astype(np.float32)
    return wp,fp,wi,fi,ww,fw,wc,fc

def _render_strip(s, y0, y1, inverse, rng):
    yy,xx=np.mgrid[y0:y1,0:s.width].astype(np.float32)
    X=inverse[0,0]*xx+inverse[0,1]*yy+inverse[0,2]
    Y=inverse[1,0]*xx+inverse[1,1]*yy+inverse[1,2]
    D=inverse[2,0]*xx+inverse[2,1]*yy+inverse[2,2]
    X/=D;Y/=D
    wp,fp,wi,fi,ww,fw,wc,fc=_stripe_features(X,Y,s)
    top=_warp_up(wi,fi,s.weave)
    cross=(wc>.20)&(fc>.20)
    front_w=np.where(cross & ~top,wc*.20,wc)
    front_f=np.where(cross & top,fc*.20,fc)
    # Surface yarns painted on top, but transmissive opacity combines both fibers.
    reflect=38.+119.*front_w+82.*front_f
    reflect+=np.where(cross & top,48.*wc,0.)
    reflect+=np.where(cross & ~top,37.*fc,0.)
    light=1.+.11*np.sin(2*np.pi*Y/s.height)+.05*(X/s.width-.5)
    decoy=s.diagonal_decoy*np.sin(2*np.pi*(.79*X+.62*Y)/63.)
    reflect=reflect*light+decoy
    absorb=np.clip(.52*wc+.55*fc+.10*cross,0,.91)
    transmission=210.*(1.-absorb)+9.*(1.-wc)*(1.-fc)
    if s.contrast_polarity=="bright":
        transmission=255.-transmission
    elif s.contrast_polarity=="mixed":
        transmission=128.+(transmission-128)*np.sin(X/s.width*np.pi*1.5+.4)
    elif s.contrast_polarity!="dark":
        raise ValueError("UNKNOWN_POLARITY")
    transmission=transmission*light+.16*decoy
    reflect+=rng.normal(0,s.noise_sigma,size=reflect.shape).astype(np.float32)
    transmission+=rng.normal(0,s.noise_sigma,size=transmission.shape).astype(np.float32)
    outside=(X<120)|(X>s.width-120)|(Y<90)|(Y>s.height-90)
    reflect=np.where(outside,62.,reflect)
    transmission=np.where(outside,80.,transmission)
    # Real-world 50x50mm frame, defined in ORIGINAL unwarped physical plane.
    bw=50./s.mm_per_px
    cx=s.width*.5;cy=s.height*.5
    x0,x1=cx-bw*.5,cx+bw*.5
    fy0,fy1=cy-bw*.5,cy+bw*.5
    wall=17.0
    outside_inner=(X<x0)|(X>x1)|(Y<fy0)|(Y>fy1)
    inside_outer=(X>=x0-wall)&(X<=x1+wall)&(Y>=fy0-wall)&(Y<=fy1+wall)
    frame=outside_inner & inside_outer
    reflect=np.where(frame,220.,reflect)
    transmission=np.where(frame,28.,transmission)
    r=np.clip(reflect,0,255).astype(np.uint8)
    t=np.clip(transmission,0,255).astype(np.uint8)
    # Channel offsets simulate different yarn spectral properties, no full RGB floats.
    rgb_r=np.stack([r,np.clip(r.astype(np.int16)+7,0,255).astype(np.uint8),r],axis=2)
    rgb_t=np.stack([t,t,np.clip(t.astype(np.int16)-4,0,255).astype(np.uint8)],axis=2)
    if s.shift_reflection_x:
        m=np.float32([[1,0,s.shift_reflection_x],[0,1,0]])
        rgb_r=cv2.warpAffine(rgb_r,m,(s.width,y1-y0),borderMode=cv2.BORDER_REFLECT101)
    return rgb_r,rgb_t

def _truth_lines(s,H):
    wp=10/(s.warp_density_cm*s.mm_per_px)
    fp=10/(s.weft_density_cm*s.mm_per_px)
    result={"warp":[],"weft":[]}
    for family,pitch in (("warp",wp),("weft",fp)):
        n=int(np.ceil(max(s.width,s.height)/pitch))+4
        for idx in range(-n,n+1):
            if family=="warp":
                ys=np.linspace(0,s.height,81)
                xs=s.width*.5+idx*pitch+_curve_shift(ys,idx,pitch,s.wave_fraction,410.)
            else:
                xs=np.linspace(0,s.width,101)
                ys=s.height*.5+idx*pitch+_curve_shift(xs,idx,pitch,s.wave_fraction,520.)
            if family=="warp" and (np.min(xs)>s.width+pitch or np.max(xs)<-pitch):continue
            if family=="weft" and (np.min(ys)>s.height+pitch or np.max(ys)<-pitch):continue
            if s.fabric_rotation_deg:
                angle=np.deg2rad(s.fabric_rotation_deg)
                dx=xs-s.width*.5;dy=ys-s.height*.5
                xs=s.width*.5+np.cos(angle)*dx-np.sin(angle)*dy
                ys=s.height*.5+np.sin(angle)*dx+np.cos(angle)*dy
            pts=np.stack([xs,ys],axis=1).astype(np.float32)
            im=cv2.perspectiveTransform(pts[None],H)[0]
            result[family].append({"id":family[0]+str(idx),"points":np.round(im,2).tolist(),
                 "nominal_width_px":round(float(pitch*(.62 if family=="warp" else .61)),3)})
    return result

def generate(scene:CaptureScene, out:Path, strip_rows:int=96):
    if scene.width!=8000 or scene.height!=6000:
        raise ValueError("NATIVE_8K_SMOKE_MUST_USE_8000x6000")
    if strip_rows<16 or strip_rows>512:raise ValueError("BAD_STRIP")
    out.mkdir(parents=True,exist_ok=True)
    t0=time.perf_counter()
    H,Hinv=camera_matrices(scene)
    R=np.memmap(str(out/"_reflection.uint8"),dtype=np.uint8,mode="w+",shape=(scene.height,scene.width,3))
    T=np.memmap(str(out/"_transmission.uint8"),dtype=np.uint8,mode="w+",shape=(scene.height,scene.width,3))
    rng=np.random.default_rng(scene.seed)
    for y in range(0,scene.height,strip_rows):
        y1=min(y+strip_rows,scene.height)
        halo=4
        ry0=max(0,y-halo);ry1=min(scene.height,y1+halo)
        a,b=_render_strip(scene,ry0,ry1,Hinv,rng)
        a=cv2.GaussianBlur(a,(5,5),sigmaX=.75,sigmaY=.75)
        b=cv2.GaussianBlur(b,(5,5),sigmaX=.75,sigmaY=.75)
        R[y:y1]=a[y-ry0:y1-ry0]
        T[y:y1]=b[y-ry0:y1-ry0]
    R.flush();T.flush()
    # No resizing: JPEG encoder sees the native original 8000x6000 arrays.
    rpath=out/"reflection_8000x6000.jpg";tpath=out/"transmission_8000x6000.jpg"
    assert cv2.imwrite(str(rpath),R,[cv2.IMWRITE_JPEG_QUALITY,88])
    assert cv2.imwrite(str(tpath),T,[cv2.IMWRITE_JPEG_QUALITY,88])
    del R,T
    os.unlink(out/"_reflection.uint8");os.unlink(out/"_transmission.uint8")
    fcx,fcy=scene.width/2,scene.height/2
    q=50/scene.mm_per_px/2
    corners=np.float32([[[fcx-q,fcy-q],[fcx+q,fcy-q],[fcx+q,fcy+q],[fcx-q,fcy+q]]])
    mapped=cv2.perspectiveTransform(corners,H)[0]
    # Directly sample the generated per-ID width model (independent of pitch gate).
    width_p10={}
    for family,density in (("warp",scene.warp_density_cm),("weft",scene.weft_density_cm)):
        pitch=10/(density*scene.mm_per_px)
        ids=np.arange(-160,161,dtype=np.float64)[:,None]
        positions=np.linspace(500,scene.height-500,50)[None,:]
        if family=="warp":
            widths=pitch*(.62+.045*np.sin(ids*1.79)+.02*np.sin(positions/130+ids))
        else:
            positions=np.linspace(500,scene.width-500,50)[None,:]
            widths=pitch*(.61+.047*np.sin(ids*1.53)+.022*np.sin(positions/150+ids))
        width_p10[family]=round(float(np.percentile(widths,10)),3)
    gt={
        "physical_width_p10_px":width_p10,
        "passes_capture_p10_gate":all(value>=12 for value in width_p10.values()),
        "generator":"native8k_physical_fabric_v1","synthetic":True,
        "real_capture_certified":False,"source_scene":asdict(scene),
        "true_weave":scene.weave,"weave_label_not_for_inference":True,
        "true_density_per_cm":{"warp":scene.warp_density_cm,"weft":scene.weft_density_cm},
        "true_pitch_px_canonical":{"warp":10/(scene.warp_density_cm*scene.mm_per_px),"weft":10/(scene.weft_density_cm*scene.mm_per_px)},
        "physical_yarn_centerlines":_truth_lines(scene,H),
        "camera_geometry":{"canonical_to_raw_homography":H.tolist(),
           "raw_to_canonical_homography":Hinv.tolist(),
           "calibration_frame_inside_mm":[50.,50.],
           "frame_corners_raw_px":mapped.tolist(),
           "frame_corners_canonical_px":corners[0].tolist(),
           "rectified_mm_per_px":scene.mm_per_px,
           "true_rectification_area_canonical_px":[float(fcx-q),float(fcy-q),float(fcx+q),float(fcy+q)]},
        "files":{"reflection":rpath.name,"transmission":tpath.name},
        "sha256":{"reflection":hash_file(rpath),"transmission":hash_file(tpath)},
        "runtime_seconds":round(time.perf_counter()-t0,3),
    }
    (out/"truth.json").write_text(json.dumps(gt,ensure_ascii=False,indent=2),encoding="utf-8")
    # Preview is derived from the native rendered image after full-resolution saving.
    raw=cv2.imread(str(tpath),cv2.IMREAD_COLOR)
    assert raw.shape[:2]==(6000,8000)
    preview=cv2.resize(raw,(1200,900),interpolation=cv2.INTER_AREA)
    cv2.imwrite(str(out/"transmission_preview.jpg"),preview)
    cv2.imwrite(str(out/"native_center_crop.jpg"),raw[2700:3300,3700:4300])
    return gt

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--out",default="experiments/shibie-8k-capture-multiwindow/smoke")
    p.add_argument("--weave",default="plain",choices=["plain","twill_2_1","twill_3_1","satin_5_2"])
    p.add_argument("--warp-density",type=float,default=30.)
    p.add_argument("--weft-density",type=float,default=25.)
    p.add_argument("--polarity",default="dark",choices=["dark","bright","mixed"])
    p.add_argument("--rotation",type=float,default=7.)
    p.add_argument("--perspective",type=float,default=.002)
    p.add_argument("--seed",type=int,default=802601)
    a=p.parse_args()
    s=CaptureScene(warp_density_cm=a.warp_density,weft_density_cm=a.weft_density,
                   weave=a.weave,contrast_polarity=a.polarity,
                   rotation_deg=a.rotation,perspective=a.perspective,seed=a.seed)
    print(json.dumps({"native_shape":[s.height,s.width],"weave":s.weave,
        "pitch":[800/s.warp_density_cm,800/s.weft_density_cm]},ensure_ascii=False),flush=True)
    x=generate(s,Path(a.out))
    print(json.dumps({"runtime_seconds":x["runtime_seconds"],"files":x["sha256"],
      "physical_yarns":{k:len(v) for k,v in x["physical_yarn_centerlines"].items()}},ensure_ascii=False),flush=True)
if __name__=="__main__":main()
