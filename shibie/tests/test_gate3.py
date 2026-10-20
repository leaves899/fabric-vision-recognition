import unittest

from engine.gate3 import summarize_gate3


class Gate3Test(unittest.TestCase):
    def test_auxiliary_low_does_not_fail_core_gate3(self):
        result = summarize_gate3(
            {"status": "PASS"}, {"status": "PASS"}, {"status": "PASS"},
            {"direction_status": "PASS", "angle_status": "PASS", "weave_status": "LOW_CONFIDENCE", "weave_reasons": ["WEAVE_TEMPLATE_MATCH_LOW"]},
            {"reference_only": True},
        )
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(result["publishable"])
        self.assertIn("GATE3_WEAVE_LOW_CONFIDENCE", result["warnings"])

    def test_core_low_produces_low_confidence(self):
        result = summarize_gate3(
            {"status": "PASS"}, {"status": "PASS"}, {"status": "LOW_CONFIDENCE"},
            {"direction_status": "PASS", "angle_status": "PASS", "weave_status": "NOT_AVAILABLE"},
            {"reference_only": True},
        )
        self.assertEqual(result["status"], "LOW_CONFIDENCE")
        self.assertTrue(result["publishable"])

    def test_core_fail_produces_fail(self):
        result = summarize_gate3(
            {"status": "PASS"}, {"status": "PASS"}, {"status": "FAIL"},
            {"direction_status": "PASS", "angle_status": "PASS"},
            {"reference_only": True},
        )
        self.assertEqual(result["status"], "FAIL")
        self.assertFalse(result["publishable"])


if __name__ == "__main__":
    unittest.main()
