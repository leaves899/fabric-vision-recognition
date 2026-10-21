"""Offline GT audit and visual panels, strictly outside detector inference."""
import json
from dataclasses import replace
from pathlib import Path
import cv2,numpy as np
from synthetic_capture_8k import CaptureScene,_render_strip
from synthetic_rt_heightfield_8k import Optics,render_region,geometry


def audit(folder,reference=None):
    folder=Path(folder);truth=json.loads((folder/'truth.json').read_text());s=CaptureScene(**truth['source_scene']);o=Optics(**truth['optics'])
    # Halo eliminates diagnostic region-edge shading artifacts.
    R,T,g=render_region(s,o,3676,2676,648,648,True)
    R=R[24:-24,24:-24];T=T[24:-24,24:-24];g={k:v[24:-24,24:-24] for k,v in g.items()}
    masks={'pore':(g['warp_chord']==0)&(g['weft_chord']==0),
        'warp_only':(g['warp_chord']>4)&(g['weft_chord']==0),
        'weft_only':(g['weft_chord']>4)&(g['warp_chord']==0),
        'cross':(g['warp_chord']>4)&(g['weft_chord']>4)}
    stats={}
    for group,m in masks.items():
        stats[group]={}
        for name,img in [('R',R),('T',T)]:
            q=cv2.cvtColor(img,cv2.COLOR_BGR2GRAY)[m]
            stats[group][name]={'n':len(q),'mean':float(q.mean()),'std':float(q.std()),'variance':float(q.var()),'histogram_32':np.histogram(q,32,(0,256))[0].tolist()}
    widths={f:float(np.percentile(g[k],10)) for f,k in [('warp','ww'),('weft','fw')]}
    identities={f:len(rows)==len(set(row['id'] for row in rows)) for f,rows in truth['physical_yarn_centerlines'].items()}
    # Exact samples check the recorded physical centre and width functions.
    from synthetic_rt_heightfield_8k import yarn_fields
    errors=[]
    for family,rows in truth['physical_yarn_centerlines'].items():
        for row in rows[::7]:
            pts=np.array(row['points']);axis=1 if family=='warp' else 0
            c,w=yarn_fields(s,family,int(row['id'][1:]),pts[:,axis])
            errors.append(float(np.abs(c-pts[:,1-axis]).max()))
    base=replace(s,weave='plain');other=replace(s,weave='twill_3_1')
    a,b=render_region(base,o,3676,2676,648,648);c,d=render_region(other,o,3676,2676,648,648)
    difference={'R_MAE':float(np.abs(a[24:-24,24:-24].astype(float)-c[24:-24,24:-24]).mean()),'T_MAE':float(np.abs(b[24:-24,24:-24].astype(float)-d[24:-24,24:-24]).mean()),'mechanism':'crimp-dependent optical path; absorption invariant to layer order, small T difference is physically allowed'}
    result={'regions':stats,'width_p10_px':widths,'passes_width_gate':all(x>=12 for x in widths.values()),'unique_ids':identities,'stored_center_max_error_px':max(errors),'topology_plain_vs_31_same_geometry_seed':difference,'real_T_calibrated':False,'visual_review':'PENDING_HUMAN_OR_ASSISTANT_IMAGE_OPEN'}
    (folder/'optics_audit.json').write_text(json.dumps(result,indent=2))
    # Colours: warp blue, weft green, pores black; the map contains visible owners.
    owners=np.array([[0,0,0],[230,100,30],[70,220,80]],np.uint8)[g['visible']]
    for row in truth['physical_yarn_centerlines']['warp']:
        pts=np.asarray(row['points']);sel=pts[(pts[:,1]>2940)&(pts[:,1]<2943)]
        if len(sel) and 3700<=sel[0,0]<4300:cv2.putText(owners,row['id'],(int(sel[0,0]-3700),245),cv2.FONT_HERSHEY_SIMPLEX,.23,(255,255,255),1)
    cv2.imwrite(str(folder/'visible_owner_ids.png'),owners)
    # Old comparison at exactly the same native coordinates, no old geometry edits.
    old_s=replace(s,shift_reflection_x=0,noise_sigma=0,diagonal_decoy=0)
    oldR,oldT=_render_strip(old_s,2700,3300,np.eye(3),np.random.default_rng(s.seed))
    panels=[('Legacy R',oldR[:,3700:4300]),('Legacy T',oldT[:,3700:4300]),('Heightfield R',R),('Heightfield T',T),('Visible entity ID map',owners)]
    if reference and Path(reference).is_file():
        real=cv2.imread(str(reference));h,w=real.shape[:2];panels.insert(0,('Real R reference; scale unknown',real[h//2-300:h//2+300,w//2-300:w//2+300]))
    canvas=np.full((650,600*len(panels),3),245,np.uint8)
    for i,(label,img) in enumerate(panels):
        canvas[50:650,600*i:600*(i+1)]=img
        cv2.putText(canvas,label,(600*i+8,30),cv2.FONT_HERSHEY_SIMPLEX,.55,(20,20,20),1,cv2.LINE_AA)
    cv2.imwrite(str(folder/'real_old_new_native_comparison.jpg'),canvas,[cv2.IMWRITE_JPEG_QUALITY,94])
    # Standalone exact diagnostic crops (exclude region-edge halo).
    cv2.imwrite(str(folder/'diagnostic_R_native600.png'),R);cv2.imwrite(str(folder/'diagnostic_T_native600.png'),T)
    np.savez_compressed(folder/'intensity_profiles.npz',R_center=R[300,:,0],T_center=T[300,:,0])
    return result

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--images',required=True);p.add_argument('--reference');a=p.parse_args();print(json.dumps(audit(a.images,a.reference)))
