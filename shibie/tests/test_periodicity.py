import unittest

import numpy as np

from engine.periodicity import compare_periodicity_to_centerlines, estimate_normal_periodicity
from engine.confidence import confidence_for_direction


class PeriodicityTest(unittest.TestCase):
    def test_autocorrelation_recovers_synthetic_pitch(self):
        x = np.arange(260, dtype=np.float64)
        profile = 127.0 + 38.0 * np.sin(2.0 * np.pi * x / 20.0)
        image = np.tile(profile, (90, 1)).astype(np.uint8)
        result = estimate_normal_periodicity(image, 10.0, 35.0)
        self.assertEqual(result["status"], "PASS")
        self.assertAlmostEqual(result["spacing_px"], 20.0, delta=1.0)

    def test_comparison_flags_large_spacing_difference_without_rewriting_value(self):
        result = compare_periodicity_to_centerlines(
            {"status": "PASS", "spacing_px": 20.0}, 10.0
        )
        self.assertAlmostEqual(result["spacing_difference_pct"], 66.6667, places=3)
        self.assertEqual(result["agreement"], "AVAILABLE")

    def test_negative_autocorrelation_peaks_are_not_measurements(self):
        # Alternating contrast produces negative odd-lag peaks in this range.
        image = np.tile(np.array([0, 255] * 100, dtype=np.uint8), (60, 1))
        result = estimate_normal_periodicity(image, 1.0, 1.0)
        self.assertEqual(result["status"], "NOT_AVAILABLE")

    def test_weak_periodicity_peak_does_not_change_centerline_confidence(self):
        density = {"path_diff_pct": 0.0}
        centerline = {"spacing_cv": 0.0, "mean_coverage": 1.0, "valid_centerline_count": 10}
        periodicity = {"agreement": "AVAILABLE", "spacing_difference_pct": 60.0, "autocorrelation_peak": 0.10}
        result = confidence_for_direction(density, centerline, periodicity=periodicity)
        self.assertEqual(result["status"], "PASS")



if __name__ == "__main__":
    unittest.main()
