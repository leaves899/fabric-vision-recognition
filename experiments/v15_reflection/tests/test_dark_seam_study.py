"""Independent synthetic positives and negatives for dark-seam ablation."""
import unittest
import numpy as np
from experiments.v15_reflection.dark_seam_study import (
    angle_delta, dark_ridge, propose,
)


def image_of_floats(seams, size=600):
    yy,xx=np.mgrid[:size,:size]
    angle=np.deg2rad(78.)
    along=xx*np.cos(angle)+yy*np.sin(angle)
    across=-xx*np.sin(angle)+yy*np.cos(angle)
    image=np.ones((size,size,3),np.float32)*[115,74,35]
    if seams:
        d=np.minimum(across%18.,18.-across%18.)
        image-=10*np.exp(-.5*(d/1.6)**2)[:,:,None]
    for row in range(-24,40):
        for col in range(-24,40):
            if (col-row)%4:continue
            cx=300+col*16*np.cos(angle)-row*18*np.sin(angle)
            cy=300+col*16*np.sin(angle)+row*18*np.cos(angle)
            if cx<0 or cy<0 or cx>=size or cy>=size:continue
            x0=max(0,int(cx)-9);x1=min(size,int(cx)+10)
            y0=max(0,int(cy)-9);y1=min(size,int(cy)+10)
            z=np.exp(-.5*((xx[y0:y1,x0:x1]-cx)**2/25+
                           (yy[y0:y1,x0:x1]-cy)**2/16))
            image[y0:y1,x0:x1]+=125*z[:,:,None]
    return np.uint8(np.clip(image,0,255))


class DarkSeamTests(unittest.TestCase):
    def test_hessian_tangent_not_normal(self):
        n=240
        y,x=np.mgrid[:n,:n]
        for angle in (0,30,60,90,120,150):
            t=np.deg2rad(angle)
            transverse=-x*np.sin(t)+y*np.cos(t)
            bright=np.zeros((n,n),np.float32)
            for k in range(-10,11):
                bright+=40*np.exp(-.5*((transverse-k*20)/2)**2)
            found,_=dark_ridge(bright,np.ones((n,n),bool))
            self.assertIsNotNone(found)
            self.assertLess(angle_delta(found,angle),1.5)

    def test_dot_lattice_without_seams_must_abstain(self):
        im=image_of_floats(seams=False)
        for rotation in range(4):
            self.assertEqual(propose(np.rot90(im,rotation).copy())["status"],"ABSTAINED")

    def test_weak_dark_ridges_rotate(self):
        im=image_of_floats(seams=True)
        for quarter_turn in range(4):
            with self.subTest(quarter_turn=quarter_turn):
                r=propose(np.rot90(im,quarter_turn).copy())
                self.assertEqual(r["status"],"CONSISTENT_IMAGE_RIDGE_UNVERIFIED")
                self.assertLess(angle_delta(r["axis_deg"],(78+90*quarter_turn)%180),3)

    def test_flat_image_refuses(self):
        r=propose(np.ones((600,600,3),dtype=np.uint8)*128)
        self.assertEqual(r["status"],"ABSTAINED")
        self.assertIsNone(r["density_per_cm"])
        self.assertFalse(r["physical_yarn_confirmed"])


if __name__=="__main__":
    unittest.main()
