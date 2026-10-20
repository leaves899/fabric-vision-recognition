from __future__ import annotations

"""Deterministic, *procedural* woven cloth R/T pairs for failure-mode research.

A yarn has one persistent physical ID and a continuously parameterized centre
curve even when hidden beneath the other family.  Intersections implement an
explicit over/under matrix, with a common geometric warp for both modalities.

This is a simplified graphics model, NOT a calibrated camera simulation, a
photorealistic fabric dataset, or a substitute for real Golden Dataset images.
Ground-truth metadata must NEVER be supplied to the shibie measurement engine.
"""

from dataclasses import dataclass, asdict
import json
import math
from pathlib import Path
import cv2
import numpy as np


@dataclass(frozen=True)
class Scene:
    name: str
    weave: str = "plain"
    size: int = 768
    warp_pitch_px: float = 22.0
    weft_pitch_px: float = 27.0
    rotation_deg: float = 0.0
    wave_px: float = 1.0
    center_jitter_px: float = 0.65
    sensor_noise: float = 3.0
    blur_sigma: float = 0.65
    contrast: float = 1.0
    diagonal_decoy: float = 0.0
    uneven_illumination: float = 0.15
    reflection_shift_px: float = 0.0
    mm_per_px: float = 0.0125
    seed: int = 421


SCENES = (
    Scene("plain_neutral", weave="plain", seed=51),
    Scene("plain_rotated", weave="plain", rotation_deg=21., seed=52),
    Scene("twill_2_1", weave="twill_2_1", warp_pitch_px=20., weft_pitch_px=31., diagonal_decoy=7., seed=53),
    Scene("twill_3_1_decoy", weave="twill_3_1", warp_pitch_px=19., weft_pitch_px=24., rotation_deg=-17., diagonal_decoy=18., seed=54),
    Scene("satin_5_2", weave="satin_5_2", warp_pitch_px=25., weft_pitch_px=26., contrast=.77, seed=55),
    Scene("plain_soft_low_contrast", weave="plain", warp_pitch_px=16.5, weft_pitch_px=19., blur_sigma=1.3, sensor_noise=8., contrast=.66, reflection_shift_px=1.6, seed=56),
)

# Seeds and nuisances are frozen before evaluating the optical phase candidate.
# These three images are held out from the six diagnostic scenarios above.
HOLDOUT_SCENES = (
    Scene("holdout_plain_33deg", weave="plain", warp_pitch_px=18.5,
          weft_pitch_px=29.0, rotation_deg=33., center_jitter_px=1.15,
          diagonal_decoy=8., sensor_noise=6., seed=7051),
    Scene("holdout_twill_3_1_soft", weave="twill_3_1", warp_pitch_px=22.,
          weft_pitch_px=28.5, rotation_deg=-11., wave_px=1.9, blur_sigma=1.25,
          diagonal_decoy=16., sensor_noise=7., seed=7052),
    Scene("holdout_satin_5_2", weave="satin_5_2", warp_pitch_px=21.,
          weft_pitch_px=30.5, rotation_deg=14., contrast=.7,
          uneven_illumination=.3, center_jitter_px=1.1, seed=7053),
)



def _is_warp_up(warp_id: int, weft_id: int, weave: str) -> bool:
    if weave == "plain":
        return (warp_id + weft_id) % 2 == 0
    if weave == "twill_2_1":
        return (warp_id - weft_id) % 3 != 0
    if weave == "twill_3_1":
        return (warp_id - weft_id) % 4 != 0
    if weave == "satin_5_2":
        return (warp_id - 2 * weft_id) % 5 == 0
    raise ValueError("unknown physical weave: " + weave)


def _positions(n: int, period: float, rng: np.random.Generator, jitter: float):
    kmax = int(math.ceil(n / period)) + 4
    ids = np.arange(-kmax, kmax + 1, dtype=int)
    positions = n * .5 + period * ids.astype(np.float64)
    positions += rng.normal(0, jitter, len(ids))
    return ids, positions


