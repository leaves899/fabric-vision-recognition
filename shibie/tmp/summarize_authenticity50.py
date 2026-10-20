import json
from pathlib import Path
from openpyxl import load_workbook

root = Path(__file__).resolve().parent.parent
payload = json.loads((root/'tmp/quality_selected_authenticity50.json').read_text(encoding='utf-8'))
sheet = load_workbook(root/'tmp/fabricnet/FabricNet_parameters.xlsx', read_only=True, data_only=True).active
refs = {f'W{int(r[0]):03d}': (float(r[2]), float(r[3])) for r in list(sheet.values)[1:] if r[0] is not None}
rows=[]
for item in payload['samples']:
    m=item['measurement']; key=Path(item['image']).stem; rw,rf=refs.get(key,(None,None))
    dbg=m.get('density_debug',{})
    def d(direction, field):
        bucket = dbg.get(direction,{})
        value = bucket.get('centerline',{}).get(field)
        if isinstance(value, dict):
            value = value.get(field)
        if isinstance(value,str) and '=' in value:
            for part in value.strip('@{}').split(';'):
                if part.startswith(field+'='): value=part.split('=',1)[1]; break
        try:return float(value)
        except:return None
    rows.append({'image':item['image'],'texture':item.get('fabricnet_texture'),'ref_warp':rw,'ref_weft':rf,'warp':m.get('warp_density_per_cm'),'weft':m.get('weft_density_per_cm'),'warp_delta':m.get('warp_density_per_cm')-rw if rw else None,'weft_delta':m.get('weft_density_per_cm')-rf if rf else None,'status':m.get('status'),'warp_cv':d('warp','spacing_cv'),'weft_cv':d('weft','spacing_cv'),'warp_count':d('warp','valid_centerline_count'),'weft_count':d('weft','valid_centerline_count')})
(root/'tmp/quality_selected_authenticity50_summary.json').write_text(json.dumps({'count':50,'rows':rows},ensure_ascii=False,indent=2),encoding='utf-8')
for r in rows: print(f"{r['image']} | ref {r['ref_warp']:.0f}/{r['ref_weft']:.0f} | out {r['warp']:.3f}/{r['weft']:.3f} | delta {r['warp_delta']:.3f}/{r['weft_delta']:.3f} | cv {r['warp_cv']}/{r['weft_cv']} | {r['status']}")
print('warp_high',sum(r['warp_delta']>0 for r in rows),'weft_high',sum(r['weft_delta']>0 for r in rows),'pass',sum(r['status']=='PASS' for r in rows))
print('mean_abs_delta',sum(abs(r['warp_delta']) for r in rows)/50,sum(abs(r['weft_delta']) for r in rows)/50)
