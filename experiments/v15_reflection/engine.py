"""V1.5-inspired, reflection-only *candidate* fabric metrology.

Never claim physical yarn correspondence or certified density.  A confirmed
50-mm planar frame is required even for candidate counts/cm; reference yarn
axes and warp/weft identity are separate human facts. No imports from V5.
Dependencies: numpy and Pillow. All computation is deterministic.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image

VERSION = "v15-reflectance-mvp.1"
FRAME_MM = 50.0
MAX_SIDE = 1792


def axis_angle(points):
    if len(points) != 2:
        raise ValueError("reference needs exactly two distinct points")
    (x1, y1), (x2, y2) = [[float(v) for v in pt] for pt in points]
    if any(not math.isfinite(v) for v in (x1, y1, x2, y2)):
        raise ValueError("nonfinite reference point")
    if math.hypot(x2-x1, y2-y1) < 20:
        raise ValueError("reference segment must span at least 20 input pixels")
    return math.degrees(math.atan2(y2-y1, x2-x1)) % 180


def _perspective(source, target):
    """Find homography source -> target using 4 point correspondences."""
    m, b = [], []
    for (x,y), (u,v) in zip(source, target):
        m.extend([[x,y,1,0,0,0,-u*x,-u*y],
                  [0,0,0,x,y,1,-v*x,-v*y]])
        b.extend([u,v])
    coeff = np.linalg.solve(np.asarray(m, dtype=float), np.asarray(b, dtype=float))
    return np.array([*coeff, 1.0], dtype=float).reshape(3,3)


def _transform_point(h, pt):
    p = h @ np.array([float(pt[0]), float(pt[1]), 1.0])
    if abs(p[2]) < 1.e-9:
        raise ValueError("degenerate perspective")
    return [float(p[0]/p[2]), float(p[1]/p[2])]


def prepare_roi(image, corners=None, frame_confirmed=False, reference=None):
    """Rectify true 5 cm square, or downscale for uncalibrated visual analysis.

    The physical resolution is never silently improved by upsampling.
    """
    w, h = image.size
    if w < 96 or h < 96:
        raise ValueError("IMAGE_TOO_SMALL")
    if corners is not None and frame_confirmed:
        if len(corners) != 4 or any(len(p) != 2 for p in corners):
            raise ValueError("expected TL TR BR BL inner frame corners")
        pts = np.asarray(corners, dtype=float)
        if not np.isfinite(pts).all():
            raise ValueError("invalid frame corners")
        edges = np.linalg.norm(np.roll(pts, -1, axis=0) - pts, axis=1)
        if np.min(edges) < 80:
            raise ValueError("FRAME_TOO_SMALL")
        # Avoid super-resolution and memory spikes on the target RK3576.
        side = min(MAX_SIDE, int(np.min(edges)))
        target = [[0,0],[side-1,0],[side-1,side-1],[0,side-1]]
        dst_to_src = _perspective(target, pts)
        inv = np.linalg.inv(dst_to_src)
        if np.linalg.cond(dst_to_src) > 1.e9:
            raise ValueError("DEGENERATE_FRAME")
        # Pillow PERSPECTIVE inverse maps destination to input.
        inv_coeff = [float(dst_to_src.flat[i]) for i in (0,1,2,3,4,5,6,7)]
        roi = image.convert("RGB").transform(
            (side,side), Image.Transform.PERSPECTIVE, inv_coeff,
            resample=Image.Resampling.BICUBIC)
        ref = [_transform_point(inv, p) for p in reference] if reference else None
        return roi, FRAME_MM/side, ref, {"confirmed": True,
                    "frame_mm": FRAME_MM, "roi_side_px": side,
                    "mm_per_px": FRAME_MM/side,
                    "capture_mm_per_px_estimate": FRAME_MM/float(np.min(edges)),
                    "downsampled_working_roi": side < int(np.min(edges)),
                    "meets_v15_0_015_mm_per_px": FRAME_MM/float(np.min(edges)) <= 0.015}
    # Never reuse unconfirmed, merely supplied corners as a scale.
    ratio = min(1.0, MAX_SIDE / max(w,h))
    roi = image.convert("RGB")
    if ratio != 1.0:
        roi = roi.resize((int(w*ratio), int(h*ratio)), Image.Resampling.LANCZOS)
    ref = [[x*ratio,y*ratio] for x,y in reference] if reference else None
    return roi, None, ref, {"confirmed": False, "reason": "FRAME_NOT_CONFIRMED",
                             "mm_per_px": None}


def gate2(image):
    sample = image.copy()
    sample.thumbnail((512,512))
    arr = np.asarray(sample.convert("L"), dtype=np.float32)
    q5, q95 = np.percentile(arr, [5,95])
    gy,gx = np.gradient(arr)
    focus = float(np.mean(gx*gx+gy*gy))
    reasons = []
    if q95-q5 < 15: reasons.append("LOW_CONTRAST")
    if np.mean(arr > 249) > .90: reasons.append("OVEREXPOSED")
    if np.mean(arr < 6) > .90: reasons.append("UNDEREXPOSED")
    if focus < 3.5: reasons.append("LOW_FOCUS_ENERGY")
    return {"status": "FAIL" if reasons else "PASS", "reasons": reasons,
            "contrast_p95_minus_p5": round(float(q95-q5),3),
            "gradient_energy": round(focus,3)}


def _peaks(a, start, end):
    """Indices of strict local maxima, largest first."""
    return sorted((i for i in range(max(1,start),min(len(a)-1,end+1))
                   if a[i] > a[i-1] and a[i] >= a[i+1]),
                  key=lambda i: float(a[i]), reverse=True)


def _pitch(profile, min_pitch=7, max_pitch=85):
    """Cross-check 1D projection FFT and unbiased autocorrelation."""
    x = np.asarray(profile, dtype=float)
    n = len(x)
    if n < 96: return {"reason": "SHORT_STRIP"}
    t = np.linspace(-1,1,n)
    x = x - np.polyval(np.polyfit(t,x,1),t)
    # Broad shading/illumination trend rejection (preserves yarn scale).
    k = min(121, max(21, (n//6)|1))
    x = x - np.convolve(np.pad(x,(k//2,k//2),mode="reflect"),
                         np.ones(k)/k,mode="valid")[:n]
    if np.std(x) < 1.5: return {"reason": "WEAK_PERIODIC_SIGNAL"}
    power = np.abs(np.fft.rfft(x * np.hanning(n)))**2
    f = np.fft.rfftfreq(n)
    power[(f < 1/max_pitch) | (f > 1/min_pitch)] = 0
    candidates = _peaks(power,1,len(power)-2)[:8]
    if not candidates: return {"reason": "FFT_PEAK_NOT_FOUND"}
    z = x-np.mean(x)
    ac = np.fft.irfft(np.abs(np.fft.rfft(z,n=2*n))**2,n=2*n)[:n]
    ac = ac / max(ac[0],1e-9) * n / np.maximum(n-np.arange(n),1)
    ac_peaks = _peaks(ac,min_pitch,max_pitch)
    accepted = []
    for i in candidates:
        period_fft = 1/f[i]
        near = [j for j in ac_peaks if abs(j-period_fft)/period_fft <= .13
                and ac[j] >= .20]
        if not near: continue
        lag = min(near,key=lambda j: abs(j-period_fft))
        score = float(power[i]/max(power[candidates[0]],1.e-9)) * .65 + float(ac[lag])*.35
        accepted.append((score,float(lag),float(period_fft),float(ac[lag])))
    if not accepted: return {"reason": "FFT_AUTOCORR_DISAGREE"}
    accepted.sort(reverse=True)
    top = accepted[0]
    # Period doubling/halving cannot be silently called real yarn count.
    for alt in accepted[1:]:
        ratio = max(top[1],alt[1])/min(top[1],alt[1])
        if 1.87 <= ratio <= 2.13 and alt[0] >= .77*top[0]:
            return {"reason": "HARMONIC_AMBIGUITY"}
    return {"period_px": top[1], "fft_period_px": round(top[2],3),
            "autocorrelation": round(top[3],4),
            "score": round(top[0],4)}


def _count_peaks(profile, pitch):
    """Independent count/physical-length estimator; not a yarn instance model."""
    x = np.asarray(profile,dtype=float)
    x = np.convolve(np.pad(x,(2,2),mode="reflect"),np.ones(5)/5,mode="valid")
    k = int(max(3,round(.40*pitch)))
    maxima = [i for i in range(k,len(x)-k)
              if x[i] == np.max(x[i-k:i+k+1])
              and x[i] > np.median(x) + .25*np.std(x)]
    selected=[]
    for i in maxima:
        if not selected or i-selected[-1] >= .65*pitch:
            selected.append(i)
        elif x[i] > x[selected[-1]]:
            selected[-1]=i
    return selected


def analyze_axis(image, direction_deg, mm_per_px=None):
    """Follow an operator axis, project in five along-yarn strips."""
    angle = float(direction_deg) % 180
    rotated = image.convert("L").rotate(angle, resample=Image.Resampling.BICUBIC,
                                         expand=False, fillcolor=127)
    s = int(min(rotated.size)*.64)
    cx,cy = rotated.width//2,rotated.height//2
    crop = np.asarray(rotated.crop((cx-s//2,cy-s//2,cx-s//2+s,cy-s//2+s)),
                      dtype=np.float32)
    profiles = [crop[:,int(j*s/5):int((j+1)*s/5)].mean(axis=1)
                for j in range(5)]
    measures = [_pitch(p) for p in profiles]
    good = [m for m in measures if "period_px" in m]
    reasons=[]
    if len(good)<3: reasons.append("INSUFFICIENT_CONSISTENT_STRIPS")
    periods = np.asarray([m["period_px"] for m in good])
    pitch = float(np.median(periods)) if len(periods) else None
    dispersion = float(np.std(periods)/np.mean(periods)) if len(periods) else None
    if dispersion is not None and dispersion > .085: reasons.append("PERIOD_UNSTABLE")
    lines = _count_peaks(crop.mean(axis=1),pitch) if pitch is not None else []
    if len(lines) < 7: reasons.append("INSUFFICIENT_PERIODIC_CENTERS")
    density_spacing = 10/(pitch*mm_per_px) if pitch and mm_per_px else None
    density_count = 10*len(lines)/(s*mm_per_px) if mm_per_px else None
    method_delta = (abs(density_spacing-density_count)/density_spacing
                    if density_spacing and density_count else None)
    if method_delta is not None and method_delta>.15:
        reasons.append("DENSITY_METHOD_CONFLICT")
    if mm_per_px is None: reasons.append("FRAME_NOT_CONFIRMED")
    return {"axis_deg": round(angle,4), "gate3": "LOW_CONFIDENCE" if reasons else "PASS",
            "reasons": reasons, "pitch_px": round(pitch,4) if pitch else None,
            "strip_period_px": [m.get("period_px") for m in measures],
            "strip_reasons": [m.get("reason") for m in measures],
            "strip_cv": round(dispersion,5) if dispersion is not None else None,
            "counted_projection_peaks": len(lines),
            "counted_positions_roi_y": lines,
            "density_by_spacing_per_cm": round(density_spacing,4) if density_spacing else None,
            "density_by_count_per_cm": round(density_count,4) if density_count else None,
            "method_difference_ratio": round(method_delta,5) if method_delta is not None else None,
            "candidate_density_per_cm": round(density_spacing,4)
               if density_spacing is not None and not reasons else None,
            "evidence": "projection peaks; NOT verified physical yarn centerlines"}


def _fft_orientation(image):
    """Auto axis *proposal* only: twill can dominate, therefore never certified."""
    small=image.convert("L")
    small.thumbnail((512,512))
    a=np.asarray(small,dtype=float)
    h,w=a.shape
    angles=[]
    for y in (0,h//2):
        for x in (0,w//2):
            patch=a[y:y+h//2,x:x+w//2]
            patch=patch-patch.mean()
            fft=np.abs(np.fft.fftshift(np.fft.fft2(
                patch*np.outer(np.hanning(len(patch)),np.hanning(patch.shape[1])))))**2
            yy,xx=np.indices(fft.shape)
            u=(xx-fft.shape[1]//2)/fft.shape[1]
            v=(yy-fft.shape[0]//2)/fft.shape[0]
            radius=np.hypot(u,v)
            fft[(radius<.015)|(radius>.18)]=0
            py,px=np.unravel_index(int(np.argmax(fft)),fft.shape)
            if fft[py,px] <= 0: continue
            angles.append(float((math.degrees(math.atan2(v[py,px],u[py,px]))+90)%180))
    if not angles: return None, None
    doubled=np.deg2rad(np.array(angles)*2)
    base=float(math.degrees(math.atan2(np.sin(doubled).mean(),np.cos(doubled).mean()))/2 %180)
    err=[min(abs((a-base)%180),180-abs((a-base)%180)) for a in angles]
    return base, float(max(err))


def _color(image):
    a=np.asarray(image.convert("RGB").resize((128,128)),dtype=np.uint8)
    med=np.median(a.reshape(-1,3),axis=0).astype(int).tolist()
    variation=float(np.std(np.asarray(image.convert("L").resize((128,128)),dtype=float)))
    return {"status":"CANDIDATE","median_rgb":med,"luminance_std":round(variation,2),
            "note":"surface color/texture summary, not yarn direction evidence"}


def measure(image, reference_points=None, confirm_reference=False,
            corners=None, confirm_corners=False, warp_family=None):
    """Return ten-position contract and physical scale provenance.

    A/B refer to yarn-axis families, never warp/weft until manually assigned.
    Angle of B is an orthogonal hypothesis, NOT independent yarn identification.
    """
    if warp_family not in (None,"A","B"):
        raise ValueError("warp_family must be A, B or absent")
    quality=gate2(image)
    output={"schema_version":"1.0","algorithm":VERSION, "source":"INDEPENDENT_V15_REFLECTION",
            "candidate_only":True,"gate2":quality,"ten_parameters": {str(i).zfill(2): {"name": name,
                "status": "UNAVAILABLE", "value": None}
                for i, name in enumerate((
                    "warp_angle","weft_angle","warp_arrangement","weft_arrangement",
                    "warp_width","weft_width","weave","warp_density","weft_density",
                    "surface_texture_color"),1)},
            "limitations":["reflectance only","no physical yarn instance validation",
                           "perpendicular B is a geometric candidate"]}
    if quality["status"]=="FAIL":
        output.update(status="REJECTED",failure_reasons=quality["reasons"])
        return output
    roi,scale,points,geometry=prepare_roi(image,corners,confirm_corners,reference_points)
    output["geometry"]=geometry
    if reference_points is not None and confirm_reference is True:
        if axis_angle(reference_points) is None: raise ValueError("reference not found")
        direction=axis_angle(points)
        orientation_source="USER_CONFIRMED_REAL_YARN_REFERENCE"
        jitter=None
    else:
        direction,jitter=_fft_orientation(roi)
        orientation_source="AUTO_FFT_UNVERIFIED"
    if direction is None:
        output.update(status="REJECTED",failure_reasons=["ORIENTATION_NOT_FOUND"])
        return output
    if jitter is not None and jitter>8:
        output.update(status="REJECTED",failure_reasons=["AUTO_ORIENTATION_UNSTABLE"],
                      orientation={"source":orientation_source,"candidate_deg":round(direction,3),
                                   "patch_dispersion_deg":round(jitter,3)})
        return output
    aa=analyze_axis(roi,direction,scale)
    bb=analyze_axis(roi,(direction+90)%180,scale)
    output["orientation"]={"source":orientation_source,"reference_axis_deg":round(direction,4),
                           "orthogonal_hypothesis_deg":round((direction+90)%180,4),
                           "patch_dispersion_deg":jitter}
    output["axes"]={"A":aa,"B":bb}
    output["surface"]=_color(roi)
    confirmed_reference=orientation_source=="USER_CONFIRMED_REAL_YARN_REFERENCE"
    identity=warp_family in ("A","B") and confirmed_reference
    warp=warp_family if identity else None
    weft=("B" if warp=="A" else "A") if warp else None
    for idx,kind,axis in ((1,"warp_angle",warp),(2,"weft_angle",weft),
                          (3,"warp_arrangement",warp),(4,"weft_arrangement",weft),
                          (5,"warp_width",warp),(6,"weft_width",weft),
                          (7,"weave",None),(8,"warp_density",warp),
                          (9,"weft_density",weft),(10,"surface_texture_color",None)):
        item={"name":kind,"status":"UNAVAILABLE","value":None}
        if idx in (1,2) and axis:
            item={"name":kind,"status":"CANDIDATE","value":output["axes"][axis]["axis_deg"]}
        elif idx in (3,4) and axis and output["axes"][axis]["strip_cv"] is not None:
            item={"name":kind,"status":"CANDIDATE","value":{
                  "strip_cv":output["axes"][axis]["strip_cv"],
                  "label":"REGULAR_CANDIDATE" if output["axes"][axis]["strip_cv"] < .08 else "UNSTABLE"}}
        elif idx in (8,9) and axis and output["axes"][axis]["candidate_density_per_cm"] is not None:
            item={"name":kind,"status":"CANDIDATE",
                  "value":output["axes"][axis]["candidate_density_per_cm"]}
        elif idx==10:
            item={"name":kind,**output["surface"]}
        output["ten_parameters"][str(idx).zfill(2)]=item
    failures=list(dict.fromkeys(aa["reasons"]+bb["reasons"]))
    if not identity: failures.append("WARP_WEFT_NOT_CONFIRMED")
    if not confirmed_reference: failures.append("AUTO_DIRECTION_NOT_VALIDATED")
    if scale is not None and not geometry["meets_v15_0_015_mm_per_px"]:
        failures.append("BELOW_V15_PHYSICAL_RESOLUTION_RECOMMENDATION")
    output["failure_reasons"]=list(dict.fromkeys(failures))
    output["status"]="CANDIDATE" if all(a["gate3"]=="PASS" for a in (aa,bb)) else "LOW_CONFIDENCE"
    # Gate3 PASS is only internal periodicity agreement, NOT GT certification.
    return output


def main(argv=None):
    p=argparse.ArgumentParser(description="Independent reflection-only V1.5 candidate metrology")
    p.add_argument("--image",type=Path,required=True)
    p.add_argument("--reference",help="x1,y1,x2,y2 on original image")
    p.add_argument("--confirm-reference",action="store_true")
    p.add_argument("--corners",help="JSON TL,TR,BR,BL corners of the 50mm INNER frame")
    p.add_argument("--confirm-corners",action="store_true")
    p.add_argument("--warp-family",choices=("A","B"))
    p.add_argument("--out",type=Path,required=True)
    args=p.parse_args(argv)
    points=None
    if args.reference:
        nums=[float(x) for x in args.reference.split(",")]
        if len(nums)!=4: p.error("--reference requires x1,y1,x2,y2")
        points=[nums[:2],nums[2:]]
    corners=json.loads(args.corners) if args.corners else None
    with Image.open(args.image) as img:
        result=measure(img,points,args.confirm_reference,corners,args.confirm_corners,args.warp_family)
    result["image_sha256"]=hashlib.sha256(args.image.read_bytes()).hexdigest()
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":result["status"],"output":str(args.out),
                      "failure_reasons":result["failure_reasons"]},ensure_ascii=False))
    return 0 if result["status"]=="CANDIDATE" else 3


if __name__=="__main__":
    raise SystemExit(main())