def _augment(img: np.ndarray, scene: Scene, rng: np.random.Generator, *, reflected: bool):
    h, w = img.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    v = scene.uneven_illumination * (
        .6 * (xx / max(w-1, 1) - .5) + .5 * np.cos(2*np.pi*(yy+.12*h)/h)
    )
    img = img.astype(np.float32) * (1 + v[:, :, None])
    if scene.diagonal_decoy:
        # Optical *surface* band, not a physically additional yarn.
        u = .84 * xx + .54 * yy
        bands = np.sin(2*np.pi*u/43.0)
        img += (scene.diagonal_decoy * bands)[:, :, None]
    if scene.blur_sigma:
        img = cv2.GaussianBlur(img, (0, 0), sigmaX=scene.blur_sigma, sigmaY=scene.blur_sigma)
    img += rng.normal(0, scene.sensor_noise, img.shape).astype(np.float32)
    return np.clip(img, 0, 255).astype(np.uint8)


def _rotate_image(image, deg):
    if not deg:
        return image.copy()
    h,w=image.shape[:2]
    matrix=cv2.getRotationMatrix2D((w/2.,h/2.),deg,1)
    return cv2.warpAffine(image,matrix,(w,h),flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT101)


def synthesize(scene: Scene):
    if scene.size < 480:
        raise ValueError("synthetic input below minimum shibie image size")
    rng=np.random.default_rng(scene.seed)
    n=scene.size
    yy,xx=np.mgrid[0:n,0:n].astype(np.float32)
    warp_ids, x_positions=_positions(n,scene.warp_pitch_px,rng,scene.center_jitter_px)
    weft_ids, y_positions=_positions(n,scene.weft_pitch_px,rng,scene.center_jitter_px)
    # Physical IDs persist throughout full scene, including at occluded crossings.
    warp_weight=np.zeros((n,n),np.float32)
    weft_weight=np.zeros((n,n),np.float32)
    warp_index=np.full((n,n),-1,np.int32)
    weft_index=np.full((n,n),-1,np.int32)
    warp_curves=[]
    weft_curves=[]
    x_curve_all=[]
    y_curve_all=[]
    for wid, base in zip(warp_ids,x_positions):
        curve=base+scene.wave_px*np.sin(2*np.pi*yy[:,0]/210 + wid*.77)
        delta=xx-curve[:,None]
        # Gaussian textile cross-section, radius ~70% of one physical pitch.
        coverage=np.exp(-.5*(delta/(scene.warp_pitch_px*.31))**4).astype(np.float32)
        update=coverage>warp_weight
        warp_weight=np.maximum(warp_weight,coverage)
        warp_index[update]=int(wid)
        warp_curves.append([[float(curve[k]),float(k)] for k in range(0,n,12)])
        x_curve_all.append(np.stack([curve,np.arange(n,dtype=np.float32)],axis=1))
    for wid,base in zip(weft_ids,y_positions):
        curve=base+scene.wave_px*np.sin(2*np.pi*xx[0,:]/240 + wid*.81)
        delta=yy-curve[None,:]
        coverage=np.exp(-.5*(delta/(scene.weft_pitch_px*.32))**4).astype(np.float32)
        update=coverage>weft_weight
        weft_weight=np.maximum(weft_weight,coverage)
        weft_index[update]=int(wid)
        weft_curves.append([[float(k),float(curve[k])] for k in range(0,n,12)])
        y_curve_all.append(np.stack([np.arange(n,dtype=np.float32),curve],axis=1))
    crossing=(warp_weight>.1)&(weft_weight>.1)
    # Fast exact analytical weave phase.
    if scene.weave=="plain":
        warp_up=(warp_index+weft_index)%2==0
    elif scene.weave=="twill_2_1":
        warp_up=(warp_index-weft_index)%3!=0
    elif scene.weave=="twill_3_1":
        warp_up=(warp_index-weft_index)%4!=0
    elif scene.weave=="satin_5_2":
        warp_up=(warp_index-2*weft_index)%5==0
    else:
        raise ValueError("invalid weave")
    # Pale warp yarn + cool dark weft yarn. Colors are BGR.
    reflected=np.full((n,n,3),(39,39,40),dtype=np.float32)
    warp_color=np.asarray([176,197,213],np.float32)
    weft_color=np.asarray([102,114,124],np.float32)
    warp_lobe=np.clip(warp_weight*(.90 + .10*np.cos(xx*.17)),0,1)
    weft_lobe=np.clip(weft_weight*(.90 + .10*np.cos(yy*.15)),0,1)
    # At intersection show *only the overlying yarn* plus a little adjacent halo.
    lower_warp=np.where(crossing&(~warp_up),warp_weight*.18,warp_weight)
    lower_weft=np.where(crossing&warp_up,weft_weight*.18,weft_weight)
    reflected=reflected*(1-lower_warp[:,:,None]*.92)+warp_color[None,None,:]*lower_warp[:,:,None]*.92
    reflected=reflected*(1-lower_weft[:,:,None]*.70)+weft_color[None,None,:]*lower_weft[:,:,None]*.70
    # Explicitly strengthen front-facing overpass after other yarn is painted.
    top_warp=(crossing&warp_up).astype(np.float32)*warp_weight
    top_weft=(crossing&(~warp_up)).astype(np.float32)*weft_weight
    reflected=reflected*(1-top_warp[:,:,None]*.88)+warp_color[None,None,:]*top_warp[:,:,None]*.88
    reflected=reflected*(1-top_weft[:,:,None]*.87)+weft_color[None,None,:]*top_weft[:,:,None]*.87

    # Transmission = optical absorption of both yarns; over/under affects shading,
    # not the physical center count. Unlike reflection it shows gaps sharply.
    union=1-(1-warp_weight)*(1-weft_weight)
    attenuation=np.clip(.58*warp_weight+.60*weft_weight+.12*crossing.astype(np.float32),0, .9)
    transmitted=np.full((n,n,3),(217,216,210),np.float32)
    transmitted *= (1-attenuation[:,:,None])
    transmitted += (4.*(1-union))[:,:,None]
    c=float(scene.contrast)
    reflected=128+(reflected-128)*c
    transmitted=128+(transmitted-128)*c
    reflected=_augment(reflected,scene,rng,reflected=True)
    transmitted=_augment(transmitted,scene,rng,reflected=False)

    if scene.reflection_shift_px:
        m=np.asarray([[1,0,scene.reflection_shift_px],[0,1,-scene.reflection_shift_px]],np.float32)
        reflected=cv2.warpAffine(reflected,m,(n,n),borderMode=cv2.BORDER_REFLECT101)
    reflected=_rotate_image(reflected,scene.rotation_deg)
    transmitted=_rotate_image(transmitted,scene.rotation_deg)

    m=cv2.getRotationMatrix2D((n/2.,n/2.),scene.rotation_deg,1.)
    def transform(curves,ids):
        out=[]
        for curve,ident in zip(curves,ids):
            points=cv2.transform(np.asarray(curve,dtype=np.float32)[None,:,:],m.astype(np.float32))[0]
            if np.all(points[:,0]<-.1*n) or np.all(points[:,0]>1.1*n) or np.all(points[:,1]<-.1*n) or np.all(points[:,1]>1.1*n):
                continue
            out.append({"id":int(ident),"points":np.round(points,3).tolist()})
        return out

    wgt=transform(x_curve_all,warp_ids)
    fgt=transform(y_curve_all,weft_ids)
    metadata={
      "generator":"synthetic_physical_fabric_v1",
      "scene":asdict(scene),
      "input_mode":"SYNTHETIC_PAIRED_REFLECTION_TRANSMISSION",
      "physical_scale_status":"EXACT_IN_SIMULATOR_ONLY",
      "physical_yarn_centerlines":{"warp":wgt,"weft":fgt},
      "periodicity_ground_truth_px":{"warp":scene.warp_pitch_px,"weft":scene.weft_pitch_px},
      "known_weave":"SYNTHETIC_LABEL_NOT_FOR_MODEL_INPUT",
      "true_weave":scene.weave,
      "true_direction_deg":{
          "warp":float((90.+scene.rotation_deg*-1)%180),
          "weft":float((-scene.rotation_deg)%180),
      },
      "photorealistic":False,
      "calibrated_50mp_captured":False,
    }
    return reflected,transmitted,metadata


if __name__=="__main__":
    out=Path("synthetic_examples")
    out.mkdir(exist_ok=True)
    for scene in SCENES:
        front,trans,meta=synthesize(scene)
        cv2.imwrite(str(out/(scene.name+"_R.png")),front)
        cv2.imwrite(str(out/(scene.name+"_T.png")),trans)
        (out/(scene.name+".json")).write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding="utf-8")
