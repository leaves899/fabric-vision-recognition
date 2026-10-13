"""Synthetic G1 regression contracts, NOT fabric accuracy claims."""
import sys
import unittest
from pathlib import Path
import cv2
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'demo/v5'))
from v51_refinement import refine_family,refine_v5_candidates

def sample():
    h,w,pitch=380,470,27
    xx=np.arange(w)
    yy=np.arange(h)[:,None]
    image=np.ones((h,w),np.float32)*135
    tracks=[]
    for j in range(7):
        center=60+j*pitch
        true=center+6*np.sin(xx/76+.4)
        image+=65*np.exp(-.5*((yy-true[None,:])/4.)**2)
        tracks.append([[float(x),float(center)] for x in np.linspace(20,w-20,200)])
    image=cv2.cvtColor(np.clip(image,0,255).astype(np.uint8),cv2.COLOR_GRAY2BGR)
    return image,tracks,pitch

class TestV51G1(unittest.TestCase):
    def test_curved_stripes_improve_without_changing_ids(self):
        img,tracks,pitch=sample()
        new,report=refine_family(img,tracks,pitch=pitch)
        self.assertEqual(len(new),len(tracks))
        self.assertGreater(report['refined_count'],0)
        for j in range(7):
            arr=np.asarray(new[j])
            truth=60+j*pitch+6*np.sin(arr[:,0]/76+.4)
            old=np.mean(abs(60+j*pitch-truth))
            err=np.mean(abs(arr[:,1]-truth))
            self.assertLess(err,min(1.5,old*.55))
        self.assertTrue(all(np.mean(np.asarray(new[i+1])[:,1])>np.mean(np.asarray(new[i])[:,1])
                            for i in range(6)))

    def test_flat_photo_fails_closed(self):
        img,tracks,pitch=sample()
        blank=np.ones_like(img)*127
        new,report=refine_family(blank,tracks,pitch=pitch)
        self.assertEqual(new,tracks)
        self.assertEqual(report['refined_count'],0)

    def test_rotate_90_degree_equivariance(self):
        img,tracks,pitch=sample()
        rotated=cv2.rotate(img,cv2.ROTATE_90_CLOCKWISE)
        height=img.shape[0]
        rt=[[[height-1-y,x] for x,y in tr] for tr in tracks]
        new,report=refine_family(rotated,rt,pitch=pitch)
        self.assertGreater(report['refined_count'],0)
        for j in range(7):
            p=np.asarray(new[j])
            original_y=height-1-p[:,0]
            truth=60+j*pitch+6*np.sin(p[:,1]/76+.4)
            self.assertLess(np.mean(abs(original_y-truth)),1.75)

    def test_v5_two_families_keep_counts(self):
        img,tracks,_=sample()
        other=[[[150.,float(10+j*24)],[390.,float(10+j*24)]] for j in range(4)]
        result=refine_v5_candidates(img,{'first':tracks,'second':other})
        self.assertEqual(len(result['first']),7)
        self.assertEqual(len(result['second']),4)
        self.assertFalse(result['physical_yarn_count_verified'])

if __name__=='__main__':unittest.main()
