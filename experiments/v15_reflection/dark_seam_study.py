"""Falsification study: half-wave dark-seam ridges in denim images.

CANDIDATE ONLY: this module does not identify physical yarns, weave family,
warp/weft, frame scale or yarn count. Median-vs-Gaussian agreement is not
independent physical proof. Never use its angle to override manual V5 reference.
"""
from __future__ import annotations

import argparse
import json
import cv2
import numpy as np

VERSION = "v15-dark-seam-ablation.1"


def angle_delta(a, b):
    return abs((float(a)-float(b)+90.)%180.-90.)


def extract(image_bgr, background="gaussian", threshold=.55, dilate_px=3):
    """Actual median vs Gaussian MEAN: original proposal called mean 'median'."""
    if background not in ("median","gaussian"):
        raise ValueError("background must be median or gaussian")
    h,w=image_bgr.shape[:2]
    s=min(600,h,w)
    roi=image_bgr[(h-s)//2:(h+s)//2,(w-s)//2:(w+s)//2]
    lab=cv2.cvtColor(roi,cv2.COLOR_BGR2LAB)
    L=lab[:,:,0].astype(np.float32)
    base=(cv2.medianBlur(lab[:,:,0],31).astype(np.float32)
          if background=="median" else cv2.GaussianBlur(L,(31,31),7.))
    difference=L-base
    local_std=np.sqrt(cv2.GaussianBlur(difference**2,(31,31),7.)+1e-5)
    bright=(difference>threshold*local_std).astype(np.uint8)
    forbidden=cv2.dilate(bright,cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE,(2*dilate_px+1,2*dilate_px+1)))>0
    valid=~forbidden
    dark=np.maximum(0.,base-L)
    return roi,dark,valid,{"mask_valid_fraction":float(valid.mean()),
                           "bright_seed_fraction":float(bright.mean()),
                           "mean_valid_dark":float(dark[valid].mean())
                             if valid.any() else 0.}


def dark_ridge(dark, valid, sigma=1.2):
    """Bright ridge in inverted darkness: tangent is lambda_max eigenvector.

    Old proposal added +90deg to this eigenvector, actually reporting its
    normal. The sign of the Hessian trace selects a bright narrow ridge.
    """
    blur=cv2.GaussianBlur(dark,(0,0),sigma)
    ixx=cv2.Sobel(blur,cv2.CV_32F,2,0,ksize=3)
    iyy=cv2.Sobel(blur,cv2.CV_32F,0,2,ksize=3)
    ixy=cv2.Sobel(blur,cv2.CV_32F,1,1,ksize=3)
    trace=ixx+iyy
    curvature=np.sqrt((ixx-iyy)**2+4*ixy**2+1.e-8)
    tangent=np.degrees(.5*np.arctan2(2*ixy,ixx-iyy))%180.
    strength=np.maximum(0.,-trace)*curvature
    if valid.sum()<150 or np.max(strength[valid])<1.e-4:
        return None,{"reason":"NO_VALID_RIDGE_SUPPORT"}
    cutoff=max(float(np.percentile(strength[valid],65)),1.e-5)
    selected=valid&(strength>cutoff)
    if selected.sum()<150:return None,{"reason":"SPARSE_RIDGE_PIXELS"}
    hist=np.histogram(tangent[selected],bins=360,range=(0.,180.),
                      weights=strength[selected])[0].astype(float)
    weights=np.exp(-.5*(np.arange(-5,6)/1.6)**2)
    weights/=weights.sum()
    smooth=np.zeros_like(hist)
    for j,a in enumerate(weights):
        smooth+=a*np.roll(hist,j-5)
    index=int(np.argmax(smooth))
    return (index+.5)*.5,{"ridge_pixel_fraction":float(selected.mean()),
                          "max_hist_strength":float(smooth[index])}


def propose(image_bgr):
    """Two-background agreement only, UNVERIFIED IMAGE RIDGE, NOT REAL YARN."""
    evidences=[]
    for background in ("gaussian","median"):
        _,dark,valid,info=extract(image_bgr,background=background)
        angle,details=dark_ridge(dark,valid)
        evidences.append({"background":background,
                          "candidate_deg":angle,**info,**details})
    a,b=[r["candidate_deg"] for r in evidences]
    result={"method":VERSION,"evidence":evidences,
            "physical_yarn_confirmed":False,
            "warp_weft_identified":False,
            "density_per_cm":None,
            "status":"ABSTAINED","axis_deg":None}
    if a is None or b is None:
        return {**result,"reason":"INSUFFICIENT_RIDGE_EVIDENCE"}
    if angle_delta(a,b)>7.:
        return {**result,"reason":"BACKGROUND_REPRESENTATION_CONFLICT"}
    c=np.exp(2j*np.deg2rad([a,b])).sum()
    theta=float(np.degrees(np.angle(c))/2%180)
    return {**result,"status":"CONSISTENT_IMAGE_RIDGE_UNVERIFIED",
            "axis_deg":round(theta,3),"reason":None,
            "orthogonal_geometry_only_deg":round((theta+90)%180,3)}


def pipeline_visual(image_bgr, out_path):
    roi,dark,valid,_=extract(image_bgr,background="gaussian")
    scale=max(float(np.percentile(dark,99.5)),1.e-5)
    dark8=np.uint8(255*np.clip(dark/scale,0,1))
    masked=dark8*valid.astype(np.uint8)
    row=[roi,cv2.cvtColor(dark8,cv2.COLOR_GRAY2BGR),
         cv2.cvtColor(masked,cv2.COLOR_GRAY2BGR)]
    cv2.imwrite(out_path,np.hstack(row))


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("image")
    p.add_argument("--visualization")
    args=p.parse_args(argv)
    im=cv2.imread(args.image)
    if im is None:raise ValueError("Image not readable: "+args.image)
    print(json.dumps(propose(im),ensure_ascii=False,indent=2))
    if args.visualization:pipeline_visual(im,args.visualization)


if __name__=="__main__":
    main()
