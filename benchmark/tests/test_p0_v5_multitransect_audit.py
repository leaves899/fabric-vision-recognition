"""E6 V5 transect concept tests; synthetic bright/dark lines aren't yarn GT."""
import unittest
import numpy as np
import cv2
from benchmark.p0_v5_multitransect_audit import (
    photo_transverse_cuts, characterize_cuts, analyze_track,
    group_median_differences, CUT_FRACTIONS,
)


class MultiTransectTests(unittest.TestCase):
    @staticmethod
    def fake_line():
        img=np.full((200,250,3),110,np.uint8)
        cv2.line(img,(20,88),(220,88),(215,215,215),7)
        return img

    def test_one_line_is_five_correlated_cuts_not_five_yarns(self):
        img=self.fake_line()
        cuts=photo_transverse_cuts(img,[[35,88],[205,88]],19)
        self.assertEqual(cuts.shape,(len(CUT_FRACTIONS),25))
        out=characterize_cuts(cuts)
        self.assertEqual(out["number_of_CORRELATED_transects"],5)
        self.assertEqual(out["state"],"OPTICAL_ONLY")
        self.assertIsNone(out["physical_yarn_identity_probability"])

    def test_synthetic_drawn_fiber_has_two_flank_brightness_peak(self):
        img=self.fake_line()
        f,_=analyze_track(img,[[35,88],[205,88]],19)
        self.assertGreater(f["center_vs_flanks_abs_response_z"],0)
        self.assertGreater(f["two_sided_center_peak_fraction"],.8)
        # Printed / purely drawn line also succeeds: this is NOT a yarn
        # classifier and must never upgrade image evidence to physical GT.
        self.assertIsNone(f["physical_yarn_identity_probability"])

    def test_flat_image_abstains_not_asserting_negative_yarn(self):
        img=np.full((200,250,3),99,np.uint8)
        f,_=analyze_track(img,[[35,88],[205,88]],19)
        self.assertEqual(f["state"],"UNRESOLVED")
        self.assertEqual(f["reason"],"FLAT_NATIVE_CUTS")

    def test_invalid_geometry_or_outside_border_is_unresolved(self):
        img=self.fake_line()
        bad=photo_transverse_cuts(img,[[3,4],[35,4]],19)
        self.assertIsNone(bad)
        o=characterize_cuts(bad)
        self.assertEqual(o["state"],"UNRESOLVED")
        self.assertEqual(o["number_of_CORRELATED_transects"],0)

    def test_resize_changes_sample_support_not_a_new_true_yarn(self):
        img=self.fake_line()
        enlarged=cv2.resize(img,None,fx=2,fy=2,interpolation=cv2.INTER_NEAREST)
        left=photo_transverse_cuts(img,[[35,88],[205,88]],19)
        right=photo_transverse_cuts(enlarged,[[70,176],[410,176]],38)
        self.assertEqual(left.shape,right.shape)
        self.assertIsNone(characterize_cuts(right)["physical_yarn_identity_probability"])

    def test_90_degree_rotation_stable_for_symmetric_fake_line(self):
        img=self.fake_line()
        rot=cv2.rotate(img,cv2.ROTATE_90_CLOCKWISE)
        a,_=analyze_track(img,[[35,88],[205,88]],19)
        b,_=analyze_track(rot,[[111,35],[111,205]],19)
        self.assertLess(abs(a["center_vs_flanks_abs_response_z"]-
                            b["center_vs_flanks_abs_response_z"]),.04)
        self.assertLess(abs(a["two_sided_center_peak_fraction"]-
                            b["two_sided_center_peak_fraction"]),.04)

    def test_group_medians_prevent_pseudoreplication(self):
        paired=[{"operator_yarn_group_id":"one","comparison_metrics":{"metric":v}}
                for v in (.1,.2,.4)]
        paired.append({"operator_yarn_group_id":"two","comparison_metrics":{"metric":-.3}})
        groups=group_median_differences(paired,"metric")
        self.assertEqual(groups["linked_operator_yarn_groups_compared"],2)
        self.assertAlmostEqual(groups["linked_group_median_green_minus_false"],-.05)
        self.assertIsNone(groups["physical_yarn_accuracy"])


if __name__=="__main__":
    unittest.main()
