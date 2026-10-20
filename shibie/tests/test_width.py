import unittest

import numpy as np

from engine.width import edge_pair_width, edge_pair_candidates, _select_consistent_pairs, _summary, _tile_quality, estimate_reflection_registration


class WidthMeasurementTest(unittest.TestCase):
    def test_registration_maps_transmission_into_shifted_reflection(self):
        transmission = np.zeros((160, 180), dtype=np.uint8)
        cv = __import__("cv2")
        cv.rectangle(transmission, (30, 35), (75, 105), 150, -1)
        cv.circle(transmission, (130, 55), 18, 230, -1)
        matrix = np.float32([[1.0, 0.0, 7.0], [0.0, 1.0, -5.0]])
        front = cv.warpAffine(transmission, matrix, (180, 160), borderMode=cv.BORDER_REFLECT)

        result = estimate_reflection_registration(front, transmission)

        self.assertEqual(result["status"], "PASS")
        estimated = result["matrix_transmission_to_reflection"]
        self.assertAlmostEqual(estimated[0][2], 7.0, delta=0.6)
        self.assertAlmostEqual(estimated[1][2], -5.0, delta=0.6)

    def test_edge_pair_returns_known_band_width(self):
        offsets = np.arange(-20.0, 20.5, 0.5)
        values = np.where(np.abs(offsets) <= 6.0, 210.0, 35.0)
        pair = edge_pair_width(offsets, values, min_width_px=2.0)
        self.assertIsNotNone(pair)
        self.assertAlmostEqual(pair["width_px"], 12.0, delta=1.0)
        self.assertLess(abs(pair["left_offset_px"] + 6.0), 0.6)
        self.assertLess(abs(pair["right_offset_px"] - 6.0), 0.6)

    def test_consistency_selection_rejects_narrow_texture_pairs(self):
        config = type("Config", (), {
            "width_consistency_weight": 0.38,
            "width_consistency_band_ratio": 0.12,
            "width_consistency_min_band_px": 2.0,
        })()
        candidates = []
        for profile_index, width in enumerate([18.0, 19.0, 18.5, 19.5, 18.0]):
            candidates.extend([
                {"profile_index": profile_index, "width_px": 4.0 + profile_index * 1.5, "pair_score": 9.0},
                {"profile_index": profile_index, "width_px": width, "pair_score": 8.5},
            ])
        selected = _select_consistent_pairs(candidates, config)
        self.assertEqual(len(selected), 5)
        self.assertTrue(all(item["width_px"] > 15.0 for item in selected))

    def test_tile_quality_prefers_sharp_contrast_tile(self):
        config = type("Config", (), {
            "width_tile_half_size_px": 16, "width_tile_min_contrast": 18.0, "width_tile_good_contrast": 55.0,
            "width_tile_min_laplacian": 8.0, "width_tile_good_laplacian": 80.0, "width_tile_min_weight": 0.25,
        })()
        flat = np.full((80, 80), 128, dtype=np.uint8)
        sharp = flat.copy()
        sharp[:, 38:42] = 220
        self.assertGreater(_tile_quality(sharp, np.array([40.0, 40.0]), config)["score"], _tile_quality(flat, np.array([40.0, 40.0]), config)["score"])

    def test_summary_reports_percentiles_and_gate_warning(self):
        samples = [{"width_px": width, "yarn_index": index // 2} for index, width in enumerate([8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19])]
        result = _summary(samples, 0.01, type("Config", (), {"width_outlier_mad_scale": 3.0, "width_min_valid_samples": 12, "width_min_valid_yarns": 3, "width_gate_p10_px": 12.0})())
        self.assertEqual(result["status"], "LOW_CONFIDENCE")
        self.assertIn("WIDTH_P10_BELOW_GATE", result["reasons"])
        self.assertAlmostEqual(result["p50_mm"], 0.135, places=4)


if __name__ == "__main__":
    unittest.main()
