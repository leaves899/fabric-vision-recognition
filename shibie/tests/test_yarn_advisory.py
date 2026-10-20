import unittest

from engine.yarn_advisory import advise_yarn_counts


class YarnAdvisoryTest(unittest.TestCase):
    def test_returns_reference_only_ranges(self):
        widths = {
            "warp": {"status": "PASS", "p50_mm": 0.14},
            "weft": {"status": "PASS", "p50_mm": 0.10},
        }
        result = advise_yarn_counts(32.0, 30.0, widths)
        self.assertTrue(result["reference_only"])
        self.assertEqual(result["status"], "AVAILABLE")
        self.assertEqual(result["warp"]["status"], "AVAILABLE")
        self.assertEqual(len(result["warp"]["range_ne"]), 2)

    def test_missing_width_is_not_available(self):
        result = advise_yarn_counts(32.0, 30.0, {"warp": None, "weft": None})
        self.assertEqual(result["status"], "NOT_AVAILABLE")
        self.assertEqual(result["warp"]["status"], "NOT_AVAILABLE")


if __name__ == "__main__":
    unittest.main()
