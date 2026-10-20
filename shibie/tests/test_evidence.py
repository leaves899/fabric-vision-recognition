import tempfile
import unittest
from pathlib import Path

import numpy as np

from engine.evidence import generate_evidence


class EvidenceTest(unittest.TestCase):
    def test_generates_images_and_index_from_existing_results(self):
        image = np.full((80, 100, 3), 120, dtype=np.uint8)
        measurement = {
            "engine_version": "test",
            "algorithm_profile": "test",
            "apparent_width": {
                "status": "PASS",
                "evidence": [{"direction": "warp", "center": [40, 40], "edge_left": [30, 40], "edge_right": [50, 40]}],
            },
            "twill": {
                "direction_status": "PASS", "angle_status": "PASS", "direction": "right", "angle_deg": 20.0,
                "evidence": [{"line": [10, 20, 70, 50]}],
                "weave_status": "LOW_CONFIDENCE",
                "interlacing_topology": {"weave_evidence": {"float_matrix": [[1, -1], [-1, 1]]}},
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            result = generate_evidence(image, measurement, directory, "W001")
            self.assertEqual(set(result["files"]), {"width", "twill", "direction_field", "centerlines", "weave_matrix", "index"})
            self.assertTrue(all(Path(path).exists() for path in result["files"].values()))


if __name__ == "__main__":
    unittest.main()
