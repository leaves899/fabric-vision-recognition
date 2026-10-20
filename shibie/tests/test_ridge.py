import unittest

import numpy as np

from engine.ridge import _validate_seed_tracks


class RidgeSeedValidationTest(unittest.TestCase):
    def test_weak_profile_track_is_removed_only_when_extra_tracks_exist(self):
        roi = np.zeros((90, 160), dtype=np.float32)
        validation = np.tile(np.linspace(60, 200, 160, dtype=np.float32), (90, 1))
        # Create seven strong local contrast locations and two weak ones.
        for x in (15, 30, 45, 60, 75, 90, 105):
            roi[:, x] = 255
            validation[:, x] = 250
        for x in (120, 135):
            roi[:, x] = 255
        tracks, _, diagnostic = _validate_seed_tracks(
            roi, validation, np.array([15, 30, 45, 60, 75, 90, 105, 120, 135], dtype=float),
            8.0, 15.0, type("Config", (), {
                "ridge_prediction_points": 4, "ridge_strip_smoothing_sigma": 1.0,
                "ridge_peak_distance_ratio": 0.70,
                "ridge_track_profile_contrast_floor": 0.12,
                "ridge_track_profile_contrast_relative_floor": 0.55,
                "ridge_track_filter_min_extra": 2, "min_valid_centerlines": 5,
            })(),
        )
        self.assertGreater(diagnostic["track_profile_rejected_count"], 0)
        self.assertGreaterEqual(len(tracks), 7)


if __name__ == "__main__":
    unittest.main()
