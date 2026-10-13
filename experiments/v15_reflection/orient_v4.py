"""V1.5 V4: spectrum/ACF candidates with native-resolution Hessian and tile checks.

FFT and inverse ACF share the same power spectrum, so agreement alone is not
independent evidence that an image period corresponds to a physical yarn.
This isolated experiment never upgrades a proposal to certified yarn truth.
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageFilter

from experiments.v15_reflection.orient_v3 import propose_axes as _propose_v3, axis_distance

VERSION = "v15-fft-acf-native-hessian-v4.0"


def _mean_axes(angles, weights=None):
    x = np.asarray(angles, float)
    w = np.ones(len(x), float) if weights is None else np.asarray(weights, float)
    z = np.sum(w*np.exp(4j*np.deg2rad(x)))
    return float(np.degrees(np.angle(z))/4 % 90) if abs(z)>1e-9 else None


def _hessian_orient(patch, sigma):
    blurred = np.asarray(patch.convert("L").filter(
        ImageFilter.GaussianBlur(float(sigma))), dtype=np.float32)
    gy,gx=np.gradient(blurred)
    yy,yx=np.gradient(gy)
    xy,xx=np.gradient(gx)
    xy=(xy+yx)/2
    half=(xx+yy)/2
    root=np.sqrt(((xx-yy)/2)**2+xy*xy)
    lower,upper=half-root,half+root
    normal=np.rad2deg(.5*np.arctan2(2*xy,xx-yy))
    normal=np.where(np.abs(lower)>np.abs(upper),normal+90,normal)
    tangent=(normal+90)%180
    # Discard crossings with mixed principal curvatures instead of treating
    # their diagonal composite gradient as a genuine yarn direction.
    weight=(np.maximum(np.abs(lower),np.abs(upper))-
            np.minimum(np.abs(lower),np.abs(upper)))**2
    bins=np.floor(tangent/2).astype(int)%90
    hist=np.bincount(bins.ravel(),weights=weight.ravel(),minlength=90)
    hist=(np.roll(hist,-1)+2*hist+np.roll(hist,1))/4.
    pair=np.sqrt(np.maximum(hist[:45]*hist[45:],0))
    idx=int(np.argmax(pair))
    ratio=float(pair[idx]/max(np.median(pair),1.e-6))
    return {"axis_deg":float(2*idx+1),"pair_strength":round(ratio,3)}


def native_evidence(image):
    """Sample true native pixels; do not infer fine yarn detail from 512px resize."""
    w,h=image.size
    s=min(640,w,h)
    if s<192:
        return {"native_hessian_consensus_deg":None,"native_hessian_strong":False,
                "native_patch_side_px":s,"reason":"INSUFFICIENT_NATIVE_RESOLUTION"}
    tile=image.crop(((w-s)//2,(h-s)//2,(w+s)//2,(h+s)//2))
    scales=[_hessian_orient(tile,sigma) for sigma in (.8,1.5,2.5)]
    selected=[v for v in scales if v["pair_strength"]>=1.28]
    angle=(_mean_axes([v["axis_deg"] for v in selected],
                       [v["pair_strength"] for v in selected])
           if len(selected)>=2 else None)
    dispersion=(max(axis_distance(v["axis_deg"],angle) for v in selected)
                if angle is not None else None)
    consistent=len(selected)>=2 and dispersion<=8.
    return {"native_hessian_scales":scales,
            "native_hessian_consensus_deg":round(angle,3) if angle is not None else None,
            "native_hessian_dispersion_deg":round(dispersion,3)
                if dispersion is not None else None,
            "native_hessian_strong":bool(consistent),
            "native_patch_side_px":s}


def _native_tile_proposals(image):
    """Require two widely spaced native neighborhoods to agree for recovery."""
    w,h=image.size
    side=min(512,w,h)
    if side<300 or min(w,h)<side*1.7:
        return []
    span_x,span_y=w-side,h-side
    # Symmetric 2x2 patches preserve the same physical quadrants under 90 degrees.
    positions=[(int(span_x*fx),int(span_y*fy))
               for fx,fy in ((.20,.20),(.80,.20),(.20,.80),(.80,.80))]
    answers=[]
    for x,y in positions:
        candidate=_propose_v3(image.crop((x,y,x+side,y+side)))
        answers.append({"angle_deg":(candidate.get("unlabelled_axes_deg") or [None])[0],
                        "reason":candidate.get("reason"),"status":candidate["status"]})
    return answers


def propose_axes(image):
    base=_propose_v3(image)
    local=native_evidence(image)
    out={**base,**local,"method":VERSION,
         "requires_manual_confirmation":base["status"]!="PROPOSED_NOT_VALIDATED"}
    theta=(base.get("unlabelled_axes_deg") or [None])[0]
    local_theta=local["native_hessian_consensus_deg"]
    if theta is not None and local["native_hessian_strong"]:
        delta=axis_distance(theta,local_theta)
        out["native_fft_acf_disagreement_deg"]=round(delta,3)
        if delta>12:
            out.update(status="ABSTAINED",reason="FFT_ACF_VS_NATIVE_CURVATURE_CONFLICT",
                       rejected_macro_candidate_deg=base["unlabelled_axes_deg"],
                       unlabelled_axes_deg=None,requires_manual_confirmation=True)
    elif theta is None and local["native_hessian_strong"]:
        tiles=_native_tile_proposals(image)
        out["native_patch_proposals"]=tiles
        supported=[t["angle_deg"] for t in tiles if t["angle_deg"] is not None]
        if len(tiles)==4 and len(supported)>=3:
            consensus=_mean_axes(supported)
            if (all(axis_distance(t,consensus)<=5 for t in supported)
                and axis_distance(consensus,local_theta)<=9):
                angle=_mean_axes(supported+[local_theta],
                                 weights=[1]*len(supported)+[.7])
                out.update(status="PROPOSED_NOT_VALIDATED",reason=None,
                           unlabelled_axes_deg=[round(angle,3),round(angle+90,3)],
                           promotion_reason="THREE_OF_FOUR_NATIVE_PATCHES_AND_HESSIAN_AGREE",
                           requires_manual_confirmation=False)
    # Never rescue an abstention from Hessian edges alone; edges can be twill.
    return out
