"""Verify all inputs/outputs and attach crop provenance; no inference changes."""
import argparse
import datetime
import platform
from pathlib import Path
import subprocess
import numpy as np
from PIL import Image
from .common import ROOT,read_json,save_json,sha


def verify(out):
    data=read_json(out/'inputs.json');expected={}
    for row in data['pairs']:
        for key in ('front','back'):expected[row[key]]=row[key+'_sha256']
    for row in data['fabricnet']:expected[row['image']]=row['sha256']
    expected[data['attachment']]=data['attachment_sha256'];expected[data['model']]=data['model_sha256']
    expected[data['fabricnet_workbook']]=data['fabricnet_workbook_sha256']
    teacher=read_json(out/'teacher_execution.json');paired={r['id']:r for r in teacher['rows']}
    for name,side in (('fl01.png','front'),('bl01.png','back')):
        expected[str(Path(data['demo_root'])/'external/upstream/example/orig_fabric'/name)]=paired['AUTHOR']['source_'+side+'_sha256']
    predictions=read_json(out/'experiment3_predictions.json')['rows'];expected_ids={r['id'] for r in data['fabricnet']}|{'PHONE_ATTACHMENT'}
    for row in read_json(ROOT/'datasets/user_contributed/2026-10-13-six-fabric-images/image_provenance.json')['images']:
        p=ROOT/'datasets/user_contributed/2026-10-13-six-fabric-images'/row['original'];expected[str(p)]=row['original_sha256'];expected_ids.add(row['sample_id'])
    expected_ids|={'PAIRED_'+r['id'] for r in teacher['rows']}
    assert {r['id'] for r in predictions}==expected_ids and len(predictions)==len(expected_ids)==176
    for ident in ('U20261013_01','U20261013_03','U20261013_06'):
        prior=read_json(out/'experiment2'/f'{ident}_assignment.json')
        expected[str(ROOT/'datasets/physical_evidence_labels/manual_image_reviews'/f'{ident}.json')]=prior['review_sha256']
    verified=[]
    for p,digest in expected.items():
        actual=sha(p);assert actual.lower()==digest.lower(),p
        verified.append({'path':p,'sha256':actual})
    artifacts=[]
    for row in predictions:
        folder=out/'experiment3'/row['id'];record=read_json(folder/'evidence.json');z=np.load(folder/'evidence.npz')
        assert record['summary']==row['summary'],row['id']
        assert np.array_equal(z['sparse_matrix'],np.asarray(record['matrix']).reshape(z['sparse_matrix'].shape)),row['id']
        assert int((z['sparse_matrix']>=0).sum())==record['summary']['weave']['observed_cells']
        assert record['summary']['warp_per_cm'] is None and record['summary']['weft_per_cm'] is None
        for file in ('original','segmentation','yarns','spacing','crossings','matrix','panel'):
            p=folder/(file+'.png')
            with Image.open(p) as im:im.verify()
        if row['source']=='paired_FCN':
            t=paired[row['id'].removeprefix('PAIRED_')]
            provenance={'coordinate_space':'native center crop','crop_original_xyxy':t['crop_original_xyxy'],
                'source_front_sha256':t['source_front_sha256'],'source_back_sha256':t['source_back_sha256'],
                'source_lookup':'inputs.json pairs and teacher_execution.json; AUTHOR under demo example/orig_fabric'}
        else:provenance={k:row[k] for k in ('image','sha256','crop_original_xyxy','domain','source')}
        record['provenance']=provenance;save_json(folder/'evidence.json',record)
        artifacts.append({'id':row['id'],'evidence_sha256':sha(folder/'evidence.json'),'npz_sha256':sha(folder/'evidence.npz')})
    splits={name:{r['fabric_id'] for r in data['pairs'] if r['split']==name} for name in ('train','validation','test')}
    assert not(splits['train']&splits['test'] or splits['validation']&splits['test'] or splits['train']&splits['validation'])
    train=read_json(out/'student_training.json')
    assert train['train_ids']==[r['id'] for r in data['pairs'] if r['split']=='train']
    assert len(read_json(out/'teacher_controls.json')['rows'])==8
    testlog=(out/'mechanics_test.log').read_text(encoding='utf-8-sig');assert '10 passed' in testlog
    tracked=subprocess.check_output(['git','diff','--name-only'],cwd=ROOT,text=True).strip()
    staged=subprocess.check_output(['git','diff','--cached','--name-only'],cwd=ROOT,text=True).strip()
    assert not tracked and not staged,'Existing tracked code changed during experiment'
    checks=['All 176 expected predictions present exactly once','Every source hash matches its initial manifest',
            'All 1232 experiment3 PNGs decode','JSON and NPZ sparse matrices agree, including unknown cells',
            'Every physical roots/cm field stays null','Training/validation/test Textile IDs are disjoint',
            '10 mechanics tests passed','8 fresh teacher stability-control records present',
            'No pre-existing tracked worktree or index changes','Every evidence JSON includes source/crop provenance']
    save_json(out/'verification.json',{'timestamp':datetime.datetime.now().astimezone().isoformat(),'checks':[{'name':c,'status':'PASS'} for c in checks],
        'verified_source_count':len(verified),'source_hashes':verified,'artifacts':artifacts,
        'code_hashes':{str(p.relative_to(ROOT)):sha(p) for p in sorted((ROOT/'benchmark/yarn_graph_experiments').glob('*')) if p.is_file()},
        'python':platform.python_version(),'platform':platform.platform(),'git_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'physical_accuracy_verified':False,'phone_station_certification_executed':False})
    print({'checks':len(checks),'verified_sources':len(verified),'predictions':len(artifacts),'physical_accuracy_verified':False})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);verify(p.parse_args().out)
