"""Compare unchanged V5 to G1 on PR16 photos; local labels are held-out diagnostics."""
from __future__ import annotations
import argparse, hashlib, json, shutil, sys
from pathlib import Path
import cv2
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'demo/v5'))
from v4_adapter import run_v4
from v51_refinement import refine_v5_candidates
from benchmark.manual_annotation import validate_annotation
from benchmark.v5_pr16_local_evidence_audit import run as audit

def evaluate(sample_id, baseline_dir, out_dir):
    out_dir.mkdir(parents=True,exist_ok=True)
    record=json.loads((baseline_dir/'v5_result.json').read_text(encoding='utf-8'))
    original=record['result']
    meta=record['original_image_provenance']
    ann_path=ROOT/'datasets/annotations/drafts'/(sample_id+'.json')
    ann=validate_annotation(ROOT,json.loads(ann_path.read_text(encoding='utf-8')))
    source=(ROOT/ann['image_path']).read_bytes()
    if hashlib.sha256(source).hexdigest()!=meta['original_image_sha256']:
        raise ValueError('stale source image compared to original V5 baseline')
    image=cv2.imdecode(np.frombuffer(source,np.uint8),cv2.IMREAD_COLOR)
    x0,y0,x1,y1=meta['crop_xyxy_original_px']
    crop=image[y0:y1,x0:x1].copy()
    if [crop.shape[1],crop.shape[0]]!=meta['cropped_pixel_size_px']:
        raise ValueError('source photo crop mismatch')
    angle=original['direction_evidence']['v4_adapter_rotation_deg']
    v4=run_v4(crop,float(angle))
    refined=refine_v5_candidates(crop,v4)
    if len(refined['first'])!=len(v4['first']) or len(refined['second'])!=len(v4['second']):
        raise AssertionError('G1 lost, added or merged a V4 candidate')
    # Both audits use exactly the same PR16 DRAFT label set; label data has
    # never been passed to refine_v5_candidates.
    if not (baseline_dir/'pr16_local_evidence_v5_audit.json').exists():
        audit(sample_id,baseline_dir)
    base=json.loads((baseline_dir/'pr16_local_evidence_v5_audit.json').read_text(encoding='utf-8'))
    shutil.copy2(baseline_dir/'v5_result.json',out_dir/'v5_result.json')
    synthetic_v4={'first':refined['first'],'second':refined['second']}
    after=audit(sample_id,out_dir,track_override=synthetic_v4)
    keys=('local_strokes_covered_at_least_60pct_within_5px',
          'local_strokes_covered_at_least_60pct_within_10px',
          'local_strokes_covered_at_least_60pct_within_quarter_pitch',
          'local_strokes_covered_at_least_60pct_within_half_pitch')
    def compare(kind):
        old=base[kind];new=after[kind]
        return {'available_draft_strokes':old['parallel_and_inside_roi'],
                'old_median_distance_px':old['median_nearest_track_px'],
                'new_median_distance_px':new['median_nearest_track_px'],
                'old':{x:old[x] for x in keys},
                'new':{x:new[x] for x in keys},
                'delta':{x:new[x]-old[x] for x in keys}}
    old_links=base.get('relations',{})
    new_links=after.get('relations',{})
    # Side-by-side comparisons at same display scale.
    old_img=cv2.imread(str(baseline_dir/'pr16_local_strokes_overlay.jpg'))
    new_img=cv2.imread(str(out_dir/'pr16_local_strokes_overlay.jpg'))
    if old_img is not None and new_img is not None:
        if new_img.shape[:2]!=old_img.shape[:2]:
            new_img=cv2.resize(new_img,(old_img.shape[1],old_img.shape[0]))
        cv2.imwrite(str(out_dir/'v51_g1_v5_side_by_side.jpg'),
                    cv2.hconcat([old_img,new_img]))
    # Preserve the complete candidate trace geometry for visual audits.
    (out_dir/'v51_g1_refined_candidates.json').write_text(json.dumps({
        'schema':'v51-g1-experiment','source_v4_sha256':v4['frozen_sha256'],
        'image_only':True,'manual_label_used_for_localization':False,
        'physical_yarn_identity_verified':False,
        'tracks':{'first':refined['first'],'second':refined['second']},
        'reports':{'A':refined['family_A'],'B':refined['family_B']},
    },ensure_ascii=False),encoding='utf-8')
    report={'sample_id':sample_id,
            'status':'EXPERIMENTAL_G1_LOCAL_CANDIDATE_REFINEMENT_NOT_PHYSICAL_YARN_GT',
            'frozen_v4_sha256':v4['frozen_sha256'],
            'operator_annotations_read_for_evaluation_only':True,
            'v4_and_v5_unchanged':True,
            'A_candidate_count_unchanged':len(v4['first']),
            'B_candidate_count_unchanged':len(v4['second']),
            'A_refinement':{k:v for k,v in refined['family_A'].items() if k!='per_track'},
            'B_refinement':{k:v for k,v in refined['family_B'].items() if k!='per_track'},
            'apparent_yarn':compare('apparent_visible_yarn'),
            'twill':compare('twill_pattern'),
            'operator_same_yarn_relations':{'baseline':old_links,'refined':new_links},
            'cautions':['Operator-drawn whole-yarn references may cross occlusions',
                        'Local photo strokes are DRAFT image-only labels, not physical yarn pixel centerline ground truth',
                        'Absolute 5px/10px thresholds refer to interpolated 2x zoom pixel coordinate space',
                        'Improving nearest-distance alone does not establish unique per-yarn tracking',
                        'Current G1 preserves baseline candidate counts, so it does not solve missing yarn count.']}
    (out_dir/'v51_g1_comparison.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('V51_G1_RESULT_JSON='+json.dumps(report,ensure_ascii=False,sort_keys=True),flush=True)
    return report

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--id',required=True)
    p.add_argument('--baseline-dir',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    baseline=args.baseline_dir if args.baseline_dir.is_absolute() else ROOT/args.baseline_dir
    out=args.out if args.out.is_absolute() else ROOT/args.out
    evaluate(args.id,baseline,out)
if __name__=='__main__':main()
