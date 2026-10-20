from __future__ import annotations
import json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from engine.pipeline import run_measurement
names=['W088.jpg','W004.jpg','W063.jpg','W012.jpg','W014.jpg','W001.jpg','W003.jpg','W100.jpg','W096.jpg','W050.jpg']
selected=json.loads((ROOT/'tmp/quality_selected_050.json').read_text(encoding='utf-8'))['samples']
out=[]
for name in names:
 old=next(x for x in selected if x['image']==name); raw=(ROOT/'tmp/user_samples'/name).read_bytes()
 m=run_measurement(raw,raw,mm_per_px_x=0.0078125,mm_per_px_y=0.0083333,warp_axis_hint='vertical')
 out.append({'image':name,'measurement':m}); print(name,m.get('warp_density_per_cm'),m.get('weft_density_per_cm'),m.get('status'),flush=True)
(ROOT/'tmp/quality_selected_smoothed10_probe.json').write_text(json.dumps({'count':10,'samples':out},ensure_ascii=False,indent=2),encoding='utf-8')
