"""Diagnostic ablation only. Duplicating T is NOT independent RT validation."""
import json
from pathlib import Path
import cv2,numpy as np
from engine.multiwindow_pitch import detect_calibration_frame,frame_windows,PitchSettings,analyze_pitch_window
from engine.local_axis_rectification import adjusted_window_homography
from engine.subpixel_physical_phase import validate_centers_fractional

def diagnose(folder,out):
    folder=Path(folder);R=cv2.imread(str(folder/'reflection_8000x6000.jpg'));T=cv2.imread(str(folder/'transmission_8000x6000.jpg'))
    frame=detect_calibration_frame(R);rows=[]
    for i,j,H0 in frame_windows(frame,3,640):
        H=adjusted_window_homography(H0,0,640,520);r=cv2.warpPerspective(R,H,(520,520));t=cv2.warpPerspective(T,H,(520,520))
        props=analyze_pitch_window(r,t,PitchSettings());row={'grid':[i,j],'families':{}}
        for family in ('warp','weft'):
            pitch=props[family]['candidates'][0]['pitch_px'] if props[family]['candidates'] else None
            checks={}
            for tag,a,b in [('RT',r,t),('TT_DUPLICATED_DIAGNOSTIC',t,t),('RR_DUPLICATED_DIAGNOSTIC',r,r)]:
                q=validate_centers_fractional(a,b,family,pitch)
                checks[tag]={k:v for k,v in q.items() if k not in ('center_positions_px','phase_candidates','subpixel_period')}
            row['families'][family]=checks
        rows.append(row)
    result={'image_only_no_GT':True,'diagnostic_not_new_method':True,'warning':'TT and RR duplicate the same source; cannot count as two independent physical observations or production acceptance',
        'windows':rows,'pass_windows':{fam:{tag:sum(w['families'][fam][tag]['status']=='PASS' for w in rows) for tag in ('RT','TT_DUPLICATED_DIAGNOSTIC','RR_DUPLICATED_DIAGNOSTIC')} for fam in ('warp','weft')}}
    Path(out).write_text(json.dumps(result,indent=2));print(result['pass_windows'])
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--images',required=True);p.add_argument('--out',required=True);a=p.parse_args();diagnose(a.images,a.out)
