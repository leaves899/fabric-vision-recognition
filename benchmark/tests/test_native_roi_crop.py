"""Synthetic-only ROI geometry tests. These are not fabric recognition tests."""
import unittest
from benchmark.run_annotated_v5_roi import crop_window


class NativeRoiCropTests(unittest.TestCase):
    def _annotation(self):
        return {
            "image_width": 3072,
            "image_height": 4080,
            "segments": {
                "reference": [[1674.255,1814.546],[1678.909,1567.855]],
                "check_same": [[2048.945,1649.309],[2044.291,1162.909]],
                "check_cross":None,
            },
        }

    def test_roi_preserves_all_original_points(self):
        data=self._annotation()
        rect=crop_window(data,380)
        self.assertEqual(rect,(1294,782,2430,2195))
        for coords in data["segments"].values():
            if coords:
                for x,y in coords:
                    self.assertTrue(rect[0]<=x<rect[2])
                    self.assertTrue(rect[1]<=y<rect[3])
        self.assertLess((rect[2]-rect[0])*(rect[3]-rect[1]),3_000_000)

    def test_zero_margin_has_positive_crop(self):
        data=self._annotation()
        roi=crop_window(data,0)
        self.assertGreaterEqual(roi[2]-roi[0],128)
        self.assertGreaterEqual(roi[3]-roi[1],128)

    def test_reject_negative_margin(self):
        with self.assertRaisesRegex(ValueError,"nonnegative"):
            crop_window(self._annotation(),-2)

    def test_out_of_bounds_margin_is_clamped(self):
        data=self._annotation()
        self.assertEqual(crop_window(data,99999),(0,0,3072,4080))


if __name__=="__main__":
    unittest.main()
