import unittest

import cv2
import numpy as np

from engine.config import DEFAULT_CONFIG
from engine.twill import (
    _binary_run_lengths,
    _classify_weave_matrix,
    _diagonal_float_chains,
    _intersection_confidence,
    _weave_template_scores,
    analyze_twill,
)


class TwillAnalysisTest(unittest.TestCase):
    def _image_with_lines(self, slope: int) -> np.ndarray:
        image = np.full((300, 300), 90, dtype=np.uint8)
        for offset in range(-260, 330, 38):
            if slope < 0:
                cv2.line(image, (0, 260 + offset), (260, offset), 205, 3)
            else:
                cv2.line(image, (0, offset), (260, 260 + offset), 205, 3)
        return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)

    def test_right_twill_for_rising_right_image_lines(self):
        result = analyze_twill(self._image_with_lines(-1), 90.0, 0.0)
        self.assertEqual(result["status"], "SEPARATE_RESULTS")
        self.assertEqual(result["direction_status"], "PASS")
        self.assertEqual(result["angle_status"], "PASS")
        self.assertEqual(result["direction"], "right")
        self.assertAlmostEqual(result["angle_deg"], 45.0, delta=8.0)

    def test_left_twill_for_falling_right_image_lines(self):
        result = analyze_twill(self._image_with_lines(1), 90.0, 0.0)
        self.assertEqual(result["status"], "SEPARATE_RESULTS")
        self.assertEqual(result["direction_status"], "PASS")
        self.assertEqual(result["angle_status"], "PASS")
        self.assertEqual(result["direction"], "left")
        self.assertAlmostEqual(result["angle_deg"], 45.0, delta=8.0)

    def test_uniform_image_is_rejected(self):
        image = np.full((300, 300, 3), 128, dtype=np.uint8)
        result = analyze_twill(image, 90.0, 0.0)
        self.assertEqual(result["status"], "SEPARATE_RESULTS")
        self.assertEqual(result["direction_status"], "FAIL")
        self.assertEqual(result["angle_status"], "FAIL")

    def test_synthetic_twill_has_scale_consistent_selected_evidence(self):
        result = analyze_twill(self._image_with_lines(-1), 90.0, 0.0)
        self.assertGreaterEqual(result["scale_consensus"], 0.65)
        self.assertGreater(result["selected_segment_count"], 0)
        self.assertTrue(result["evidence"])
        self.assertEqual(result["direction_status"], "PASS")
        self.assertEqual(result["angle_status"], "PASS")

    def test_twill_without_centerline_context_keeps_surface_result(self):
        result = analyze_twill(self._image_with_lines(-1), 90.0, 0.0)
        self.assertEqual(result["status"], "SEPARATE_RESULTS")
        self.assertEqual(result["interlacing_topology"]["status"], "NOT_AVAILABLE")
        self.assertEqual(result["weave_status"], "NOT_AVAILABLE")

    def test_interlacing_run_length_keeps_contiguous_float_segments(self):
        signs = {
            (0, 0): 1.0, (0, 1): 1.0, (0, 2): -1.0, (0, 3): -1.0,
            (1, 0): -1.0, (1, 1): -1.0, (1, 2): 1.0, (1, 3): 1.0,
        }
        self.assertEqual(sorted(_binary_run_lengths(signs, axis=1)), [2, 2, 2, 2])

    def test_diagonal_float_chain_requires_contiguous_same_state_crossings(self):
        signs = {(index, index): 1.0 for index in range(5)}
        points = {node: np.array([float(node[1] * 10), float(node[0] * 10)]) for node in signs}
        chains = _diagonal_float_chains(signs, points, (1, 1), min_points=4)
        self.assertEqual(len(chains), 1)
        self.assertEqual(chains[0]["node_count"], 5)
        self.assertAlmostEqual(chains[0]["image_line_angle_deg"], 45.0, delta=1.0)

    def test_weave_matrix_recognizes_plain_repeat(self):
        matrix = [[1, -1] * 4, [-1, 1] * 4] * 4
        signs = {(row, column): float(value) for row, values in enumerate(matrix) for column, value in enumerate(values)}
        result = _classify_weave_matrix(signs, DEFAULT_CONFIG)
        self.assertEqual(result["weave_type"], "plain")
        self.assertEqual(result["weave_status"], "PASS")

    def test_weave_matrix_recognizes_two_one_repeat(self):
        matrix = [
            [1, 1, -1, 1, 1, -1, 1, 1],
            [-1, 1, 1, -1, 1, 1, -1, 1],
            [1, -1, 1, 1, -1, 1, 1, -1],
            [-1, 1, -1, 1, 1, -1, 1, 1],
        ] * 2
        signs = {(row, column): float(value) for row, values in enumerate(matrix) for column, value in enumerate(values)}
        result = _classify_weave_matrix(signs, DEFAULT_CONFIG)
        self.assertEqual(result["weave_type"], "2/1")
        self.assertEqual(result["weave_status"], "PASS")

    def test_weave_matrix_recognizes_three_one_repeat(self):
        matrix = [
            [1, 1, 1, -1, 1, 1, 1, -1],
            [-1, 1, 1, 1, -1, 1, 1, 1],
            [1, -1, 1, 1, 1, -1, 1, 1],
            [1, 1, -1, 1, 1, 1, -1, 1],
        ] * 2
        signs = {(row, column): float(value) for row, values in enumerate(matrix) for column, value in enumerate(values)}
        result = _classify_weave_matrix(signs, DEFAULT_CONFIG)
        self.assertEqual(result["weave_type"], "3/1")
        self.assertEqual(result["weave_status"], "PASS")

    def test_template_match_downweights_uncertain_crossing_errors(self):
        matrix = np.fromfunction(
            lambda row, col: np.where((row + col) % 2 == 0, 1.0, -1.0),
            (8, 8),
        ).astype(np.float32)
        confidence = np.ones_like(matrix)
        for row, column in ((0, 0), (1, 3), (3, 4), (6, 2)):
            matrix[row, column] *= -1.0
            confidence[row, column] = 0.1
        unweighted = _weave_template_scores(matrix)["plain"]
        weighted = _weave_template_scores(matrix, confidence)["plain"]
        self.assertGreater(weighted, unweighted)
        self.assertGreater(weighted, 0.98)

    def test_intersection_confidence_rewards_clear_strong_crossings(self):
        near_threshold = _intersection_confidence(1.35, 1.0, 0.30, 1.0, 4.0)
        clear_crossing = _intersection_confidence(5.0, 1.0, 0.30, 1.0, 4.0)
        self.assertGreater(clear_crossing, near_threshold)
        self.assertGreaterEqual(near_threshold, 0.05)
        self.assertLessEqual(clear_crossing, 1.0)

    def test_repeat_consistency_downweights_low_confidence_error(self):
        matrix = np.fromfunction(
            lambda row, col: np.where((row + col) % 2 == 0, 1.0, -1.0),
            (8, 8),
        ).astype(np.float32)
        matrix[0, 0] *= -1.0
        signs = {(row, column): float(value) for row, values in enumerate(matrix) for column, value in enumerate(values)}
        high_confidence = _classify_weave_matrix(signs, DEFAULT_CONFIG)
        low_confidence = _classify_weave_matrix(
            signs, DEFAULT_CONFIG,
            {node: 0.05 if node == (0, 0) else 1.0 for node in signs},
        )
        self.assertGreater(low_confidence["repeat_consistency"], high_confidence["repeat_consistency"])

    def test_zero_confidence_keeps_low_confidence_protection(self):
        matrix = [[1, -1] * 4, [-1, 1] * 4] * 4
        signs = {(row, column): float(value) for row, values in enumerate(matrix) for column, value in enumerate(values)}
        result = _classify_weave_matrix(signs, DEFAULT_CONFIG, {node: 0.0 for node in signs})
        self.assertEqual(result["weave_status"], "LOW_CONFIDENCE")
        self.assertIn("WEAVE_REPEAT_CONSISTENCY_LOW", result["reasons"])
        self.assertEqual(result["candidate_confidence"], 0.0)


if __name__ == "__main__":
    unittest.main()
