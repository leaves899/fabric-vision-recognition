"""Fresh paired FCN inference with original weights. Run in TDD TF environment."""
import argparse
import os
import time
from pathlib import Path

os.environ.setdefault('CUDA_VISIBLE_DEVICES','-1')
os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL','2')
import numpy as np
import tensorflow as tf
from PIL import Image

from .common import center_crop, decision, panel, PALETTE, read_json, read_rgb, save_json, sha


def run(out):
    tf.config.threading.set_intra_op_parallelism_threads(8)
    tf.config.threading.set_inter_op_parallelism_threads(2)
    data=read_json(out/'inputs.json')
    if sha(data['model'])!=data['model_sha256']:raise ValueError('Model changed')
    model=tf.keras.models.load_model(data['model'],compile=False)
    pairs=data['pairs']+[{'id':'AUTHOR','split':'reference_only',
        'front':str(Path(data['demo_root'])/'external/upstream/example/orig_fabric/fl01.png'),
        'back':str(Path(data['demo_root'])/'external/upstream/example/orig_fabric/bl01.png')}]
    target=out/'paired';target.mkdir(exist_ok=False)
    rows=[]
    for row in pairs:
        started=time.perf_counter()
        f,box=center_crop(read_rgb(row['front']));b,box_b=center_crop(read_rgb(row['back']))
        if box!=box_b or f.shape!=b.shape:raise ValueError('Pair geometry mismatch')
        # Match author's OpenCV BGR input, symmetric 40px context, and /255.
        x=np.concatenate([f[...,::-1],b[...,::-1]],axis=-1)
        x=np.pad(x,((40,40),(40,40),(0,0)),mode='symmetric').astype(np.float32)/255
        probs=model(x[None],training=False).numpy()[0,40:-40,40:-40]
        np.savez_compressed(target/(row['id']+'.npz'),rgb=f,teacher_probs=probs.astype(np.float16))
        dec=decision(probs)
        record={'id':row['id'],'split':row['split'],'crop_original_xyxy':box,'source_front_sha256':sha(row['front']),
            'source_back_sha256':sha(row['back']),'softmax_sum_max_error':float(abs(probs.sum(-1)-1).max()),
            'resolved_fraction':float((dec!=3).mean()),'class_fraction':[float((dec==i).mean()) for i in range(4)],
            'seconds':time.perf_counter()-started,'fresh_inference':True,
            'npz_sha256':sha(target/(row['id']+'.npz'))}
        rows.append(record)
        if row['split'] in ('test','reference_only'):
            panel(target/(row['id']+'_teacher.png'),[f,b,PALETTE[dec]],['Reflected RGB','Transmitted RGB','Paired FCN candidates'])
        print(row['id'],round(record['seconds'],2),record['class_fraction'],flush=True)
        save_json(out/'teacher_execution.json',{'model_sha256':data['model_sha256'],'tensorflow':tf.__version__,
          'class_order':['vertical_float','background','horizontal_float'],'rows':rows,'physical_accuracy':None})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);run(p.parse_args().out)
