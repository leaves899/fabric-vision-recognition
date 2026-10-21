from __future__ import annotations
import tempfile
import unittest
from pathlib import Path
import numpy as np
from synthetic_capture_8k import CaptureScene
from synthetic_photo_guided_flat_8k import (
    DEFAULT_REFERENCE,_sample_reference,_colorize_reflection,
    _frame_mask,apply_photo_appearance)


class FlatPhotoGuidedCaptureTests(unittest.TestCase):
    def test_existing_real_photo_reference_is_not_synthetic(self):
        photo,style=_sample_reference(DEFAULT_REFERENCE)
        self.assertGreater(photo.shape[0],500)
        self.assertGreater(photo.shape[1],500)
        self.assertGreater(len(style["photo_sha256"]),32)
        self.assertEqual(len(style["palette_bgr_dark_mid_bright"]),3)

    def test_flat_physical_frame_is_exact_50mm(self):
        mask=_frame_mask(988,1012,8000,6000,.0125)
        self.assertTrue(mask[12,2000])
        self.assertFalse(mask[12,4000])
        self.assertFalse(mask[0,2000])

    def test_reflection_color_references_source_palette(self):
        photo,style=_sample_reference(DEFAULT_REFERENCE)
        gray=np.tile(np.arange(0,255,dtype=np.uint8),(64,1))
        a=_colorize_reflection(gray,style["palette_bgr_dark_mid_bright"],
                               style["fine_grain_sigma_px"],np.random.default_rng(1))
        b=_colorize_reflection(gray,style["palette_bgr_dark_mid_bright"],
                               style["fine_grain_sigma_px"],np.random.default_rng(1))
        self.assertTrue(np.array_equal(a,b))
        self.assertGreater(np.mean(np.abs(a.astype(float)-gray[:,:,None])),2.)

    def test_flat_workflow_rejects_geometric_rotation(self):
        with tempfile.TemporaryDirectory() as temp:
            bad=CaptureScene(rotation_deg=1.,fabric_rotation_deg=0.,perspective=0.)
            with self.assertRaisesRegex(ValueError,"ZERO_ROTATION"):
                apply_photo_appearance(bad,Path(temp),DEFAULT_REFERENCE)
            bad2=CaptureScene(rotation_deg=0.,fabric_rotation_deg=2.,perspective=0.)
            with self.assertRaisesRegex(ValueError,"ZERO_FABRIC_ROTATION"):
                apply_photo_appearance(bad2,Path(temp),DEFAULT_REFERENCE)


if __name__=="__main__":
    unittest.main()
