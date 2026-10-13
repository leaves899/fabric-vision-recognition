"""G1.3 synthetic contracts, NOT physical-yarn-identity accuracy tests."""
import unittest
import numpy as np
from benchmark.v51_g13_assisted_lattice import assisted_first_family,candidate_gap_count

def tracks():
    return [[[15.,float(20+15*k)],[220.,float(20+15*k)]]
            for k in range(12)]
def A(y):
    return [[45.,float(y)],[180.,float(y)]]

class AssistedTests(unittest.TestCase):
    def test_equal_intervals_preserves_population(self):
        t=tracks()
        result,diag=assisted_first_family(t,A(35),A(65),physical_intervals=2,confirmed=True)
        self.assertEqual(len(result),len(t))
        self.assertEqual(diag["operator_physical_yarn_intervals"],2)
        self.assertTrue(diag["A3_used_in_inference"] is False)

    def test_unconfirmed_abstains(self):
        t=tracks()
        result,diag=assisted_first_family(t,A(35),A(65),physical_intervals=2,confirmed=False)
        self.assertEqual(result,t)
        self.assertEqual(diag["status"],"ABSTAINED")

    def test_missing_intervals_do_not_invent_yarns(self):
        t=tracks()
        result,diag=assisted_first_family(t,A(35),A(65),physical_intervals=5,confirmed=True)
        self.assertEqual(result,t)
        self.assertEqual(diag["reason"],"MISSING_REAL_YARN_INTERVAL_CANDIDATES_NO_INTERPOLATION")

    def test_index_spacing_has_no_holdout_argument(self):
        t=tracks()
        self.assertEqual(candidate_gap_count(t,A(35),A(65)),2)

if __name__=="__main__":unittest.main()
