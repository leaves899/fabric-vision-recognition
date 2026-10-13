"""Contract tests for G1 local-entity hypothesis competition.

Synthetic patterns verify software behavior only; they are not reported as
real-fabric accuracy or physical-yarn ground truth.
"""
import copy
import unittest

import cv2
import numpy as np

from benchmark.local_entity_competition import (
    evaluate_a3_holdout,
    infer_hypotheses,
    zoom_segment_to_original,
)


def synthetic_weave(brightness=1.0):
    h = w = 360
    image = np.full((h, w, 3), 62.0, np.float32)
    pitch = 30
    # Horizontal physical entities with paired edges and regular vertical
    # over/under interruptions.  This is only a deterministic code fixture.
    for row, y in enumerate(range(45, 330, pitch)):
        cv2.line(image, (0, y), (w - 1, y), (205, 205, 205), 12, cv2.LINE_AA)
        for col, x in enumerate(range(35, 340, pitch)):
            if (row + col) % 2:
                cv2.line(image, (x, y - 10), (x, y + 10), (88, 88, 88), 8, cv2.LINE_AA)
            else:
                cv2.line(image, (x - 8, y), (x + 8, y), (220, 220, 220), 10, cv2.LINE_AA)
    image = np.clip(image * brightness, 0, 255).astype(np.uint8)
    return image


def annotation():
    return {
        "schema_version": "1.0",
        "sample_id": "SYNTHETIC_CONTRACT_ONLY",
        "annotation_target": "PHYSICAL_YARN_REFERENCE",
        "coordinate_space": "ZOOM_2X_NATIVE_PIXELS",
        "crop_original_xyxy": [0, 0, 360, 360],
        "enlargement_scale": 2,
        "original_image_path": "unused.png",
        "original_image_sha256": "unused",
        "segments": {
            "reference": [[20, 90], [700, 90]],
            "check_same": [[20, 330], [700, 330]],
            "holdout_same": [[20, 450], [700, 450]],
            "check_cross": [[70, 20], [70, 700]],
            "check_cross_second": [[310, 20], [310, 700]],
        },
        "same_family_intervals": 4,
        "same_family_intervals_confirmed": True,
        "cross_family_intervals": 4,
        "cross_family_intervals_confirmed": True,
    }


class LocalEntityCompetitionTests(unittest.TestCase):
    def test_zoom_coordinates_map_to_original_without_using_zoom_pixels(self):
        ann = annotation()
        ann["crop_original_xyxy"] = [100, 200, 460, 560]
        result = zoom_segment_to_original(ann, [[20, 40], [60, 80]])
        np.testing.assert_allclose(result, [[110, 220], [130, 240]])

    def test_a3_change_cannot_change_inference_candidates_or_scores(self):
        image = synthetic_weave()
        ann = annotation()
        first, geometry = infer_hypotheses(image, ann)
        old_eval = evaluate_a3_holdout(first, geometry, ann)
        changed = copy.deepcopy(ann)
        changed["segments"]["holdout_same"] = [[20, 515], [700, 515]]
        second, second_geometry = infer_hypotheses(image, changed)
        new_eval = evaluate_a3_holdout(second, second_geometry, changed)
        self.assertEqual(first, second)
        self.assertNotEqual(old_eval["a3_rectified_mean_y"], new_eval["a3_rectified_mean_y"])
        self.assertFalse(old_eval["used_for_inference"])

    def test_brightness_change_preserves_candidate_ordering_contract(self):
        outcomes = []
        for brightness in (0.68, 1.0, 1.22):
            inferred, geometry = infer_hypotheses(synthetic_weave(brightness), annotation())
            held = evaluate_a3_holdout(inferred, geometry, annotation())
            outcomes.append(held["physical_reference_hypothesis_score"] > held["gap_competitor_score"])
        self.assertTrue(all(outcomes))

    def test_rotated_input_with_rotated_annotations_is_consistent(self):
        image = synthetic_weave()
        ann = annotation()
        base, base_geometry = infer_hypotheses(image, ann)
        base_eval = evaluate_a3_holdout(base, base_geometry, ann)
        rotated = cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
        changed = copy.deepcopy(ann)
        for role, segment in changed["segments"].items():
            changed["segments"][role] = [[2 * (359 - y / 2), 2 * (x / 2)] for x, y in segment]
        result, geometry = infer_hypotheses(rotated, changed)
        held = evaluate_a3_holdout(result, geometry, changed)
        self.assertAlmostEqual(
            held["physical_reference_hypothesis_score"],
            base_eval["physical_reference_hypothesis_score"],
            delta=0.08,
        )

    def test_wrong_period_and_printed_diagonal_are_not_certified(self):
        image = synthetic_weave()
        wrong = annotation()
        wrong["same_family_intervals"] = 8
        inferred, geometry = infer_hypotheses(image, wrong)
        held = evaluate_a3_holdout(inferred, geometry, wrong)
        self.assertEqual(
            inferred["period_counterexample_status"],
            "ABSTAIN_WRONG_PERIOD_OR_PHASE_COMPETITION",
        )
        self.assertFalse(held["automated_reference_support"])
        self.assertEqual(held["status"], "ABSTAIN_COMPETING_HYPOTHESES_NOT_SEPARATED")
        self.assertFalse(held["physical_identity_verified"])
        # Even a strong diagonal stripe response remains an unverified texture
        # hypothesis; software must never promote it to physical truth.
        self.assertTrue(all("confirmed_actual_physical_yarn" not in item
                            for item in inferred["twill_texture_hypotheses_NOT_truth"]))
        self.assertIsNone(inferred["verified_physical_yarn_count"])


if __name__ == "__main__":
    unittest.main()
