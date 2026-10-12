"""Shared image utilities for frozen-V4 based 10-parameter Demo.

Contains calibration, quality, color, formatting ONLY. No yarn/direction estimator.
"""
from __future__ import annotations
import base64
import math
from typing import Any
import cv2
import numpy as np

CM = 5.0

SIZE = 901

LABELS = ["经向","纬向","经纱排列状态","纬纱排列状态","经纱粗细","纬纱粗细","组织结构","经密","纬密","表面纹理与色系"]

MODULES = ["A","A","A","A","B","B","C","B","B","D"]

def decode_image(data: bytes) -> np.ndarray:
    if len(data) > 16*1024*1024:
        raise ValueError("图片文件超过 16 MB")
    im = cv2.imdecode(np.frombuffer(data,np.uint8),cv2.IMREAD_COLOR)
    if im is None or min(im.shape[:2]) < 128:
        raise ValueError("不是有效的图片，或短边小于 128 px")
    if max(im.shape[:2]) > 8000:
        raise ValueError("图片边长过大，请先缩小到 8000 px 以内")
    return im

def shrink(image: np.ndarray, maxsize=980) -> np.ndarray:
    h,w=image.shape[:2]
    k=min(1.,maxsize/max(w,h))
    if k >= 1: return image.copy()
    return cv2.resize(image,(round(w*k),round(h*k)),interpolation=cv2.INTER_AREA)

def image_uri(img: np.ndarray, quality=83) -> str:
    ok,buffer=cv2.imencode('.jpg',img,[cv2.IMWRITE_JPEG_QUALITY,quality])
    if not ok: raise RuntimeError('JPEG encode error')
    return 'data:image/jpeg;base64,' + base64.b64encode(buffer).decode('ascii')

def calibrate(img: np.ndarray, corners, confirm: bool) -> tuple[np.ndarray,dict[str,Any]]:
    if corners is None:
        return shrink(img), {'status':'UNAVAILABLE','confirmed':False,'physical_size_cm':None,'cm_per_px':None,
             'inner_corners_px':None,'notes':'未提供实体方框内侧四角，禁止计算物理经纬密度'}
    pts=np.asarray(corners,dtype=np.float32)
    if pts.shape != (4,2) or not np.isfinite(pts).all():
        raise ValueError('四角必须为 TL, TR, BR, BL 的 4 组像素坐标')
    h,w=img.shape[:2]
    if np.any(pts[:,0]<0) or np.any(pts[:,0]>=w) or np.any(pts[:,1]<0) or np.any(pts[:,1]>=h):
        raise ValueError('标定点超出原图范围')
    if not cv2.isContourConvex(pts) or cv2.contourArea(pts,oriented=True)<max(300,.0005*h*w):
        raise ValueError('四角不构成足够大的凸四边形，检查点击顺序')
    dst=np.float32([[0,0],[SIZE-1,0],[SIZE-1,SIZE-1],[0,SIZE-1]])
    H=cv2.getPerspectiveTransform(pts,dst)
    if abs(np.linalg.det(H))<1e-10: raise ValueError('标定变换无法求逆')
    rect=cv2.warpPerspective(img,H,(SIZE,SIZE),flags=cv2.INTER_LINEAR)
    return rect,{'status':'CALIBRATED_HUMAN_CONFIRMED' if confirm else 'CALIBRATION_PROVISIONAL',
        'confirmed':bool(confirm),'physical_size_cm':[CM,CM],
        'cm_per_px':CM/(SIZE-1),'inner_corners_px':pts.tolist(),
        'homography':H.tolist(),'notes':'仅对框内同一平面的长度进行几何换算；照片边框内角由用户确认' if confirm else '四角尚未人工确认；物理量不可作为正式结果'}

def quality_metrics(roi: np.ndarray) -> dict:
    img=shrink(roi,600)
    gray=cv2.cvtColor(img,cv2.COLOR_BGR2GRAY)
    sharp=float(cv2.Laplacian(gray,cv2.CV_64F).var())
    bright=float(gray.mean())
    white=float((gray>250).mean())
    dark=float((gray<8).mean())
    flags=[]
    if sharp<28:flags.append('局部清晰度偏低，可能影响纱线计数')
    if white>.09:flags.append('高亮区域较多，可能存在过曝')
    if dark>.09:flags.append('暗部占比较高，可能隐藏交织点')
    if not flags:flags=['图像质量基础指标通过；不等于识别准确率合格']
    return {'sharpness_laplacian_variance':round(sharp,1),'average_grayscale':round(bright,1),
        'overexposed_fraction':round(white,4),'underexposed_fraction':round(dark,4),'warnings':flags}

def color_and_texture(roi:np.ndarray) -> dict:
    sample=shrink(roi,420)
    rgb=cv2.cvtColor(sample,cv2.COLOR_BGR2RGB)
    hsv=cv2.cvtColor(sample,cv2.COLOR_BGR2HSV)
    flat=rgb.reshape(-1,3)
    rng=np.random.default_rng(29)
    sel=flat[rng.choice(len(flat),size=min(4500,len(flat)),replace=False)]
    cv2.setRNGSeed(29)
    _,labels,centers=cv2.kmeans(sel.astype(np.float32),3,None,
            (cv2.TERM_CRITERIA_EPS+cv2.TERM_CRITERIA_MAX_ITER,22,.4),5,cv2.KMEANS_PP_CENTERS)
    counts=np.bincount(labels.ravel(),minlength=3)
    idx=np.argsort(counts)[::-1]
    colors=[]
    for i in idx:
        r,g,b=np.clip(centers[i],0,255).astype(int)
        colors.append({'hex':f'#{r:02X}{g:02X}{b:02X}', 'ratio':round(float(counts[i]/len(sel)),3)})
    gray=cv2.cvtColor(sample,cv2.COLOR_BGR2GRAY)
    gx=cv2.Sobel(gray,cv2.CV_32F,1,0,ksize=3)
    gy=cv2.Sobel(gray,cv2.CV_32F,0,1,ksize=3)
    magn=np.sqrt(gx*gx+gy*gy)
    # gradient direction ≠ yarn orientation; treat as surface texture only.
    hist,_=np.histogram((np.rad2deg(np.arctan2(gy,gx))+90)%180,bins=np.arange(0,181,10),weights=magn)
    tex_deg=float(np.argmax(hist)*10+5)
    return {'dominant_colors':colors,'mean_hsv':np.round(hsv.reshape(-1,3).mean(axis=0),1).tolist(),
      'texture_orientation_candidate_deg':tex_deg,
      'edge_strength_mean':round(float(magn.mean()),2),
      'surface_contrast_std':round(float(gray.std()),2),
      'texture_note':'纹理方向仅用于参数10，严禁作为经纬纱线方向真值'}

def _parameter(pid,value,status,unit=None,evidence=None,notes='',options=None):
    return {'id':pid,'name':LABELS[pid-1],'module':MODULES[pid-1],
        'status':status,'value':value,'unit':unit,'confidence':None,
        'evidence':evidence or [],'notes':notes,'candidates':options or []}
