"""Expected failures document frozen legacy limitations; never alter baseline."""
import unittest
from dataclasses import replace
import numpy as np
from synthetic_capture_8k import CaptureScene,_render_strip

class LegacyPhysicsFailures(unittest.TestCase):
    @unittest.expectedFailure
    def test_weave_affects_transmission_geometry(self):
        s=CaptureScene(noise_sigma=0,shift_reflection_x=0)
        t=_render_strip(s,2900,2932,np.eye(3),np.random.default_rng(1))[1]
        u=_render_strip(replace(s,weave='twill_3_1'),2900,2932,np.eye(3),np.random.default_rng(1))[1]
        self.assertGreater(np.max(np.abs(t.astype(float)-u)),0)

    @unittest.expectedFailure
    def test_has_physical_light_direction(self):
        self.assertTrue(hasattr(CaptureScene(),'light_direction'))

    @unittest.expectedFailure
    def test_rejects_nonphysical_polarity_inversion(self):
        with self.assertRaises(ValueError):
            _render_strip(CaptureScene(contrast_polarity='bright'),2900,2932,np.eye(3),np.random.default_rng(1))
