"""Synthetic tests for native-position anchoring, not real photo accuracy."""
import unittest
from benchmark.yarn_phase_anchor import normal_to_segment, adjust_first_family

class AnchorPhaseTests(unittest.TestCase):
    def tracks(self, y_values):
        return [[[0.0,float(y)],[300.0,float(y)]] for y in y_values]

    def test_corrects_gap_phase_without_using_holdout(self):
        tracks=self.tracks([10,30,50,70,90,110,130])
        ref=[[60,40],[250,40]]
        check=[[60,80],[250,80]]
        corrected, report=adjust_first_family(tracks,ref,check)
        self.assertEqual(report["status"],"ANCHORED_CANDIDATE_A")
        self.assertGreater(report["reference_before_px"],8)
        self.assertLess(report["reference_after_px"],.01)
        self.assertLess(report["check_after_px"],.01)

    def test_keeps_correct_yarn_centers(self):
        tracks=self.tracks([0,20,40,60,80,100,120])
        corrected, report=adjust_first_family(tracks,[[60,40],[250,40]],[[60,80],[250,80]])
        self.assertEqual(report["status"],"ALREADY_ALIGNED_A")
        self.assertEqual(report["reference_after_px"],0)
        self.assertEqual(report["check_after_px"],0)

    def test_rejects_zero_support(self):
        corrected, report=adjust_first_family([],[[0,40],[250,40]])
        self.assertEqual(report["status"],"ABSTAINED")
        self.assertEqual(corrected,[])

    def test_rejects_short_anchor(self):
        with self.assertRaisesRegex(ValueError,"20"):
            normal_to_segment([[2,2],[9,2]])

    def test_corrects_negative_image_axis(self):
        tracks=[[[10,0],[10,300]],[[30,0],[30,300]],[[50,0],[50,300]],
                [[70,0],[70,300]],[[90,0],[90,300]],[[110,0],[110,300]]]
        corrected,report=adjust_first_family(tracks,[[40,50],[40,250]],[[80,50],[80,250]])
        self.assertEqual(report["status"],"ANCHORED_CANDIDATE_A")
        self.assertLess(report["reference_after_px"],1)
        self.assertLess(report["check_after_px"],1)

if __name__=="__main__":
    unittest.main()
