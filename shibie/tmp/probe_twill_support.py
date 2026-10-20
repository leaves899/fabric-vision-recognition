from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import cv2, numpy as np
from engine.pipeline import run_measurement
from engine.preprocess import center_crop, local_normalize, resize_max_side, to_gray
from engine.twill import _extract_diagonal_segments, _gabor_band_candidates, _dominant_orientation, _angular_distance
from engine.config import DEFAULT_CONFIG
for n in [3,6,8,9,11,13,21,27,28,30,31,32,33,35,39]:
 name=f'W{n:03d}.jpg'; raw=(Path('tmp/user_samples')/name).read_bytes(); out=run_measurement(raw,raw,mm_per_px_x=.0078125,mm_per_px_y=.0083333,warp_axis_hint='vertical'); wd=out['orientation']['warp_direction_deg'];fd=out['orientation']['weft_direction_deg'];img=cv2.imdecode(np.frombuffer(raw,np.uint8),1);gray,_=resize_max_side(center_crop(to_gray(img),.86),DEFAULT_CONFIG.twill_max_side); norm=local_normalize(gray); bands=_gabor_band_candidates(norm,wd,fd,DEFAULT_CONFIG)
 if not bands: print(n,'none',flush=True); continue
 _,l,a=_extract_diagonal_segments(norm,wd,fd,DEFAULT_CONFIG); sel=_angular_distance(a,bands[0]['image_line_angle_deg'])<=DEFAULT_CONFIG.twill_direction_tolerance_deg
 if not np.any(sel): print(n,'no seg',flush=True); continue
 angle,_,_= _dominant_orientation(a[sel],l[sel]); gd=float(np.sum(l[_angular_distance(a,angle)<=12.5])/np.sum(l)); print(n,out['twill']['status'],round(gd,3),round(bands[0]['direction_field_coverage'],3),flush=True)
