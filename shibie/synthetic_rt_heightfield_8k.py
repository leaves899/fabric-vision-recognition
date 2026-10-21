from __future__ import annotations
"""Native-coordinate 2.5D RT renderer. Approximation, not measured camera physics.

Closed elliptical fibre bundles, continuous crimp along each persistent yarn,
z-buffer visibility, diffuse/specular illumination and short-range height shadow.
Transmission uses chord optical depth and symmetric diffuse lateral scattering.
No image texture pasting, polarity inversion, weave label in detector, or R->T.
"""
import argparse,json,os,time,resource
from dataclasses import dataclass,asdict
from pathlib import Path
import cv2
import numpy as np
from synthetic_capture_8k import CaptureScene,_curve_shift,_warp_up,_truth_lines,hash_file

@dataclass(frozen=True)
class Optics:
    light_direction: tuple = (-.38,-.45,.81)
    warp_albedo_bgr: tuple = (.10,.065,.045)
    weft_albedo_bgr: tuple = (.67,.70,.70)
    ambient: float = .30
    diffuse: float = .68
    specular: float = .025
    absorption_per_px: float = .18
    scattering_fraction: float = .16
    psf_sigma_px: float = .68
    noise_sigma: float = .9
    backlight: float = .88
    exposure: float = 1.05
    fibre_strength: float = .12
    twist_pitch_px: float = 95.


def validate(s):
    if (s.rotation_deg,s.fabric_rotation_deg,s.perspective)!=(0,0,0):
        raise ValueError('ONLY_ZERO_STATION_GEOMETRY_SUPPORTED')
    if s.shift_reflection_x!=0 or s.contrast_polarity!='dark' or s.diagonal_decoy!=0:
        raise ValueError('NO_SHIFT_POLARITY_INVERSION_OR_DECOY_ALLOWED')


def _smooth_random(along,index,seed,scale):
    u=along/scale;lo=np.floor(u);f=u-lo;f=f*f*(3-2*f)
    a=_coordinate_noise(lo,index,seed)*2
    b=_coordinate_noise(lo+1,index,seed)*2
    return a*(1-f)+b*f


def yarn_fields(s,family,index,along):
    warp=family=='warp';pitch=10/(s.mm_per_px*(s.warp_density_cm if warp else s.weft_density_cm))
    center=(s.width/2 if warp else s.height/2)+index*pitch+_curve_shift(along,index,pitch,s.wave_fraction,410 if warp else 520)
    center+=.028*pitch*_smooth_random(along,index,s.seed+13,85)
    width=pitch*((.62 if warp else .61)+(.045*np.sin(index*1.79)+.02*np.sin(along/130+index) if warp else .047*np.sin(index*1.53)+.022*np.sin(along/150+index)))
    width*=1+.12*_smooth_random(along,index,s.seed+83,49)+.045*_smooth_random(along,index,s.seed+88,13)
    return center,width


