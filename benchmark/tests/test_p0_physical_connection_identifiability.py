"""E6.3 counterfactual graph certificate: no human-label leakage."""
import json
import tempfile
import unittest
from pathlib import Path

from benchmark.p0_physical_connection_identifiability import (
    exact_structural_identifiability,
    graph_from_fragments, maximum_cardinality,
    max_links_with_edge_forced, remove_edge_cardinality,
    posthoc_operator_confirmation,
)


def nodes(*ids):
    return [{"id":id} for id in ids]


def edges(*pairs):
    return [{"source":a,"target":b} for a,b in pairs]


class GraphIdentifiabilityTests(unittest.TestCase):
    def test_single_forced_chain_has_graph_necessary_links_not_physical_truth(self):
        f=nodes("a","b","c")
        e=edges(("a","b"),("b","c"))
        cert=exact_structural_identifiability(f,e,[("a","b")])
        self.assertEqual(cert["max_cardinality_NOT_real_yarn_count"],2)
        self.assertEqual(cert["necessary_edge_count_NOT_identity_accuracy"],2)
        self.assertFalse(cert["structural_uniqueness_cannot_certify_physical_yarn"] is False)
        self.assertEqual(cert["candidate_link_counterfactuals"][0]["alternative_target_count"],0)
        self.assertEqual(cert["candidate_link_counterfactuals"][0]["remove_edge_max_cardinality"],1)

    def test_two_competing_links_can_both_have_equal_maximum(self):
        f=nodes("a","b","x","y")
        e=edges(("a","x"),("a","y"),("b","x"),("b","y"))
        cert=exact_structural_identifiability(f,e,[("a","x"),("a","y")])
        self.assertEqual(cert["max_cardinality_NOT_real_yarn_count"],2)
        self.assertEqual(cert["necessary_edge_count_NOT_identity_accuracy"],0)
        audit=cert["candidate_link_counterfactuals"]
        self.assertTrue(all(x["forced_edge_max_cardinality"]==2 for x in audit))
        self.assertTrue(all(x["alternative_target_count"]==1 for x in audit))
        self.assertTrue(all(x["actual_physical_yarn_identity"]=="UNKNOWN" for x in audit))

    def test_candidate_graph_independent_of_candidate_order_and_operator_labels(self):
        f=nodes("a","b","x","y")
        es=edges(("a","x"),("a","y"),("b","x"),("b","y"))
        a=exact_structural_identifiability(f,es,[("a","x")])
        b=exact_structural_identifiability(f[::-1],es[::-1],[("a","x")])
        self.assertEqual(a,b)
        self.assertFalse(a["matching_graph_weak_operator_labels_used"])

    def test_invalid_nonexistent_forced_edge_is_not_fabricated(self):
        f=nodes("a","b")
        ids,ix,g=graph_from_fragments(f,edges(("a","b")))
        self.assertIsNone(max_links_with_edge_forced(g,ix["b"],ix["a"]))
        self.assertIsNone(remove_edge_cardinality(g,ix["b"],ix["a"]))
        with self.assertRaises(ValueError):
            exact_structural_identifiability(f,edges(("a","b")),[("b","a")])

    def test_empty_graph_abstains_and_does_not_make_yarns(self):
        f=nodes("a","b")
        cert=exact_structural_identifiability(f,[],[])
        self.assertEqual(cert["max_cardinality_NOT_real_yarn_count"],0)
        self.assertEqual(cert["necessary_edge_count_NOT_identity_accuracy"],0)
        self.assertEqual(cert["candidate_link_counterfactuals"],[])

    def test_posthoc_user_counterexample_does_not_change_graph_certificate(self):
        f=nodes("r0004","r0005","r0011","other")
        es=edges(("r0004","r0005"),("r0004","r0011"),
                 ("other","r0005"),("other","r0011"))
        cert=exact_structural_identifiability(f,es,[("r0004","r0005"),("r0004","r0011")])
        comp={"structure_only_consensus_UNKNOWN_PHYSICAL_IDENTITY":[["r0004","r0011"]]}
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            path=root/"datasets/physical_evidence_labels/operator_confirmations/U20261013_03_E63_counterexample.json"
            path.parent.mkdir(parents=True)
            data={"sample_id":"U20261013_03","audit_only_NOT_inference_input":True,
                  "operator_confirms_image_inferred_same_yarn":[{"source":"r0004","target":"r0005"}],
                  "operator_rejects_same_yarn":[{"source":"r0004","target":"r0011"}]}
            path.write_text(json.dumps(data),encoding="utf-8")
            post=posthoc_operator_confirmation(root,"U20261013_03",cert,comp)
            self.assertTrue(post["human_confirmation_available"])
            self.assertFalse(post["operator_positive_continuations"][0]["was_E62_consensus_link"])
            self.assertTrue(post["operator_rejected_continuations"][0]["was_E62_consensus_link"])
            self.assertTrue(post["operator_rejected_continuations"][0][
                "has_same_cardinality_alternative_under_model"])
            self.assertEqual(cert,exact_structural_identifiability(f,es,[("r0004","r0005"),("r0004","r0011")]))
            self.assertIsNone(post["independent_physical_ground_truth_accuracy"])

    def test_exhaustive_small_graph_matches_brute_maximum_cardinality(self):
        # Each link is simply an adjacency; enumerate every simple matching
        # on 3x3 to verify the exact graph solver and edge-removal logic.
        import itertools
        left=("a","b","c")
        right=("x","y","z")
        all_links=list(itertools.product(left,right))
        f=nodes(*(left+right))
        for mask in range(1<<len(all_links)):
            chosen=[e for i,e in enumerate(all_links) if (mask>>i)&1]
            cert=exact_structural_identifiability(f,edges(*chosen),chosen)
            assignments=[]
            for size in range(4):
                for sel in itertools.combinations(chosen,size):
                    if len({x for x,y in sel})==size and len({y for x,y in sel})==size:
                        assignments.append(set(sel))
            maximal=max(map(len,assignments),default=0)
            indispensable=set.intersection(*(x for x in assignments if len(x)==maximal)) if maximal else set()
            self.assertEqual(cert["max_cardinality_NOT_real_yarn_count"],maximal)
            self.assertEqual(set(map(tuple,cert["edges_necessary_in_all_max_cardinality_matchings_NOT_REAL_GT"])),
                             indispensable)


if __name__=="__main__":
    unittest.main()
