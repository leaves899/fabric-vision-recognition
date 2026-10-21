"""Post-inference artifact integrity checks; renderer/GT validation only."""
import hashlib,json
from pathlib import Path
import numpy as np
from PIL import Image

def verify(root,repo,out):
    root=Path(root);repo=Path(repo);results={}
    baseline=json.loads((repo/'experiments/shibie-8k-rt-physical-optics/M0_FREEZE.json').read_text())
    unchanged={p:hashlib.sha256((repo/p).read_bytes()).hexdigest()==h for p,h in baseline['frozen_sha256'].items()}
    assert all(unchanged.values())
    for folder in sorted(root.glob('physical-rt-8k-*')):
        g=json.loads((folder/'truth.json').read_text());r=json.loads((folder/'AB/comparison.json').read_text());a=json.loads((folder/'optics_audit.json').read_text())
        s=g['source_scene'];assert all(s[k]==0 for k in ('rotation_deg','fabric_rotation_deg','perspective'))
        assert g['camera_geometry']['calibration_frame_inside_mm']==[50,50]
        for modality,filename in g['files'].items():
            assert Image.open(folder/filename).size==(8000,6000)
            assert hashlib.sha256((folder/filename).read_bytes()).hexdigest()==g['sha256'][modality]==r['input_hash_sha256'][modality]
        ids=[row['id'] for rows in g['physical_yarn_centerlines'].values() for row in rows]
        assert len(ids)==len(set(ids));assert a['unique_ids']['global']
        assert a['stored_center_max_error_px']<.01
        p10={f:float(np.percentile([w for row in rows for w in row['widths_px']],10)) for f,rows in g['physical_yarn_centerlines'].items()}
        assert min(p10.values())>=12
        assert a['regions']['pore']['T']['mean']>a['regions']['cross']['T']['mean']
        x0,y0,x1,y1=g['camera_geometry']['true_rectification_area_canonical_px']
        for window in r['windows']:
            H=np.linalg.inv(np.asarray(next(w['raw_to_tile'] for w in json.loads((folder/'AB/frozen_predictions_before_GT.json').read_text())['windows'] if w['grid']==window['grid'])))
            corners=np.array([[0,0,1],[519,0,1],[519,519,1],[0,519,1]])@H.T
            xy=corners[:,:2]/corners[:,2:]
            assert np.all((xy[:,0]>x0)&(xy[:,0]<x1)&(xy[:,1]>y0)&(xy[:,1]<y1))
        assert len(r['windows'])==9
        results[r['case']]={'native_dimensions':True,'hashes_match_frozen_inference':True,'zero_rotation':True,'frame_50mm_and_all_AB_windows_inside':True,'global_unique_IDs':len(ids),'P10_from_all_recorded_width_samples_px':p10,'center_coordinate_error_px':a['stored_center_max_error_px'],'pore_cross_T_order':True}
    assert len(results)==5
    result={'baseline_unchanged':unchanged,'five_scenes':results,'integrity_status':'PASS','photo_realism_acceptance':'FAIL_REQUIRES_MORE_WORK','real_T_calibration':'NOT_AVAILABLE','physical_ID_tracking_accuracy':'NOT_EVALUATED','RK3576_validation':'NOT_RUN'}
    Path(out).write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--artifacts',required=True);p.add_argument('--repo',default='.');p.add_argument('--out',required=True);a=p.parse_args();verify(a.artifacts,a.repo,a.out)