def geometry(s,x,y):
    """One analytic source of centres, widths, crimp, chord and visibility."""
    wp=10/(s.warp_density_cm*s.mm_per_px);fp=10/(s.weft_density_cm*s.mm_per_px)
    wi=np.rint((x-s.width/2)/wp).astype(np.int32)
    fi=np.rint((y-s.height/2)/fp).astype(np.int32)
    for _ in range(3):
        wx,ww=yarn_fields(s,'warp',wi,y);fy,fw=yarn_fields(s,'weft',fi,x)
        wi=np.rint((x-(wx-wi*wp))/wp).astype(np.int32)
        fi=np.rint((y-(fy-fi*fp))/fp).astype(np.int32)
    wx,ww=yarn_fields(s,'warp',wi,y);fy,fw=yarn_fields(s,'weft',fi,x)
    u=(x-wx)/(ww/2);v=(y-fy)/(fw/2)
    ew=np.sqrt(np.maximum(0,1-u*u));ef=np.sqrt(np.maximum(0,1-v*v))
    # Cubic smoothstep between actual adjacent crossing centres. A 3/1 run
    # stays above three crossings; only dives around the single weft-up crossing.
    yd=(y-fy)/fp;xd=(x-wx)/wp
    j=fi+np.where(yd<0,-1,0);i=wi+np.where(xd<0,-1,0)
    ty=np.where(yd<0,yd+1,yd);tx=np.where(xd<0,xd+1,xd)
    sy=np.clip(ty,0,1);sy=sy*sy*(3-2*sy)
    sx=np.clip(tx,0,1);sx=sx*sx*(3-2*sx)
    up0=_warp_up(wi,j,s.weave).astype(np.float32)*2-1
    up1=_warp_up(wi,j+1,s.weave).astype(np.float32)*2-1
    vf0=1-_warp_up(i,fi,s.weave).astype(np.float32)*2
    vf1=1-_warp_up(i+1,fi,s.weave).astype(np.float32)*2
    rz_w=ww*.22;rz_f=fw*.22
    separation=.60*(rz_w+rz_f)
    center_w=separation*(up0*(1-sy)+up1*sy)
    center_f=separation*(vf0*(1-sx)+vf1*sx)
    sign=np.where(_warp_up(wi,fi,s.weave),1.,-1.)
    # Unilateral contact: enforce non-interpenetrating elliptical volumes.
    required=rz_w*ew+rz_f*ef+1.0
    contact=np.maximum(0,required-sign*(center_w-center_f))*.5*((ew>0)&(ef>0))
    center_w+=sign*contact;center_f-=sign*contact
    zw=center_w+rz_w*ew;zf=center_f+rz_f*ef
    mw=np.abs(u)<1;mf=np.abs(v)<1
    zw=np.where(mw,zw,-100);zf=np.where(mf,zf,-100)
    visible=np.where(mw & ((zw>=zf)|~mf),1,np.where(mf,2,0)).astype(np.uint8)
    return dict(wi=wi,fi=fi,wx=wx,fy=fy,ww=ww,fw=fw,u=u,v=v,
        ew=ew,ef=ef,zw=zw,zf=zf,visible=visible,
        top=_warp_up(wi,fi,s.weave),volume_clearance=sign*(center_w-center_f)-rz_w*ew-rz_f*ef,warp_chord=2*rz_w*ew,weft_chord=2*rz_f*ef)


def _coordinate_noise(x,y,seed):
    # Integer coordinate hash: deterministic across strip heights and halos.
    with np.errstate(over='ignore'):
        q=x.astype(np.uint32)*np.uint32(374761393)+y.astype(np.uint32)*np.uint32(668265263)+np.uint32(seed)
        q=(q^(q>>13))*np.uint32(1274126177);q=q^(q>>16)
    return q.astype(np.float32)/np.float32(4294967295.)-.5


