"""Synthetic tests for two real-yarn anchor calibration; not textile accuracy."""
import unittest
from benchmark.yarn_pitch_calibration import two_anchor_correct

class DualYarnCalTests(unittest.TestCase):
    @staticmethod
    def lines(coords):
        return [[[0,float(y)],[300,float(y)]] for y in coords]

    def test_two_anchors_calibrate_gap_phase_and_pitch(self):
        old=self.lines([10,60,110,160,210,260,310])
        # Actual center grid: y=20,65,110,155,... (45px pitch)
        corrected,report=two_anchor_correct(old,[[20,20],[280,20]],[[20,110],[280,110]])
        self.assertEqual(report["status"],"TWO_ANCHOR_CANDIDATE_GRID")
        self.assertLess(report["reference_after_px"],.01)
        self.assertLess(report["second_after_px"],.01)
        self.assertAlmostEqual(report["scale_pitch"],.90,places=3)
        self.assertFalse(report["physical_interval_count_verified"])

    def test_vertical_segments(self):
        old=[[[x,0],[x,300]] for x in [10,40,70,100,130,160]]
        corrected,report=two_anchor_correct(old,[[20,10],[20,290]],[[80,10],[80,290]])
        self.assertEqual(report["status"],"TWO_ANCHOR_CANDIDATE_GRID")
        self.assertLess(report["reference_after_px"],1)

    def test_refuses_nonparallel_manual_lines(self):
        old=self.lines([10,40,70,100,130,160])
        _,report=two_anchor_correct(old,[[30,40],[270,40]],[[50,20],[50,280]])
        self.assertEqual(report["status"],"ABSTAINED")
        self.assertEqual(report["reason"],"ANCHOR_DIRECTIONS_NOT_PARALLEL")

    def test_no_candidate_grids(self):
        _,report=two_anchor_correct([],[[20,30],[280,30]],[[20,80],[280,80]])
        self.assertEqual(report["status"],"ABSTAINED")

    def test_count_not_claimed_verified(self):
        old=self.lines([10,60,110,160,210,260])
        _,report=two_anchor_correct(old,[[20,20],[280,20]],[[20,100],[280,100]])
        self.assertEqual(report["physical_interval_count_verified"],False)

if __name__=="__main__":
    unittest.main()
