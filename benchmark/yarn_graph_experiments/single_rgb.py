"""Single-RGB student; paired FCN outputs are pseudo-labels, never ground truth."""
from __future__ import annotations
import argparse
import time
from pathlib import Path

import cv2
import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

from .common import PALETTE, decision, panel, pixel_agreement, read_json, save_json, sha


class SmallUNet(nn.Module):
    def __init__(self):
        super().__init__()
        def block(a,b):
            return nn.Sequential(nn.Conv2d(a,b,3,padding=1),nn.GroupNorm(4,b),nn.SiLU(),
                                 nn.Conv2d(b,b,3,padding=1),nn.GroupNorm(4,b),nn.SiLU())
        self.e1=block(3,16);self.e2=block(16,32);self.e3=block(32,64)
        self.d2=block(96,32);self.d1=block(48,16);self.head=nn.Conv2d(16,3,1)
    def forward(self,x):
        a=self.e1(x);b=self.e2(F.avg_pool2d(a,2));c=self.e3(F.avg_pool2d(b,2))
        d=self.d2(torch.cat([F.interpolate(c,size=b.shape[-2:],mode='bilinear',align_corners=False),b],1))
        return self.head(self.d1(torch.cat([F.interpolate(d,size=a.shape[-2:],mode='bilinear',align_corners=False),a],1)))


def structure_proxy(rgb):
    """Image-gradient orientation control, explicitly not a physical float segmenter."""
    gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY).astype(np.float32)/255
    gx=cv2.Sobel(gray,cv2.CV_32F,1,0);gy=cv2.Sobel(gray,cv2.CV_32F,0,1)
    xx=cv2.GaussianBlur(gx*gx,(0,0),3);yy=cv2.GaussianBlur(gy*gy,(0,0),3)
    xy=cv2.GaussianBlur(gx*gy,(0,0),3)
    energy=xx+yy;coherence=np.sqrt((xx-yy)**2+4*xy**2)/(energy+1e-7)
    # Dominant normal x => vertically extended image feature.
    result=np.where(xx>=yy,0,2).astype(np.uint8)
    result[(coherence<.45)|(energy<max(float(np.quantile(energy,.45)),1e-5))]=3
    return result


def predict(model,rgb):
    with torch.inference_mode():
        x=torch.from_numpy(np.ascontiguousarray(rgb.transpose(2,0,1))).float()[None]/255
        return model(x).softmax(1)[0].permute(1,2,0).numpy()


def load_student(out):
    torch.set_num_threads(8)
    m=SmallUNet();m.load_state_dict(torch.load(Path(out)/'student.pt',map_location='cpu',weights_only=True));m.eval()
    return m


