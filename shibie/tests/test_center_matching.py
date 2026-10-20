from __future__ import annotations
import unittest
import numpy as np
from evaluate_center_matching import cardinality_gated_yarn_match


class GatedPhysicalMatchTests(unittest.TestCase):
    def test_maximum_cardinality_when_counts_differ(self):
        pitch=32.
        truth=np.arange(11)*pitch+90.
        found=np.concatenate([truth+.5,np.array([23.,56.,470.])])
        score=cardinality_gated_yarn_match(found,truth,pitch)
        self.assertEqual(score["matches"],11)
        self.assertEqual(score["truth"],11)
        self.assertAlmostEqual(score["f1"],22/25)

    def test_prediction_order_does_not_change_matching(self):
        t=np.arange(10)*26.666+31.
        p=np.concatenate([t+.6,[530,580.]])
        a=cardinality_gated_yarn_match(p,t,26.666)
        b=cardinality_gated_yarn_match(p[::-1],t[::-1],26.666)
        self.assertEqual(a["matches"],b["matches"])
        self.assertEqual(a["f1"],b["f1"])

    def test_cannot_match_one_prediction_twice(self):
        r=cardinality_gated_yarn_match([23.],[23.,24.],32.)
        self.assertEqual(r["matches"],1)
        self.assertAlmostEqual(r["f1"],2/3,places=6)

    def test_bad_outlier_does_not_displace_valid_matches(self):
        t=np.arange(12)*30.
        base=cardinality_gated_yarn_match(t+.5,t,30.)
        extra=cardinality_gated_yarn_match(np.r_[t+.5,-300,900],t,30.)
        self.assertEqual(base["matches"],12)
        self.assertEqual(extra["matches"],12)

    def test_half_period_offset_is_rejected(self):
        t=np.arange(10)*32.
        p=t+16.
        s=cardinality_gated_yarn_match(p,t,32.)
        self.assertEqual(s["matches"],0)


if __name__=="__main__":
    unittest.main()
