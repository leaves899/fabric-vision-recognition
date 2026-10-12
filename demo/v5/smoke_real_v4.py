"""Run real V4 through /api/analyze once with simulated click coordinates.

SMOKE ONLY: The points here are geometry test input, NOT confirmed real-yarn annotation.
"""
from pathlib import Path
import json,base64,time
from fastapi.testclient import TestClient
from server import app
ROOT=Path(__file__).resolve().parent
img=ROOT/'samples/无标定框_示例.jpg'
OUT=ROOT/'outputs'
OUT.mkdir(exist_ok=True)
client=TestClient(app)
start=time.time()
with img.open('rb') as fh:
    res=client.post('/api/analyze',files={'image':(img.name,fh,'image/jpeg')},data={
        'reference_points':'[[600,850],[850,795]]','confirm_reference':'true'})
print('status',res.status_code,'elapsed',round(time.time()-start,1),'sec',flush=True)
if res.status_code!=200:
    print(res.text[:3000],flush=True)
    raise SystemExit(2)
obj=res.json()
(OUT/'v5_smoke_result.json').write_text(json.dumps(obj['result'],indent=2,ensure_ascii=False),encoding='utf-8')
(OUT/'v5_smoke_three_panel.jpg').write_bytes(base64.b64decode(obj['visuals']['three_panel'].split(',')[1]))
print('rotation',obj['result']['manual_yarn_reference']['v4_adapter_rotation_deg'],flush=True)
print('candidate counts',obj['result']['v4']['family_a_candidate_lines'],obj['result']['v4']['family_b_candidate_lines'],flush=True)
print('smoke points are simulated, not actual confirmed physical yarn',flush=True)