def train(out):
    torch.set_num_threads(8);torch.manual_seed(20261016);np.random.seed(20261016)
    data=read_json(out/'inputs.json');rng=np.random.default_rng(20261016)
    def load(split):
        return [(r['id'],dict(np.load(out/'paired'/(r['id']+'.npz')))) for r in data['pairs'] if r['split']==split]
    training=load('train');validation=load('validation')
    model=SmallUNet();optimizer=torch.optim.AdamW(model.parameters(),lr=.002,weight_decay=1e-4)
    # Computed from TRAIN pseudo-labels only. No TEST/FabricNET labels are read here.
    freq=np.mean([a['teacher_probs'].astype(np.float32).mean((0,1)) for _,a in training],0)
    weights=torch.tensor(1/np.sqrt(freq+.01));weights/=weights.mean()
    def loss(logits,target):
        conf=target.max(1).values
        valid=(conf>=.55).float()
        values=-(target*F.log_softmax(logits,1)*weights[None,:,None,None]).sum(1)
        return (values*valid).sum()/valid.sum().clamp_min(1)
    history=[];best=float('inf');started=time.perf_counter()
    for epoch in range(12):
        model.train();losses=[]
        for step in range(40):
            xx=[];yy=[]
            for _ in range(4):
                _,item=training[int(rng.integers(len(training)))];h,w=item['rgb'].shape[:2];size=192
                y=int(rng.integers(h-size+1));x=int(rng.integers(w-size+1))
                rgb=item['rgb'][y:y+size,x:x+size].astype(np.float32)/255
                target=item['teacher_probs'][y:y+size,x:x+size].astype(np.float32)
                k=int(rng.integers(4));rgb=np.rot90(rgb,k);target=np.rot90(target,k)
                if k%2:target=target[...,[2,1,0]]
                if rng.random()<.5:rgb=rgb[:,::-1];target=target[:,::-1]
                rgb=np.clip(rgb*rng.uniform(.8,1.2)+rng.uniform(-.05,.05),0,1)
                xx.append(rgb.transpose(2,0,1));yy.append(target.transpose(2,0,1))
            x=torch.from_numpy(np.ascontiguousarray(xx));target=torch.from_numpy(np.ascontiguousarray(yy))
            optimizer.zero_grad();v=loss(model(x),target);v.backward();optimizer.step();losses.append(float(v.detach()))
        model.eval();vl=[]
        with torch.inference_mode():
            for _,item in validation:
                # Same fixed center validation patch each epoch.
                rgb=item['rgb'][192:448,192:448];target=item['teacher_probs'][192:448,192:448]
                x=torch.from_numpy(np.ascontiguousarray(rgb.transpose(2,0,1))).float()[None]/255
                y=torch.from_numpy(np.ascontiguousarray(target.transpose(2,0,1))).float()[None]
                vl.append(float(loss(model(x),y)))
        row={'epoch':epoch+1,'training_loss':float(np.mean(losses)),'validation_pseudo_label_loss':float(np.mean(vl))}
        if row['validation_pseudo_label_loss']<best:
            best=row['validation_pseudo_label_loss'];torch.save(model.state_dict(),out/'student.pt');best_epoch=epoch+1
        history.append(row);print(row,flush=True)
        save_json(out/'student_training.json',{'history':history,'best_epoch':best_epoch,'train_ids':[i for i,_ in training],
          'validation_ids':[i for i,_ in validation],'test_used_for_selection':False,'rgb_channels':3,
          'targets':'PAIRED_MODEL_SOFT_PSEUDOLABELS_NOT_GT','parameter_count':sum(p.numel() for p in model.parameters()),
          'seconds':time.perf_counter()-started,'seed':20261016,'class_weights':weights.numpy()})
    save_json(out/'student_model_manifest.json',{'sha256':sha(out/'student.pt'),'architecture':'SmallUNet-16-32-64',
      'source_model':data['model_sha256'],'trained_this_run':True,'physical_accuracy_validated':False})
    evaluate(out)


def evaluate(out):
    model=load_student(out);data=read_json(out/'inputs.json');rows=[]
    evals=[r for r in data['pairs'] if r['split'] in ('validation','test')]+[{'id':'AUTHOR','split':'reference_only'}]
    for row in evals:
        d=np.load(out/'paired'/(row['id']+'.npz'));rgb=d['rgb'];ref=decision(d['teacher_probs'].astype(np.float32))
        probs=predict(model,rgb);pred=decision(probs);proxy=structure_proxy(rgb)
        metrics={'id':row['id'],'split':row['split'],'student_vs_paired_teacher':pixel_agreement(pred,ref),
                 'structure_proxy_vs_paired_teacher':pixel_agreement(proxy,ref),'physical_segmentation_accuracy':None}
        if row['split'] in ('test','reference_only'):
            rotations=[]
            for k in (1,2,3):
                q=predict(model,np.rot90(rgb,k));q=np.rot90(q,-k)
                if k%2:q=q[...,[2,1,0]]
                rotations.append({'ccw_degrees':k*90,'mapped_prediction_vs_original':pixel_agreement(decision(q),pred)})
            metrics['independent_student_rotation_runs']=rotations
            panel(out/'experiment1'/(row['id']+'.png'),[rgb,PALETTE[ref],PALETTE[pred],PALETTE[proxy]],
                  ['Native RGB','Paired teacher (not GT)','RGB student (candidates)','Gradient control (not yarns)'],420)
        rows.append(metrics)
    save_json(out/'experiment1.json',{'status':'EXECUTED_PSEUDOLABEL_COMPARISON','fresh_student_inference':True,
      'physical_pixel_accuracy':None,'pixel_ground_truth_available':False,'rows':rows})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();train(a.out)
