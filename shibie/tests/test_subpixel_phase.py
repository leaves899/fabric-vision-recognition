from __future__ import annotations
import unittest
import numpy as np
from engine.subpixel_physical_phase import (_fold_fractional, _positions,
    refine_pitch_subpixel, validate_centers_fractional)


class SubpixelPhaseTest(unittest.TestCase):
    def test_float_pitch_does_not_accumulate_integer_drift(self):
        pitch = 800. / 30.
        line = _positions(640, 3.25, pitch)
        self.assertGreater(len(line), 10)
        self.assertLess(float(np.max(np.abs(np.diff(line)-pitch))), 1.e-8)

    def test_subpixel_acf_finds_fractional_period_without_truth_input(self):
        pitch = 800. / 30.
        x = np.arange(640, dtype=float)
        signal = (128. + 48*np.cos(2*np.pi*(x-4.0)/pitch)
                  + 12*np.cos(4*np.pi*(x-4.0)/pitch))
        inverse = 255.-signal
        result = refine_pitch_subpixel(signal, inverse, 27)
        self.assertEqual(result["status"], "CANDIDATE_ONLY")
        self.assertLess(abs(result["pitch_px"]-pitch), .21)

    def test_float_fold_preserves_phase(self):
        p = 800. / 30.
        x = np.arange(640, dtype=float)
        profile = 100.+45*np.cos(2*np.pi*(x-5.)/p)
        result = _fold_fractional(profile, p)
        self.assertIsNotNone(result)
        phases, values = result
        measured = float(phases[np.argmax(values)])
        dist = abs((measured-5. + p/2.) % p - p/2.)
        self.assertLess(dist, 1.0)

    def test_bad_pair_rejected(self):
        patch = np.zeros((520,520,3), dtype=np.uint8)
        result = validate_centers_fractional(patch,patch,"warp",27)
        self.assertNotEqual(result["status"],"PASS")

    def test_not_confusing_rt_polarity_with_yarn_identity(self):
        x = np.arange(520,dtype=np.float64)
        period = 800./30.
        # Both true yarns and equally-sized pores have a possible extremum.
        core = np.cos(2*np.pi*(x-4.)/period)
        a = np.clip(125 + 65*core,0,255).astype(np.uint8)
        b = np.clip(125 - 65*core,0,255).astype(np.uint8)
        R = np.repeat(a[None,:,None],520,axis=0)
        R = np.repeat(R,3,axis=2)
        T = np.repeat(b[None,:,None],520,axis=0)
        T = np.repeat(T,3,axis=2)
        result = validate_centers_fractional(R,T,"warp",27)
        self.assertIn(result["status"],("LOW_CONFIDENCE","UNDETERMINED"))


if __name__ == "__main__":
    unittest.main()
