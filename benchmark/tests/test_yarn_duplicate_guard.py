"""Synthetic alias regression, not physical-fabric accuracy testing."""
import unittest
from benchmark.yarn_duplicate_guard import suppress_double_tracks

class DoubleTrackTests(unittest.TestCase):
    @staticmethod
    def horizontal(ys):
        return [[[10.0,float(y)],[300.0,float(y)]] for y in ys]

    def test_two_candidate_lines_per_real_yarn_are_suppressed(self):
        tracks=self.horizontal(range(0,211,10))  # V4 pitch 10, real pitch 20
        raw,info=suppress_double_tracks(
            tracks,[[20,40],[290,40]],[[20,120],[290,120]],
            physical_intervals=4,confirmed=True,
            holdout=[[20,80],[290,80]])
        self.assertEqual(info["status"],"DOUBLE_CANDIDATES_SUPPRESSED_UNVERIFIED_FIELD")
        self.assertEqual(info["candidate_lines_per_real_yarn_period"],2)
        self.assertEqual(info["suppressed_candidates"],10)
        self.assertEqual(len(raw),11)
        self.assertLess(info["reference_after_px"],.01)
        self.assertLess(info["second_after_px"],.01)
        self.assertLess(info["independent_holdout_after_px"],.01)

    def test_no_one_interval_truth_means_no_dedup(self):
        tracks=self.horizontal(range(0,211,10))
        corrected,info=suppress_double_tracks(
            tracks,[[20,40],[290,40]],[[20,120],[290,120]])
        self.assertEqual(info["status"],"ABSTAINED")
        self.assertEqual(info["reason"],"PHYSICAL_INTERVAL_COUNT_UNCONFIRMED")
        self.assertEqual(corrected,tracks)

    def test_wrong_interval_reports_no_alias_and_does_not_hack(self):
        tracks=self.horizontal(range(0,211,10))
        _,info=suppress_double_tracks(tracks,[[20,40],[290,40]],[[20,120],[290,120]],
                                     physical_intervals=8,confirmed=True)
        self.assertEqual(info["status"],"ABSTAINED")
        self.assertEqual(info["reason"],"NO_CLEAR_INTEGER_MULTIPLE_ALIAS")

    def test_three_to_one_duplicate(self):
        tracks=self.horizontal(range(0,241,10))
        output,info=suppress_double_tracks(tracks,[[20,30],[290,30]],[[20,150],[290,150]],
                                           physical_intervals=4,confirmed=True)
        self.assertEqual(info["candidate_lines_per_real_yarn_period"],3)
        self.assertLess(len(output),len(tracks)*.5)

    def test_vertical_detects_same_alias(self):
        tracks=[[[float(x),10.0],[float(x),300.0]] for x in range(0,211,10)]
        output,info=suppress_double_tracks(tracks,[[40,20],[40,280]],[[120,20],[120,280]],
                                           physical_intervals=4,confirmed=True)
        self.assertEqual(info["status"],"DOUBLE_CANDIDATES_SUPPRESSED_UNVERIFIED_FIELD")
        self.assertLess(len(output),len(tracks))

    def test_rejects_nonparallel_yarn_anchors(self):
        tracks=self.horizontal(range(0,211,10))
        _,info=suppress_double_tracks(tracks,[[20,40],[290,40]],[[100,20],[100,240]],
                                     physical_intervals=4,confirmed=True)
        self.assertEqual(info["reason"],"NONPARALLEL_REAL_YARN_ANCHORS")

    def test_refuses_tiny_unresolvable_real_pitch(self):
        tracks=self.horizontal(range(0,211,10))
        _,info=suppress_double_tracks(tracks,[[20,40],[290,40]],[[20,80],[290,80]],
                                     physical_intervals=20,confirmed=True)
        self.assertEqual(info["reason"],"PHYSICAL_YARNS_UNRESOLVABLE_AT_IMAGE_SCALE")

    def test_requires_boolean_explicit_confirmation_not_one_as_true(self):
        tracks=self.horizontal(range(0,211,10))
        _,info=suppress_double_tracks(tracks,[[20,40],[290,40]],[[20,120],[290,120]],
                                     physical_intervals=True,confirmed=True)
        self.assertEqual(info["reason"],"PHYSICAL_INTERVAL_COUNT_UNCONFIRMED")

if __name__=="__main__":
    unittest.main()
