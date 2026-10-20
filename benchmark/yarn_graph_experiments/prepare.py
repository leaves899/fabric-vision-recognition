"""Run with bundled Python/openpyxl. Read-only sources, new experiment folder."""
import argparse
import collections
from pathlib import Path

import openpyxl

from .common import ROOT, read_json, save_json, sha


def prepare(out, demo, fabric, attachment):
    out.mkdir(parents=True,exist_ok=False)
    manifest=read_json(demo/'datasets/OLP/PER_TEXTILE_MANIFEST.json')
    pairs=[]
    for i in range(1,39):
        entries=[x for x in manifest['files'] if x['path'].split('/')[1]==f'Textile_{i}']
        front=next(x for x in entries if '_fl' in Path(x['path']).name)
        back=next(x for x in entries if '_bl' in Path(x['path']).name)
        for x in (front,back):
            if sha(demo/'datasets/OLP'/x['path'])!=x['sha256']:raise ValueError('OLP hash mismatch')
        split='test' if i%5==0 else 'validation' if i%5==1 else 'train'
        pairs.append({'id':f'OLP_{i:02d}','fabric_id':f'OLP_Textile_{i}','split':split,
            'front':str(demo/'datasets/OLP'/front['path']),'back':str(demo/'datasets/OLP'/back['path']),
            'front_sha256':front['sha256'],'back_sha256':back['sha256'],'pixel_gt':False,'weave_gt':None})
    book=fabric/'FabricNet_parameters.xlsx'
    wb=openpyxl.load_workbook(book,read_only=True,data_only=True)
    ws=wb['parameters']; rows=list(ws.iter_rows(values_only=True));wb.close()
    if list(rows[0])!=['Image id','Specific Mass','Warp','Weft','Texture']:raise ValueError('Unexpected workbook schema')
    fabrics=[]
    for row_number,(ident,mass,warp,weft,texture) in enumerate(rows[1:],2):
        path=fabric/f'W{int(ident):03d}.jpg'
        fabrics.append({'id':path.stem,'image':str(path),'sha256':sha(path),'capture':'MICROSCOPIC',
            'source_sheet':'parameters','source_row':row_number,'coarse_weave_label':texture,
            'subtype_label':None,'specific_mass_raw':mass,'warp_raw':warp,'weft_raw':weft,
            'density_units_verified':False,'physical_scale_confirmed':False,
            'split':'external_evaluation_only','pixel_gt':False,
            'possible_fabric_group_NOT_verified':'|'.join(map(str,[mass,warp,weft,texture]))})
    data={'pairs':pairs,'fabricnet':fabrics,'fabricnet_workbook':str(book),'fabricnet_workbook_sha256':sha(book),
          'attachment':str(attachment),'attachment_sha256':sha(attachment),'demo_root':str(demo),
          'model':str(demo/'external/upstream/example/net.h5'),'model_sha256':sha(demo/'external/upstream/example/net.h5')}
    save_json(out/'inputs.json',data)
    protocol={'version':'2026-10-16-first-round-1','frozen_before_inference':True,'seed':20261016,
        'native_crop_side':640,'split_counts':dict(collections.Counter(x['split'] for x in pairs)),
        'fabricnet_label_counts':dict(collections.Counter(x['coarse_weave_label'] for x in fabrics)),
        'experiment1':{'teacher':'original six-channel paired FCN, probabilities retained',
          'student':'three-channel small U-Net, distillation from TRAIN fabric IDs only',
          'selection':'best validation soft-target loss, 12 epochs x 40 batches, no test selection',
          'metrics':'teacher agreement, resolved coverage, independent image rotations; NO pixel accuracy GT',
          'negative_control':'single-image multiscale Hessian orientation candidates'},
        'experiment2':{'fixed_inputs':'existing PHONE_IMAGE_OPERATOR_REVIEW short lines, DRAFT; not exact masks',
          'methods':['axis_nearest','local_tangent','local_tangent_with_competing_assignment'],
          'relation_use':'posthoc evaluation only; absent SAME is NOT a negative; different connected groups are NOT automatically different yarns',
          'scope':'01/03 SAME relations, 06 no SAME -> unscorable identity'},
        'experiment3':{'input':'FabricNET all 130 center crops, no label input to reconstruction',
          'templates':['plain','2/1 both slopes','3/1 both slopes','2/2 both slopes','5-harness satin'],
          'coarse_labels':'posthoc only; no subtype accuracy; no density conversion from Warp/Weft fields',
          'matrix_observation':'only geometrical intersections that fall on image-supported visible region; uncertain cells stay unknown'},
        'decisions':{'confidence':.65,'margin':.20,'neighbor_turn_deg':30,'max_gap_over_fragment_length':4,
          'max_side_offset_over_fragment_length':.6,'weave_min_rows_cols':6,'weave_min_cells':36,
          'weave_max_mismatch':.20,'weave_min_runnerup_margin':.08},
        'untouched_sources':['frozen V4','existing benchmark modules','TDD demo','FabricNET','operator JSON'],
        'limits':['No independent pixel masks currently supplied','Same phone labels are weak observations',
                  'FabricNET microscope results do not establish ordinary phone performance',
                  'Teacher predictions are pseudo-labels, not truth; teacher training overlap with OLP unknown']}
    save_json(out/'protocol.json',protocol)
    print({'out':str(out),'pairs':len(pairs),'fabricnet':len(fabrics),'split':protocol['split_counts']})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--demo',type=Path,required=True)
    p.add_argument('--fabric',type=Path,required=True);p.add_argument('--attachment',type=Path,required=True)
    a=p.parse_args();prepare(a.out,a.demo,a.fabric,a.attachment)
