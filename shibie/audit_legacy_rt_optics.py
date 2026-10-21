"""Controlled legacy renderer audit; GT used here only for renderer diagnostics."""
from dataclasses import replace
from pathlib import Path
import json
import cv2
import numpy as np
from synthetic_capture_8k import CaptureScene, _render_strip, _stripe_features

def audit(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    s=CaptureScene(rotation_deg=0,perspective=0,fabric_rotation_deg=0,
        shift_reflection_x=0,noise_sigma=0,diagonal_decoy=0)
    # Actual native-coordinate rectangle, not a resized image.
    a,b=_render_strip(s,2700,3300,np.eye(3),np.random.default_rng(41))
    c,d=_render_strip(replace(s,weave='twill_3_1'),2700,3300,np.eye(3),np.random.default_rng(41))
    yy,xx=np.mgrid[2700:3300,0:8000].astype(np.float32)
    *_,wc,fc=_stripe_features(xx,yy,s)
    roi=(xx>2100)&(xx<5900)
    masks={'pore':(wc<.05)&(fc<.05),'warp_only':(wc>.8)&(fc<.05),
        'weft_only':(fc>.8)&(wc<.05),'cross':(wc>.8)&(fc>.8)}
    stats={}
    for name,m in masks.items():
        stats[name]={}
        for mode,img in [('R',a),('T',b)]:
            q=cv2.cvtColor(img,cv2.COLOR_BGR2GRAY)[m&roi]
            stats[name][mode]={'count':int(q.size),'mean':float(q.mean()),'std':float(q.std()),
                'histogram_16':np.histogram(q,bins=16,range=(0,256))[0].tolist()}
    result={'same_geometry_seed_noise_off':True,'native_coordinate_rectangle':[0,2700,8000,3300],
        'R_mean_absolute_difference':float(np.abs(a.astype(float)-c).mean()),
        'T_mean_absolute_difference':float(np.abs(b.astype(float)-d).mean()),
        'T_changed_values':int(np.count_nonzero(b!=d)),'regions':stats,
        'failed_physics_gates':['T_IGNORES_WEAVE','NO_NORMAL_OR_LIGHT_PARAMETER','NONPHYSICAL_POLARITY_INVERSION'],
        'T_order_invariance_note':'Absorption alone can legitimately be order invariant. Legacy has no topology-dependent geometry or scattering; zero difference alone is not a universal physical failure.'}
    for name,img in [('plain_R',a),('plain_T',b),('twill31_R',c),('twill31_T',d)]:
        cv2.imwrite(str(out/(name+'_native600.png')),img[:,3700:4300])
    np.savez_compressed(out/'profiles.npz',R=a[300,2100:5900,0],T=b[300,2100:5900,0])
    (out/'audit.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
    return result

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);audit(p.parse_args().out)
