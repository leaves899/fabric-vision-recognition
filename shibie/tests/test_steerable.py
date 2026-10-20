import unittest

from engine.config import DEFAULT_CONFIG
from engine.steerable import assess_scale_consistency


def candidate(key: str, density: float, quality: float) -> dict:
    polarity, sigma = key.split("@")
    return {
        "_base_confidence_status": "PASS",
        "candidate_quality": quality,
        "density": {"density_per_cm": density},
        "steerable": {
            "response_key": key,
            "selected_sigma": float(sigma),
            "selected_polarity": polarity,
        },
    }


class SteerableScaleConsistencyTest(unittest.TestCase):
    def test_quality_close_candidates_with_large_density_gap_are_flagged(self):
        selected = candidate("dark@4.3", 26.62, 1.018)
        result = assess_scale_consistency(
            [selected, candidate("bright@4.3", 20.70, 0.968)], selected
        )
        self.assertEqual(result["status"], "AVAILABLE")
        self.assertTrue(result["disagreement"])

    def test_nearby_density_candidates_remain_consistent(self):
        selected = candidate("bright@6", 43.876, 1.048)
        result = assess_scale_consistency(
            [selected, candidate("bright@5", 43.689, 1.040)], selected
        )
        self.assertEqual(result["status"], "AVAILABLE")
        self.assertFalse(result["disagreement"])


if __name__ == "__main__":
    unittest.main()
