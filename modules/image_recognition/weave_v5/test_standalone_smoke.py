"""Offline smoke tests for standalone V5 package (no photo fixtures needed)."""
import unittest
import numpy as np
from PIL import Image
try:
    from .color_plain import circular_phase, circular_gap, estimate_x_repeat
    from .run_photo_weave_v5 import choose_rois, summarize
except ImportError:
    from color_plain import circular_phase, circular_gap, estimate_x_repeat
    from run_photo_weave_v5 import choose_rois, summarize

class WeaveV5Smoke(unittest.TestCase):
    def test_40_pixel_period_recovered_from_signal(self):
        x=np.arange(640)
        row=(127+95*np.cos(2*np.pi*x/40)).clip(0,255).astype(np.uint8)
        img=np.tile(row,(640,1))
        period,_=estimate_x_repeat(img)
        self.assertEqual(period,40)

    def test_phases_near_half_repeat(self):
        a,c=circular_phase(np.arange(20,620,40),40)
        b,d=circular_phase(np.arange(40,620,40),40)
        self.assertAlmostEqual(circular_gap(a,b,40),20,places=4)
        self.assertGreater(c,.99)
        self.assertGreater(d,.99)

    def test_three_distinct_rois(self):
        boxes=choose_rois(Image.new('RGB',(2448,2050)),3)
        self.assertEqual(len(boxes),3)
        self.assertTrue(all(b[2]-b[0]==640 and b[3]-b[1]==640 for b in boxes))

    def test_evidence_consensus(self):
        regions=[dict(status='plain_candidate_from_color_topology'),dict(status='plain_candidate_from_color_topology'),dict(status='unresolved_no_lattice')]
        result=summarize(regions)
        self.assertEqual(result['organization_candidate'],'plain_1_1')
        self.assertFalse(result['physical_0_1_verified'])
        self.assertEqual(result['S_Z_direction'],'unresolved')

    def test_no_forced_guess(self):
        regions=[dict(status='unresolved_no_lattice')]*3
        self.assertIsNone(summarize(regions)['organization_candidate'])

if __name__=='__main__':
    unittest.main()
