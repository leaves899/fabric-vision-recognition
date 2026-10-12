"""Numerical synthetic tests only; no photographic yarn GT is assumed."""
from __future__ import annotations

import unittest

from benchmark.phase_offset_diagnostic import (
    closest_track_distances, evaluate_tracks, nearby_candidate_pitch,
)


class PhaseDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.on_yarn = {
            "segments": {
                "reference": [[20, 20], [190, 20]],
                "check_same": [[20, 40], [190, 40]],
            }
        }
        self.center_tracks=[
            [[0,0],[210,0]],
            [[0,20],[210,20]],
            [[0,40],[210,40]],
            [[0,60],[210,60]],
            [[0,80],[210,80]],
        ]
        self.gap_tracks=[
            [[0,10],[210,10]],
            [[0,30],[210,30]],
            [[0,50],[210,50]],
            [[0,70],[210,70]],
            [[0,90],[210,90]],
        ]

    def test_distance_zero_for_yarn_center(self):
        self.assertLess(max(closest_track_distances([[40,20],[60,40]],self.center_tracks)),1e-5)

    def test_gap_centered_lines_have_half_pitch_displacement(self):
        self.assertAlmostEqual(closest_track_distances([[50,20]],self.gap_tracks)[0],10,places=5)
        result=evaluate_tracks(self.on_yarn,self.gap_tracks)
        self.assertAlmostEqual(result["reference"]["local_candidate_pitch_px"],20)
        self.assertAlmostEqual(result["reference"]["distance_as_fraction_of_candidate_pitch"],.5)
        self.assertTrue(result["reference"]["possible_gap_phase"])
        self.assertTrue(result["check_same"]["possible_gap_phase"])

    def test_correct_center_is_not_flagged(self):
        result=evaluate_tracks(self.on_yarn,self.center_tracks)
        self.assertLess(result["reference"]["median_min_distance_px"],.01)
        self.assertFalse(result["reference"]["possible_gap_phase"])
        self.assertFalse(result["check_same"]["possible_gap_phase"])

    def test_independent_check_absence_explicit(self):
        obj={"segments":{"reference":[[20,20],[190,20]],"check_same":None}}
        result=evaluate_tracks(obj,self.center_tracks)
        self.assertEqual(result["check_same"]["status"],"NO_OPERATOR_SEGMENT")

    def test_offset_from_cropped_image_preserved(self):
        a={"segments":{"reference":[[320,420],[490,420]],"check_same":[[320,440],[490,440]]}}
        result=evaluate_tracks(a,self.center_tracks,origin=(300,400))
        self.assertAlmostEqual(result["reference"]["median_min_distance_px"],0,places=5)

    def test_empty_tracks_have_unknown_pitch_and_distances(self):
        result=evaluate_tracks(self.on_yarn,[])
        self.assertIsNone(result["reference"]["median_min_distance_px"])
        self.assertIsNone(result["reference"]["distance_as_fraction_of_candidate_pitch"])
        self.assertFalse(result["reference"]["possible_gap_phase"])


if __name__ == "__main__":
    unittest.main()
