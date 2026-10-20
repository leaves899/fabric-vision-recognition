from __future__ import annotations
import unittest
import numpy as np
from evaluate_strict_yarn_identity import strict_trajectory_id_match


class StrictIdTests(unittest.TestCase):
    def setUp(self):
        ys=np.linspace(35,485,7)
        self.y=ys
        self.truth=[
          {"id":name,"sampled_points_in_tile":[[float(x),float(y)] for y in ys]}
          for name,x in (("warp-A",100.),("warp-B",132.))
        ]

    def _track(self, xs):
        return [{"track_id":"candidate","points":[[float(x),float(y)]
            for x,y in zip(xs,self.y)]}]

    def test_perfect_local_entity_scores_one_if_only_one_truth(self):
        result=strict_trajectory_id_match(self._track([100]*7),self.truth[:1],"warp",32.)
        self.assertEqual(result["matched_physical_ids"],1)
        self.assertEqual(result["f1"],1.)

    def test_switch_one_of_seven_points_is_rejected(self):
        # The OLD permissive matcher would have accepted 6 of 7 as same ID;
        # physical identity cannot swap to a second confirmed yarn and back.
        q=strict_trajectory_id_match(self._track([100]*6+[132]),self.truth,"warp",32.)
        self.assertEqual(q["matched_physical_ids"],0)
        self.assertGreater(q["nearest_id_switch_events"],0)

    def test_blank_unmatched_point_is_not_a_different_physical_id(self):
        result=strict_trajectory_id_match(self._track([100]*6+[114]),self.truth[:1],"warp",32.)
        self.assertEqual(result["matched_physical_ids"],1)

    def test_duplicate_candidates_not_matched_to_same_gt_twice(self):
        xs=[{"track_id":name,"points":[[float(x),float(y)]
             for y in self.y]} for name,x in (("one",100.),("two",101.))]
        q=strict_trajectory_id_match(xs,self.truth[:1],"warp",32.)
        self.assertEqual(q["matched_physical_ids"],1)
        self.assertEqual(q["proposed_tracks"],2)


if __name__=="__main__":
    unittest.main()