def render_region(s,o,x0,y0,width,height,diagnostic=False):
    validate(s)
    if width<4 or height<4:raise ValueError('REGION_TOO_SMALL')
    y,x=np.mgrid[y0:y0+height,x0:x0+width].astype(np.float32)
    g=geometry(s,x,y);vis=g['visible'];mw=vis==1;mf=vis==2
    # Z derivatives are taken on the selected yarn surface, not across the
    # depth jump at an occlusion boundary. No fictitious surface connects yarns.
    # Correlated small fibre bundles produce real surface slopes and highlights.
    seedphase=s.seed*.013
    phase_w=(x-g['wx'])*.52+y/o.twist_pitch_px+g['wi']*.173+.32*_smooth_random(y,g['wi'],s.seed+101,19)
    phase_f=(y-g['fy'])*.52+x/o.twist_pitch_px+g['fi']*.173+.32*_smooth_random(x,g['fi'],s.seed+102,19)
    rough_w=.21*np.sin(2*np.pi*phase_w)+.16*_smooth_random(y,(g['wi']*53+np.floor((x-g['wx'])*1.3)),s.seed+103,4)
    rough_f=.21*np.sin(2*np.pi*phase_f)+.16*_smooth_random(x,(g['fi']*53+np.floor((y-g['fy'])*1.3)),s.seed+104,4)
    g['zw']=g['zw']+rough_w*(g['ew']>0);g['zf']=g['zf']+rough_f*(g['ef']>0)
    dzwy,dzwx=np.gradient(g['zw']);dzfy,dzfx=np.gradient(g['zf'])
    nx=-np.where(mw,dzwx,dzfx);ny=-np.where(mw,dzwy,dzfy)
    norm=np.sqrt(1+nx*nx+ny*ny);nx/=norm;ny/=norm;nz=1/norm
    L=np.asarray(o.light_direction,np.float32);L/=np.linalg.norm(L)
    lambert=np.maximum(0,nx*L[0]+ny*L[1]+nz*L[2])
    z=np.maximum(g['zw'],g['zf']);shadow=np.zeros(z.shape,np.float32)
    # Four height samples towards the light; bounded local shadow approximation.
    for distance in (2,4,8,12):
        dx=int(round(L[0]/max(L[2],.2)*distance));dy=int(round(L[1]/max(L[2],.2)*distance))
        q=np.roll(z,(-dy,-dx),(0,1))
        shadow=np.maximum(shadow,np.clip((q-z-distance)/3,0,1))
    shade=o.ambient+o.diffuse*lambert*(1-.75*shadow)
    half=L+np.array([0,0,1],np.float32);half/=np.linalg.norm(half)
    spec=o.specular*np.maximum(0,nx*half[0]+ny*half[1]+nz*half[2])**24
    # Twisted fibre bundle pattern lives in each entity's own local coordinates.
    seedphase=s.seed*.013
    wf=np.sin(2*np.pi*phase_w)
    ff=np.sin(2*np.pi*phase_f)
    fibre=np.where(mw,wf,ff)
    yarnvar=np.where(mw,1+.10*np.sin(g['wi']*2.41+seedphase)+.035*np.sin(y/49+g['wi']),
                          1+.10*np.sin(g['fi']*2.13+seedphase)+.035*np.sin(x/49+g['fi']))
    grain=_coordinate_noise(x,y,s.seed)
    rho=np.where(mw[:,:,None],np.asarray(o.warp_albedo_bgr),np.asarray(o.weft_albedo_bgr)).astype(np.float32)
    rho*=((1+o.fibre_strength*fibre+.08*grain)*yarnvar)[:,:,None]
    R=(rho*shade[:,:,None]+spec[:,:,None])*o.exposure
    R[vis==0]=.008
    # Beer-Lambert: line-integrated fibre mass is invariant to layer order.
    # Crimp increases fibre volume per projected length. Lateral scattering
    # depends on actual fibre mass; it is not an invented weave-contrast term.
    cw=g['warp_chord']*np.sqrt(1+dzwy*dzwy)
    cf=g['weft_chord']*np.sqrt(1+dzfx*dzfx)
    tau=o.absorption_per_px*(cw*(1+.08*wf)+cf*(1+.08*ff))
    direct=np.exp(-tau)
    diffuse=cv2.GaussianBlur(direct,(0,0),1.6)
    T=o.backlight*((1-o.scattering_fraction)*direct+o.scattering_fraction*diffuse)
    illum=1-.07*((x-s.width/2)/(s.width/2))**2-.07*((y-s.height/2)/(s.height/2))**2
    R*=illum[:,:,None];T*=illum
    # Linear-light -> camera gamma, then sensor noise and optical PSF.
    R=np.clip(R,0,1)**(1/2.2)*255
    T=np.clip(T,0,1)**(1/2.2)*255
    R+=o.noise_sigma*grain[:,:,None]*3.464
    T+=o.noise_sigma*_coordinate_noise(x,y,s.seed+131)*3.464
    R=cv2.GaussianBlur(R.astype(np.float32),(0,0),o.psf_sigma_px)
    T=cv2.GaussianBlur(T.astype(np.float32),(0,0),o.psf_sigma_px)
    T=np.repeat(T[:,:,None],3,axis=2)
    half_frame=25/s.mm_per_px;wall=17
    dx=np.abs(x-s.width/2);dy=np.abs(y-s.height/2)
    frame=(dx<=half_frame+wall)&(dy<=half_frame+wall)&((dx>half_frame)|(dy>half_frame))
    R[frame]=235;T[frame]=24
    R=np.clip(R,0,255).astype(np.uint8);T=np.clip(T,0,255).astype(np.uint8)
    return (R,T,g) if diagnostic else (R,T)


def _dense_truth(s):
    lines=_truth_lines(s,np.eye(3))
    for family,rows in lines.items():
        pitch=10/(s.mm_per_px*(s.warp_density_cm if family=='warp' else s.weft_density_cm))
        for row in rows:
            idx=int(row['id'][1:]);along=np.arange(0,(s.height if family=='warp' else s.width)+1,2,dtype=np.float32)
            center,ww=yarn_fields(s,family,idx,along)
            pts=np.stack([center,along],1) if family=='warp' else np.stack([along,center],1)
            row['points']=np.round(pts,4).tolist();row['widths_px']=np.round(ww,4).tolist()
    return lines


