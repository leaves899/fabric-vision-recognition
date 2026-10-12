"""Experimental real-yarn-axis proposal from joint orthogonal spectral and ACF evidence.

Neither Fourier texture peaks nor autocorrelation lattice vectors are verified
physical yarn directions; fail closed when independent evidence disagrees.
No ground-truth or sample-specific angle is ever passed to this estimator.
"""
from __future__ import annotations

import math
import numpy as np
from PIL import Image, ImageFilter

ORIENTATION_VERSION = "orthogonal-spectrum-acf-0.1"
BIN_DEG = 3
N_BINS = 180 // BIN_DEG
WINDOW = 72


def _canonical_delta(a, b):
    """Distance of unlabelled perpendicular axis pairs (90-degree symmetry)."""
    z = abs((float(a)-float(b)) % 90.0)
    return min(z,90.0-z)


def _bin_axes(angles, weights):
    idx=np.floor((angles % 180)/BIN_DEG).astype(int) % N_BINS
    return np.bincount(idx.ravel(),weights=np.asarray(weights).ravel(),
                       minlength=N_BINS).astype(float)


def _pair_score(hist):
    """Wants two orthogonal directional families, not one diagonal twill band."""
    h=np.asarray(hist,float)
    folded=np.sqrt(np.maximum(h[:30],0)*np.maximum(h[30:],0))
    sm=(np.roll(folded,1)+2*folded+np.roll(folded,-1))/4
    rank=np.argsort(sm)[::-1]
    best=int(rank[0])
    other=next((int(i) for i in rank[1:] if min(abs(int(i)-best),30-abs(int(i)-best))>=4),int(rank[-1]))
    return (best+.5)*BIN_DEG,float(sm[best]),float(sm[other]),float(np.median(sm))


def _spectral(image):
    """Return orthogonal pair orientation: strength from both spatial families."""
    image=image.convert("L")
    image.thumbnail((768,768),Image.Resampling.LANCZOS)
    w,h=image.size
    s=min(w,h)
    left=(w-s)//2
    top=(h-s)//2
    tile=image.crop((left,top,left+s,top+s))
    # Do not enlarge; lower image resolution cannot support physical pitch.
    a=np.asarray(tile,dtype=np.float32)
    if s < 160 or np.std(a)<5:
        return None,{"reason":"INSUFFICIENT_IMAGE_STRUCTURE"}
    bg=np.asarray(tile.filter(ImageFilter.GaussianBlur(radius=15)),dtype=np.float32)
    a=a-bg
    a*=np.outer(np.hanning(s),np.hanning(s))
    spectrum=np.abs(np.fft.fftshift(np.fft.fft2(a)))**2
    fy=np.fft.fftshift(np.fft.fftfreq(s))
    fx=fy
    yy,xx=np.meshgrid(fy,fx,indexing="ij")
    radius=np.hypot(xx,yy)
    mask=(radius>=.012)&(radius<=.19)
    # Normalize power across radius bands, so dominant low-frequency twill
    # cannot automatically overrule two weaker orthogonal yarn signatures.
    ring=np.minimum((radius*120).astype(int),25)
    hist_ring=np.bincount(ring[mask].ravel(),
                          weights=spectrum[mask].ravel(),minlength=26)
    counts=np.bincount(ring[mask].ravel(),minlength=26)
    avg=hist_ring/np.maximum(counts,1)
    normalized=np.where(mask, spectrum/np.maximum(avg[ring],1e-8),0)
    normalized=np.sqrt(np.maximum(normalized,0))
    normal_angle=(np.degrees(np.arctan2(yy,xx))+180)%180
    line_angle=(normal_angle+90)%180
    directional=_bin_axes(line_angle,normalized)
    theta,peak,other,median=_pair_score(directional)
    return theta,{"fft_two_family_score":round(peak,4),
                  "fft_runner_up_score":round(other,4),
                  "fft_pair_to_median":round(peak/max(median,1e-8),4),
                  "fft_peak_to_runner":round(peak/max(other,1e-8),4),
                  "original_side_px":s,
                  "field":a}


def _ac_lattice(field):
    """Evaluate correlation-maxima translation directions, not raw FFT axes."""
    s=field.shape[0]
    p=np.abs(np.fft.fft2(field))**2
    ac=np.fft.fftshift(np.fft.ifft2(p).real)
    ac=ac/max(ac[s//2,s//2],1e-8)
    d=min(WINDOW,s//4)
    patch=ac[s//2-d:s//2+d+1,s//2-d:s//2+d+1]
    y,x=np.indices(patch.shape)
    y=y-d
    x=x-d
    radius=np.hypot(x,y)
    valid=(radius>=7)&(radius<d)
    # Maxima in surrounding +/- 2px, without scipy dependency.
    peaks=valid & (patch>=.055)
    for dy in (-2,-1,0,1,2):
        for dx in (-2,-1,0,1,2):
            if dy==0 and dx==0: continue
            shifted=np.roll(np.roll(patch,dy,axis=0),dx,axis=1)
            peaks &= patch>=shifted
    if not np.any(peaks):
        return None,{"reason":"NO_AUTOCORRELATION_LATTICE_PEAKS",
                     "ac_peak_count":0}
    # Multiple repeats along a periodic axis reinforce it; prefer short lag.
    v=np.clip(patch[peaks],0,None)/(radius[peaks]**.3)
    direction=(np.degrees(np.arctan2(y[peaks],x[peaks]))+180)%180
    h=_bin_axes(direction,v)
    theta,peak,other,median=_pair_score(h)
    return theta,{"ac_peak_count":int(np.count_nonzero(peaks)),
                  "ac_two_family_score":round(peak,6),
                  "ac_pair_to_median":round(peak/max(median,1e-8),4),
                  "ac_peak_to_runner":round(peak/max(other,1e-8),4)}


def propose_axes(image):
    """Automated proposal or explicit rejection. Output axis pair unlabelled."""
    theta,fft=_spectral(image)
    if theta is None: return {"status":"ABSTAINED",**fft,"method":ORIENTATION_VERSION}
    field=fft.pop("field")
    ac_theta,ac=_ac_lattice(field)
    result={"method":ORIENTATION_VERSION,"status":"ABSTAINED",
            "spectrum_axis_deg":round(theta%90,3),
            "acf_axis_deg":round(ac_theta%90,3) if ac_theta is not None else None,
            "unlabelled_axes_deg":None,
            **fft,**ac}
    if ac_theta is None:
        result["reason"]="AUTOCORRELATION_UNSUPPORTED"
    elif _canonical_delta(theta,ac_theta)>9:
        result["reason"]="SPECTRUM_ACF_AXIS_CONFLICT"
    elif fft["fft_pair_to_median"]<1.11:
        result["reason"]="FOURIER_AXES_AMBIGUOUS"
    elif ac.get("ac_pair_to_median",0)<1.15:
        result["reason"]="ACF_AXES_AMBIGUOUS"
    else:
        # Orientations are intrinsically modulo 90: no warp/weft identity.
        theta_rad=math.radians(4*theta)
        ac_rad=math.radians(4*ac_theta)
        combined=(math.degrees(math.atan2(math.sin(theta_rad)+math.sin(ac_rad),
                       math.cos(theta_rad)+math.cos(ac_rad)))/4)%90
        result.update(status="PROPOSED_NOT_VALIDATED",reason=None,
                      unlabelled_axes_deg=[round(combined,3),
                                            round(combined+90,3)])
    result["method_disagreement_deg"]=round(_canonical_delta(theta,ac_theta),3) if ac_theta is not None else None
    return result
