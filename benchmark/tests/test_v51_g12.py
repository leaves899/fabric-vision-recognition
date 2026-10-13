"""G1.2 synthetic safety contracts; not physical-yarn accuracy tests."""
import sys,unittest
from pathlib import Path
import numpy as np
import cv2

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"demo/v5"))
from v51_g12_refinement import refine_family,refine_v5_g12

def fixture():
    h,w=240,360
    xx=np.arange(w,dtype=np.float32)
    yy=np.arange(h,dtype=np.float32)[:,None]
    centers=(65.,93.,121.,149.)
    photo=np.full((h,w),120.,np.float32)
    model=np.zeros((h,w),np.float32)
    tracks=[]
    for center in centers:
        y=center+2*np.sin(xx/55.)
        photo+=55*np.exp(-.5*((yy-y[None,:])/3.)**2)
        model=np.maximum(model,.95*np.exp(-.5*((yy-y[None,:])/2.4)**2))
        tracks.append([[float(x),center] for x in np.linspace(12,w-12,90)])
    photo=np.clip(photo,0,255).astype(np.uint8)
    return cv2.cvtColor(photo,cv2.COLOR_GRAY2BGR),model,tracks

class G12Tests(unittest.TestCase):
    def test_flat_photo_abstains_even_with_high_model(self):
        photo,model,tracks=fixture()
        blank=np.ones_like(photo)*127
        output,diag=refine_family(blank,tracks,model,28.)
        self.assertEqual(output,tracks)
        self.assertEqual(diag["changed"],0)

    def test_no_model_gain_abstains_even_with_photo(self):
        photo,model,tracks=fixture()
        output,diag=refine_family(photo,tracks,np.ones_like(model)*.95,28.)
        self.assertEqual(output,tracks)
        self.assertEqual(diag["changed"],0)

    def test_track_counts_preserved_90deg(self):
        photo,model,tracks=fixture()
        rotated=cv2.rotate(photo,cv2.ROTATE_90_CLOCKWISE)
        R=cv2.rotate(model,cv2.ROTATE_90_CLOCKWISE)
        H=photo.shape[0]
        t=[[[H-1-y,x] for x,y in track] for track in tracks]
        scores=dict(first=R,second=R,frozen_sha256="synthetic")
        out=refine_v5_g12(rotated,dict(first=t,second=t),scores)
        self.assertEqual(len(out["first"]),4)
        self.assertEqual(len(out["second"]),4)
        self.assertFalse(out["physical_yarn_identity_verified"])

    def test_probability_shape_mismatch_rejected(self):
        photo,model,tracks=fixture()
        with self.assertRaises(ValueError):
            refine_family(photo,tracks,model[:100],28.)

if __name__=="__main__":unittest.main()
