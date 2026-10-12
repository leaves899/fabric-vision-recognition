"""Synthetic correctness and abstention tests for orientation proposals."""
import unittest
import numpy as np
from PIL import Image

from experiments.v15_reflection.orient_v2 import _canonical_delta, propose_axes


def woven(size=512, yarn_theta=0, diagonal_weight=0):
    yy,xx=np.indices((size,size))
    th=np.deg2rad(yarn_theta)
    u=xx*np.cos(th)+yy*np.sin(th)
    v=-xx*np.sin(th)+yy*np.cos(th)
    q=130+40*np.cos(2*np.pi*u/20)+36*np.cos(2*np.pi*v/24)
    q+=diagonal_weight*np.cos(2*np.pi*(xx+yy)/53)
    return Image.fromarray(np.uint8(np.clip(q,0,255)),"L").convert("RGB")


class ProposalTests(unittest.TestCase):
    def test_modulo_90_error(self):
        self.assertEqual(_canonical_delta(0,90),0)
        self.assertEqual(_canonical_delta(4,178),6)

    def test_uniform_image_abstains(self):
        r=propose_axes(Image.new("RGB",(512,512),"gray"))
        self.assertEqual(r["status"],"ABSTAINED")
        self.assertIsNone(r.get("unlabelled_axes_deg"))

    def test_rotation_pair_equivariance(self):
        # Decision may abstain, but the two spectral estimators cannot
        # spontaneously choose different coordinate systems after 90/180.
        image=woven()
        outs=[propose_axes(image.rotate(x)) for x in (0,90,180,270)]
        for o in outs:
            self.assertIn(o["status"],("ABSTAINED","PROPOSED_NOT_VALIDATED"))
        if all(o["status"]=="PROPOSED_NOT_VALIDATED" for o in outs):
            for o in outs[1:]:
                self.assertLessEqual(_canonical_delta(
                    o["unlabelled_axes_deg"][0],
                    outs[0]["unlabelled_axes_deg"][0]),3.1)


if __name__=="__main__":
    unittest.main()
