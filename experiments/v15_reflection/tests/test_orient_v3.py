"""Synthetic protocol tests only; these are not real-fabric accuracy proof."""
import unittest
import numpy as np
from PIL import Image

from experiments.v15_reflection.orient_v3 import propose_axes, axis_distance, _period


def woven(size=512, angle=0, diagonal_weight=0):
    yy, xx = np.indices((size,size))
    th = np.deg2rad(angle)
    u = xx*np.cos(th)+yy*np.sin(th)
    v = -xx*np.sin(th)+yy*np.cos(th)
    q = 128+35*np.cos(2*np.pi*u/14)+32*np.cos(2*np.pi*v/17)
    q += diagonal_weight*np.cos(2*np.pi*(xx*.74+yy*.67)/23)
    return Image.fromarray(np.uint8(np.clip(q,0,255))).convert("RGB")


class ProposedAxesTests(unittest.TestCase):
    def test_unlabelled_axis_modulo_90(self):
        self.assertEqual(axis_distance(0,90),0)
        self.assertEqual(axis_distance(179,1),2)

    def test_uniform_abstains(self):
        self.assertEqual(propose_axes(Image.new("RGB",(512,512),128))["status"],"ABSTAINED")

    def test_single_diagonal_texture_abstains(self):
        yy,xx = np.indices((512,512))
        q = 128+70*np.cos(2*np.pi*(xx*.75+yy*.66)/17)
        im = Image.fromarray(np.uint8(np.clip(q,0,255))).convert("RGB")
        self.assertEqual(propose_axes(im)["status"],"ABSTAINED")

    def test_acf_fundamental(self):
        x = np.arange(300)
        result = _period(120+33*np.cos(2*np.pi*x/15))
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result["pitch_px"],15,delta=1)

    def test_six_physical_axis_rotations_synthetic(self):
        for angle in (0,15,30,60,90,135):
            with self.subTest(angle=angle):
                result = propose_axes(woven(angle=angle))
                self.assertEqual(result["status"],"PROPOSED_NOT_VALIDATED",str(result))
                self.assertLessEqual(axis_distance(result["unlabelled_axes_deg"][0],angle),5)

    def test_diagonal_texture_contamination_synthetic(self):
        for angle in (0,15,30,60):
            for weight in (5,15,25,35,55):
                with self.subTest(angle=angle,weight=weight):
                    result = propose_axes(woven(angle=angle,diagonal_weight=weight))
                    self.assertIn(result["status"],("PROPOSED_NOT_VALIDATED","ABSTAINED"))
                    if result["status"]=="PROPOSED_NOT_VALIDATED":
                        self.assertLessEqual(axis_distance(result["unlabelled_axes_deg"][0],angle),5)

    def test_90_180_270_rotation_invariant(self):
        im = woven(angle=21)
        results = [propose_axes(im.rotate(r)) for r in (0,90,180,270)]
        self.assertTrue(all(x["status"]=="PROPOSED_NOT_VALIDATED" for x in results))
        for x in results[1:]:
            self.assertLessEqual(axis_distance(x["unlabelled_axes_deg"][0],
                                               results[0]["unlabelled_axes_deg"][0]),3)


if __name__=="__main__":
    unittest.main()
