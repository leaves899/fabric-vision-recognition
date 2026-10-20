"""Fresh paired-model rotation and registration-perturbation diagnostics (not GT)."""
import argparse
import os
from pathlib import Path
os.environ.setdefault('CUDA_VISIBLE_DEVICES','-1')
os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL','2')
import numpy as np
import tensorflow as tf
from .common import center_crop,decision,pixel_agreement,read_json,read_rgb,save_json,sha


def run(out):
    tf.config.threading.set_intra_op_parallelism_threads(4);tf.config.threading.set_inter_op_parallelism_threads(2)
    d=read_json(out/'inputs.json');model=tf.keras.models.load_model(d['model'],compile=False)
    def infer(f,b):
        x=np.concatenate([f[...,::-1],b[...,::-1]],-1)
        x=np.pad(x,((40,40),(40,40),(0,0)),mode='symmetric').astype(np.float32)/255
        return model(x[None],training=False).numpy()[0,40:-40,40:-40]
    items=[r for r in d['pairs'] if r['split']=='test']+[{'id':'AUTHOR','front':str(Path(d['demo_root'])/'external/upstream/example/orig_fabric/fl01.png'),
                                                          'back':str(Path(d['demo_root'])/'external/upstream/example/orig_fabric/bl01.png')}]
    rows=[]
    for row in items:
        f,_=center_crop(read_rgb(row['front']));b,_=center_crop(read_rgb(row['back']));ref=decision(np.load(out/'paired'/f"{row['id']}.npz")['teacher_probs'].astype(np.float32))
        tests=[]
        for k in (1,2,3):
            q=infer(np.rot90(f,k),np.rot90(b,k));q=np.rot90(q,-k)
            if k%2:q=q[...,[2,1,0]]
            tests.append({'test':'ROTATION','ccw_degrees':90*k,'mapped_vs_original':pixel_agreement(decision(q),ref)})
        if row['id']=='AUTHOR':
            for shift in (1,3,6):
                shifted=np.pad(b,((0,0),(shift,0),(0,0)),mode='edge')[:,:b.shape[1]]
                q=infer(f,shifted)
                tests.append({'test':'BACK_IMAGE_X_SHIFT','pixels':shift,'mapped_vs_original':pixel_agreement(decision(q)[8:-8,8:-8],ref[8:-8,8:-8])})
        rows.append({'id':row['id'],'tests':tests});save_json(out/'teacher_controls.json',{'model_sha256':sha(d['model']),'fresh_inference':True,
              'accuracy_against_truth':None,'note':'Repeatability and perturbation only; agreement may be wrong in both runs','rows':rows})
        print(row['id'],'controls complete',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);run(p.parse_args().out)
