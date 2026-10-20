from pathlib import Path
import sys
import cv2
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine.twill import analyze_twill
labels6=['P1','P2','P3','P4','T1','P5','P6','P7','T2','T3','BT','P8','TP1','T4','TP2','T5','P9','P10','P11','P12']
labels7=['P13','P14','P15','P16','P17','T6','T7','T8']
with open('tmp/paper_twill_results.txt','w') as out:
 for page,labels in [(6,labels6),(7,labels7)]:
  for idx,label in enumerate(labels):
   row,col=divmod(idx,4); path=Path('tmp/paper_samples')/f'p{page}_{row}_{col}.jpg'; image=cv2.imread(str(path)); result=analyze_twill(image,90.0,0.0); out.write('\t'.join(str(x) for x in (label,result.get('status'),result.get('candidate_direction'),result.get('candidate_angle_deg'),result.get('dominance'),result.get('scale_consensus'),result.get('reasons')))+'\n'); out.flush()
