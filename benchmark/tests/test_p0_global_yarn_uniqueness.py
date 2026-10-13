"""E6.2 global-uniqueness invariants, synthetic—not true yarn GT."""
import copy
import unittest

from benchmark.p0_global_yarn_uniqueness import (
    APPEARANCE_METRICS, GEOMETRY_METRICS,
    ordered_preferences, naive_source_best, global_assignment,
    crossing_conflicts, compare_structures, validate_unique,
    posthoc_audit, path_components,
)


def frag(id,u0,u1,v):
    return {"id":id,"u_start":u0,"u_end":u1,
            "v_start":v,"v_end":v,"start":[u0,v],"end":[u1,v]}


def candidate(src,tgt,lateral,gap,turn=0.,appearance=0.):
    return {"source":src,"target":tgt,
            "lateral_over_pitch":lateral,
            "gap_over_pitch":gap,
            "endpoint_turn_fraction":turn,
            "profile_dissimilarity":appearance,
            "appearance_lab_delta_scaled":appearance}


class GlobalYarnUniquenessTests(unittest.TestCase):
    def test_naive_independent_nearest_can_reuse_target_but_global_cannot(self):
        fs=[frag("a",0,10,0),frag("b",0,10,4),
            frag("x",20,30,1),frag("y",20,30,9)]
        edges=[candidate("a","x",.1,1),candidate("a","y",.9,1),
               candidate("b","x",.2,1),candidate("b","y",.8,1)]
        ranks=ordered_preferences(edges,GEOMETRY_METRICS)
        naive=naive_source_best(ranks)
        self.assertEqual(naive["targets_with_multiple_predecessors"],1)
        assignment=global_assignment(fs,ranks)
        self.assertEqual(len(assignment),2)
        self.assertEqual(len({t for _,t in assignment}),2)
        self.assertTrue(validate_unique(assignment,fs))
        self.assertNotEqual(naive["excess_predecessors_dropped_by_one_to_one"],0)

    def test_forward_DAG_allows_one_in_and_one_out_at_middle(self):
        fs=[frag("a",0,10,0),frag("b",20,30,0),frag("c",40,50,0)]
        ed=[candidate("a","b",0,1),candidate("b","c",0,1),
            candidate("a","c",0,3)]
        comp=compare_structures(fs,ed)
        geometry={tuple(x) for x in comp["geometry_links"]}
        self.assertEqual(geometry,{("a","b"),("b","c")})
        self.assertTrue(comp["geometry_one_to_one"])
        self.assertEqual(path_components(fs,sorted(geometry)),[["a","b","c"]])

    def test_crossing_veto_abstains_both_links_and_keeps_unknown(self):
        fs=[frag("a",0,10,0),frag("b",0,10,10),
            frag("x",30,40,10),frag("y",30,40,0)]
        # By hypothesis appearance and geometry agree on crossing.
        ed=[candidate("a","x",0,1),candidate("b","y",0,1)]
        comp=compare_structures(fs,ed)
        self.assertEqual(comp["both_strategies_agree_links"],2)
        self.assertEqual(comp["agreed_links_in_topological_crossing"],2)
        self.assertEqual(comp["agreed_links_after_crossing_ABSTENTION"],0)
        self.assertTrue(comp["agreed_topology_conflict_free"])
        self.assertIsNone(comp["real_physical_yarn_identity_accuracy"])

    def test_disagreement_is_not_forced_unique_physical_trajectory(self):
        fs=[frag("a",0,10,0),frag("b",0,10,8),
            frag("x",20,30,0),frag("y",20,30,8)]
        ed=[candidate("a","x",.01,1,appearance=.95),
            candidate("a","y",2,1,appearance=.01),
            candidate("b","x",2,1,appearance=.01),
            candidate("b","y",.01,1,appearance=.95)]
        comp=compare_structures(fs,ed)
        self.assertEqual(comp["global_geometry_links_FORCED_HYPOTHESES"],2)
        self.assertEqual(comp["global_appearance_links_FORCED_HYPOTHESES"],2)
        self.assertEqual(comp["agreed_links_after_crossing_ABSTENTION"],0)
        self.assertIsNone(comp["real_physical_yarn_identity_accuracy"])

    def test_missing_image_cues_never_fill_with_zero(self):
        fs=[frag("a",0,10,0),frag("b",20,30,0)]
        ed=[candidate("a","b",.2,1)]
        ed[0]["profile_dissimilarity"]=None
        self.assertEqual(len(ordered_preferences(ed,GEOMETRY_METRICS)),1)
        self.assertEqual(len(ordered_preferences(ed,APPEARANCE_METRICS)),0)
        comp=compare_structures(fs,ed)
        self.assertEqual(comp["geometry_ranks_available"],1)
        self.assertEqual(comp["appearance_ranks_available"],0)
        self.assertEqual(comp["both_strategies_agree_links"],0)
        self.assertEqual(comp["agreed_links_after_crossing_ABSTENTION"],0)

    def test_absolute_resolution_and_quarter_turn_do_not_change_precomputed_dimensionless_ranks(self):
        # Evidence already in source-aligned, pitch-normalized u,v frame.
        # E4 runs its own 90deg and resolution tests before these graph steps.
        fs=[frag("a",0,10,0),frag("b",20,30,0),frag("c",20,30,6)]
        ed=[candidate("a","b",0,1),candidate("a","c",.6,1)]
        baseline=compare_structures(fs,ed)
        rotated_scaled=[frag("a",100,140,90),frag("b",180,220,90),
                        frag("c",180,220,114)]
        same=compare_structures(rotated_scaled,copy.deepcopy(ed))
        self.assertEqual(baseline["geometry_links"],same["geometry_links"])
        self.assertEqual(baseline["appearance_links"],same["appearance_links"])

    def test_posthoc_same_relations_never_influence_global_solution(self):
        fs=[frag("a",0,10,0),frag("x",20,30,0),frag("y",20,30,2)]
        ed=[candidate("a","x",0,1),candidate("a","y",.2,1)]
        before=compare_structures(fs,ed)
        r1={"relations":[{"a":"a","b":"x","relation":"SAME_PHYSICAL_YARN"}]}
        r2={"relations":[{"a":"a","b":"y","relation":"SAME_PHYSICAL_YARN"}]}
        audit1=posthoc_audit(before,r1,fs)
        audit2=posthoc_audit(before,r2,fs)
        after=compare_structures(fs,ed)
        self.assertEqual(before,after)
        self.assertNotEqual(audit1["operator_link_directly_in_forced_geometry"],
                            audit2["operator_link_directly_in_forced_geometry"])
        self.assertIsNone(audit1["independent_physical_yarn_identity_accuracy"])
        self.assertTrue(audit2["operator_absent_links_are_not_independent_NEGATIVE_truth"])

    def test_empty_candidates_abstain_all_structural_hypotheses(self):
        fs=[frag("a",0,10,0),frag("b",20,30,0)]
        v=compare_structures(fs,[])
        self.assertEqual(v["agreed_links_after_crossing_ABSTENTION"],0)
        self.assertEqual(len(v["structure_only_candidate_paths_NOT_REAL_YARN_COUNTS"]),2)
        self.assertTrue(v["geometry_one_to_one"])
        self.assertTrue(v["appearance_one_to_one"])


if __name__=="__main__":
    unittest.main()