def generate(s,out,o=Optics(),strip_rows=96):
    validate(s)
    if (s.width,s.height)!=(8000,6000):raise ValueError('NATIVE_8K_REQUIRED')
    out=Path(out);out.mkdir(parents=True,exist_ok=True);start=time.perf_counter()
    arrays=[np.memmap(out/f'_{q}.u8',dtype='uint8',mode='w+',shape=(6000,8000,3)) for q in ('R','T')]
    for y in range(0,6000,strip_rows):
        a=max(0,y-24);b=min(6000,y+strip_rows+24)
        R,T=render_region(s,o,0,a,8000,b-a)
        arrays[0][y:min(y+strip_rows,6000)]=R[y-a:min(y+strip_rows,6000)-a]
        arrays[1][y:min(y+strip_rows,6000)]=T[y-a:min(y+strip_rows,6000)-a]
    hashes={};files={}
    for q,arr in zip(('reflection','transmission'),arrays):
        arr.flush();p=out/f'{q}_8000x6000.jpg';assert cv2.imwrite(str(p),arr,[cv2.IMWRITE_JPEG_QUALITY,93])
        hashes[q]=hash_file(p);files[q]=p.name
        cv2.imwrite(str(out/f'{q}_preview.jpg'),cv2.resize(arr,(1200,900),interpolation=cv2.INTER_AREA))
        cv2.imwrite(str(out/f'{q}_native600.png'),arr[2700:3300,3700:4300])
    for a in arrays:del a
    for q in ('R','T'):os.unlink(out/f'_{q}.u8')
    lines=_dense_truth(s);q=25/s.mm_per_px
    truth={'generator':'heightfield_RT_v2','synthetic':True,'real_capture_certified':False,
        'source_scene':asdict(s),'optics':asdict(o),'true_weave':s.weave,
        'true_density_per_cm':{'warp':s.warp_density_cm,'weft':s.weft_density_cm},
        'true_pitch_px_canonical':{'warp':10/(s.warp_density_cm*s.mm_per_px),'weft':10/(s.weft_density_cm*s.mm_per_px)},
        'physical_yarn_centerlines':lines,'sha256':hashes,'files':files,
        'camera_geometry':{'canonical_to_raw_homography':np.eye(3).tolist(),'raw_to_canonical_homography':np.eye(3).tolist(),
            'calibration_frame_inside_mm':[50,50],'rectified_mm_per_px':s.mm_per_px,
            'frame_corners_raw_px':[[4000-q,3000-q],[4000+q,3000-q],[4000+q,3000+q],[4000-q,3000+q]],
            'true_rectification_area_canonical_px':[4000-q,3000-q,4000+q,3000+q]},
        'truth_coordinate_definition':'analytic geometry() shared by optical render and ID maps; points sampled every 2 px; widths use exact rendering formula',
        'runtime_seconds':round(time.perf_counter()-start,3),'peak_rss_mib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,
        'limitations':['single-scattering approximation','short-range height shadow','no true lens or fibre BRDF calibration','no individual hair geometry yet','no measured transmission reference']}
    (out/'truth.json').write_text(json.dumps(truth,separators=(',',':')))
    R,T,g=render_region(s,o,3700,2700,600,600,True)
    # Raw per-pixel geometry audit, distinct from inference inputs.
    np.savez_compressed(out/'geometry_native600.npz',**{k:g[k] for k in ('wi','fi','ww','fw','visible','top','zw','zf','warp_chord','weft_chord','volume_clearance')})
    overlay=R.copy()
    for family in ('warp','weft'):
        for row in lines[family]:
            pts=np.asarray(row['points'],np.float32)-[3700,2700]
            cv2.polylines(overlay,[np.rint(pts).astype(np.int32)],False,(0,200,255) if family=='warp' else (80,230,60),1)
    cv2.imwrite(str(out/'truth_center_overlay.png'),overlay)
    print(json.dumps({k:truth[k] for k in ('generator','sha256','runtime_seconds','peak_rss_mib')}),flush=True)
    return truth


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path);p.add_argument('--weave',default='plain');p.add_argument('--seed',type=int,default=38121);p.add_argument('--material',default='development');a=p.parse_args()
    s=CaptureScene(name=a.out.name,weave=a.weave,rotation_deg=0,perspective=0,shift_reflection_x=0,diagonal_decoy=0,seed=a.seed)
    o=Optics() if a.material=='development' else Optics(warp_albedo_bgr=(.22,.14,.09),weft_albedo_bgr=(.55,.58,.60),absorption_per_px=.23,twist_pitch_px=117,noise_sigma=1.3)
    generate(s,a.out,o)
if __name__=='__main__':main()
