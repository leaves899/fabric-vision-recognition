from __future__ import annotations
import unittest
import numpy as np
from engine.local_yarn_tracks import trace_local_yarns, TrackSettings
from evaluate_yarn_track_identity import (evaluate_local_tracks,
                                          straight_candidate_tracks)


def yarn(track_id, xs, y_positions):
    return {"track_id":track_id,"points":[[float(x),float(y)] for x,y in zip(xs,y_positions)]}


def gt(yarn_id, x, y_positions):
    return {"id":yarn_id,"positions_by_slice":{i:float(x) for i in range(len(y_positions))},
            "sampled_points_in_tile":[[float(x),float(y)] for y in y_positions]}


class PhysicalTrackIdentityTests(unittest.TestCase):
    def test_two_distinct_physical_yarns_require_two_distinct_tracks(self):
        ys=np.linspace(40,480,7)
        truth=[gt("w10",100,ys),gt("w11",132,ys)]
        preds=[yarn("a",[100]*7,ys),yarn("b",[132]*7,ys)]
        m=evaluate_local_tracks(preds,truth,"warp",32.)
        self.assertEqual(m["matched_tracks"],2)
        self.assertEqual(m["f1"],1.)
        self.assertEqual(m["nearest_gt_id_switches_unmatched_inclusive"],0)

    def test_switching_from_one_yarn_to_another_fails_identity(self):
        ys=np.linspace(40,480,7)
        truth=[gt("w10",100,ys),gt("w11",132,ys)]
        wrong=[yarn("switch",[100,100,100,132,132,132,132],ys)]
        m=evaluate_local_tracks(wrong,truth,"warp",32.)
        self.assertEqual(m["matched_tracks"],0)
        self.assertGreater(m["nearest_gt_id_switches_unmatched_inclusive"],0)

    def test_no_duplicate_match_to_same_truth_id(self):
        ys=np.linspace(40,480,7)
        truth=[gt("w10",100,ys)]
        duplicate=[yarn("x",[99]*7,ys),yarn("y",[101]*7,ys)]
        m=evaluate_local_tracks(duplicate,truth,"warp",32.)
        self.assertEqual(m["matched_tracks"],1)
        self.assertEqual(m["predicted_tracks"],2)

    def test_straight_baseline_created_without_gt(self):
        ys=np.linspace(40,480,7)
        q=straight_candidate_tracks({"status":"PASS","center_positions_px":[101.,135.]},"warp",ys)
        self.assertEqual(len(q),2)
        self.assertEqual(len(q[0]["points"]),7)

    def test_ambiguous_blank_rt_must_abstain(self):
        tile=np.full((520,520,3),127,np.uint8)
        result=trace_local_yarns(tile,tile,"warp",27.)
        self.assertEqual(result["tracks"],[])
        self.assertNotEqual(result["status"],"PASS")

    def test_reject_nonfinite_tracks(self):
        truth=[gt("w10",100,np.linspace(40,480,7))]
        with self.assertRaises(ValueError):
            evaluate_local_tracks([yarn("nan",[float("nan")]*7,np.linspace(40,480,7))],
                                  truth,"warp",32.)


if __name__=="__main__":
    unittest.main()
