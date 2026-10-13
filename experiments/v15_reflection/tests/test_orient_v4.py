"""V4 regression checks: stable axes, no silent texture promotion, symmetry."""
from __future__ import annotations
import unittest
import numpy as np
from PIL import Image

from experiments.v15_reflection.orient_v4 import (
    propose_axes, native_evidence, _native_tile_proposals, VERSION)
from experiments.v15_reflection.orient_v3 import axis_distance


def woven(size=512, angle=0, diagonal_weight=0):
    yy,xx=np.indices((size,size))
    t=np.deg2rad(angle)
    u=xx*np.cos(t)+yy*np.sin(t)
    v=-xx*np.sin(t)+yy*np.cos(t)
    q=128+35*np.cos(2*np.pi*u/14)+32*np.cos(2*np.pi*v/17)
    q+=diagonal_weight*np.cos(2*np.pi*(xx*.74+yy*.67)/23)
    return Image.fromarray(np.uint8(np.clip(q,0,255))).convert("RGB")


class V4Tests(unittest.TestCase):
    def test_flat_rejects(self):
        r=propose_axes(Image.new("RGB",(512,512),128))
        self.assertEqual(r["status"],"ABSTAINED")
        self.assertIsNone(r.get("unlabelled_axes_deg"))

    def test_native_hessian_axis_on_known_synthetic(self):
        for angle in (0,15,21,30,60,135):
            r=native_evidence(woven(angle=angle))
            self.assertTrue(r["native_hessian_strong"])
            self.assertLessEqual(axis_distance(r["native_hessian_consensus_deg"],angle),3.)

    def test_diagonal_overlay_is_not_wrong_accepted(self):
        for angle in (0,15,30,60):
            for overlay in (5,15,25,35,55):
                r=propose_axes(woven(angle=angle, diagonal_weight=overlay))
                if r["status"]=="PROPOSED_NOT_VALIDATED":
                    self.assertLessEqual(axis_distance(
                        r["unlabelled_axes_deg"][0],angle),5.)

    def test_rotation_90_180_270(self):
        im=woven(angle=21)
        outcomes=[propose_axes(im.rotate(deg)) for deg in (0,90,180,270)]
        self.assertTrue(all(r["status"]=="PROPOSED_NOT_VALIDATED" for r in outcomes))
        for r in outcomes:
            self.assertLessEqual(axis_distance(r["unlabelled_axes_deg"][0],21),4)

    def test_native_four_tile_recovery_rotation(self):
        # Dense native yarns are aliased in a whole-frame 512px thumbnail,
        # but four true-resolution patches must agree after quarter turns.
        image=woven(size=1200,angle=21)
        results=[propose_axes(image.rotate(k)) for k in (0,90,180,270)]
        for r in results:
            self.assertEqual(r["status"],"PROPOSED_NOT_VALIDATED",str(r))
            self.assertEqual(r.get("promotion_reason"),
                             "THREE_OF_FOUR_NATIVE_PATCHES_AND_HESSIAN_AGREE")
            self.assertLessEqual(axis_distance(r["unlabelled_axes_deg"][0],21),3)

    def test_small_image_never_upsampled(self):
        self.assertEqual(_native_tile_proposals(Image.new("RGB",(512,512),128)),[])
        self.assertEqual(native_evidence(Image.new("RGB",(250,250),128))["native_patch_side_px"],250)

    def test_output_method_provenance(self):
        x=propose_axes(woven())
        self.assertEqual(x["method"],VERSION)
        self.assertIn("requires_manual_confirmation",x)
        self.assertIn("native_hessian_scales",x)


if __name__=="__main__":
    unittest.main()
