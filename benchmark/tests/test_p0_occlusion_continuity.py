"""Synthetic E4 contracts: no fixed pixel gate, A3 or human relation leakage."""
import copy
import unittest

import numpy as np

from benchmark.p0_occlusion_continuity import (
    calibration_fields, create_fragments, morphology_pair,
    propose_candidates, rank_evidence, audit_operator_connections,
    endpoint_signature, predicted_B_crossing,
)


def reference():
    return {
        "segments":{
            "reference":[[20,100],[220,100]],
            "check_same":[[20,160],[220,160]],
            "holdout_same":[[15,200],[215,200]],
            "check_cross":[[80,0],[80,240]],
            "check_cross_second":[[140,0],[140,240]],
        },
        "same_family_intervals":3,
        "same_family_intervals_confirmed":True,
        "cross_family_intervals":2,
        "cross_family_intervals_confirmed":True,
    }


def makef(id,x0,x1,y,pitch=10,signature=None):
    return {"id":id,"start":[x0,y],"end":[x1,y],
            "u_start":x0,"u_end":x1,"v_start":y,"v_end":y,
            "direction":[1.,0.],"camera_length":x1-x0,
            "start_signature":signature,"end_signature":signature}


def mockcal(pitch=10):
    return {"pitch":float(pitch),"tangent":np.array([1.,0.]),
            "normal":np.array([0.,1.]),
            "B_normal":np.array([-1.,0.]),
            "B_tangent":np.array([0.,1.]),
            "B_origin":np.array([80.,0.]),"B_pitch_signed":-30.,
            "uses_A3_holdout":False}


class OcclusionContinuityTests(unittest.TestCase):
    def test_no_absolute_pixel_distance_gate_even_when_large_gap(self):
        f=[makef("r1",0,15,0),makef("r2",80,90,0),
           makef("r3",80,90,5)]
        edges=propose_candidates(f,mockcal())
        self.assertEqual(len(edges),2)
        self.assertEqual({e["target"] for e in edges},{"r2","r3"})
        self.assertGreater(edges[0]["gap_over_pitch"],5)
        self.assertTrue(all(e["real_physical_same_yarn_probability"] is None for e in edges))

    def test_change_resolution_preserves_normalized_geometry(self):
        a=propose_candidates([makef("a",0,16,2),makef("b",40,60,5)],mockcal(12))[0]
        b=propose_candidates([makef("a",0,64,8),makef("b",160,240,20)],mockcal(48))[0]
        for key in ("gap_over_pitch","lateral_over_pitch","endpoint_turn_fraction"):
            self.assertAlmostEqual(a[key],b[key])

    def test_90_degree_rotation_keeps_normalized_evidence(self):
        f=[makef("a",0,16,2),makef("b",40,60,5)]
        base=propose_candidates(f,mockcal(12))[0]
        # After rotating image 90°, the along-y A tangent is still
        # the same abstract local coordinates u and v.
        cal=mockcal(12)
        cal["tangent"]=np.array([0.,1.])
        cal["normal"]=np.array([-1.,0.])
        cal["B_origin"]=np.array([0.,80.])
        cal["B_normal"]=np.array([0.,-1.])
        rf=[]
        for it in f:
            rr=copy.deepcopy(it)
            rr["start"]=[-it["start"][1],it["start"][0]]
            rr["end"]=[-it["end"][1],it["end"][0]]
            rr["direction"]=[0.,1.]
            rf.append(rr)
        rotated=propose_candidates(rf,cal)[0]
        for key in ("gap_over_pitch","lateral_over_pitch","endpoint_turn_fraction"):
            self.assertAlmostEqual(base[key],rotated[key])

    def test_inference_never_reads_human_relation(self):
        photo=np.full((250,250,3),125,np.uint8)
        review={"regions":[
            {"id":"r1","kind":"APPARENT_VISIBLE_YARN","geometry":{
                "type":"LINE","points":[[20,100],[70,100]]}},
            {"id":"r2","kind":"APPARENT_VISIBLE_YARN","geometry":{
                "type":"LINE","points":[[130,100],[180,100]]}},
            {"id":"r3","kind":"APPARENT_VISIBLE_YARN","geometry":{
                "type":"LINE","points":[[130,140],[180,140]]}},
        ],"relations":[{"a":"r1","b":"r2","relation":"SAME_PHYSICAL_YARN"}]}
        provenance={"crop_original_xyxy":[0,0,250,250],"enlargement_scale":2}
        cal=mockcal(10)
        a=create_fragments(photo,review,provenance,cal)
        edges=rank_evidence(propose_candidates(a,cal))
        changed=copy.deepcopy(review)
        changed["relations"]=[{"a":"r1","b":"r3","relation":"SAME_PHYSICAL_YARN"}]
        b=create_fragments(photo,changed,provenance,cal)
        independent=rank_evidence(propose_candidates(b,cal))
        self.assertEqual(edges,independent)
        audit1=audit_operator_connections(edges,review["relations"],a)
        audit2=audit_operator_connections(edges,changed["relations"],a)
        self.assertNotEqual(audit1["operator_links"],audit2["operator_links"])
        self.assertEqual(audit1["operator_linked_component_count_NOT_PHYSICAL_YARN_COUNT"],2)
        geom=audit1["per_cue_operator_relation_competition_DIAGNOSTIC_ONLY"]["gap_over_pitch"]
        self.assertEqual(geom["operator_links_scored_NOT_independent_GT"],1)
        self.assertTrue(geom["not_a_true_false_classification_metric"])
        self.assertEqual(geom["distinct_operator_same_groups_scored"],1)
        self.assertTrue(all(e["inference_identity_status"]=="UNKNOWN" for e in edges))

    def test_unlinked_competitor_not_fake_negative(self):
        f=[makef("start",10,30,0),makef("other",40,60,15),
           makef("same",40,60,0)]
        edges=rank_evidence(propose_candidates(f,mockcal()))
        candidates=[x for x in edges if x["source"]=="start"]
        self.assertEqual(len(candidates),2)
        self.assertTrue(all(x["unknown_alternative_NOT_negative_GT"] for x in candidates))
        self.assertTrue(all(x["real_physical_same_yarn_probability"] is None for x in candidates))
        self.assertLess(next(x["lateral_over_pitch"] for x in candidates if x["target"]=="same"),
                        next(x["lateral_over_pitch"] for x in candidates if x["target"]=="other"))

    def test_holdout_a3_prohibited_from_scoring(self):
        a=reference()
        other=copy.deepcopy(a)
        other["segments"]["holdout_same"]=[[99999,90000],[-2,-8]]
        self.assertEqual(calibration_fields(a)["pitch"],calibration_fields(other)["pitch"])
        self.assertTrue(np.array_equal(calibration_fields(a)["B_origin"],
                                       calibration_fields(other)["B_origin"]))
        self.assertFalse(calibration_fields(a)["uses_A3_holdout"])

    def test_B_crossing_is_only_a_geometric_hypothesis(self):
        c=mockcal()
        i=makef("a",50,70,0)
        j=makef("b",100,120,0)
        out=predicted_B_crossing(i,j,c)
        self.assertGreaterEqual(out["expected_B_lattice_intersections_NOT_physical_GT"],1)
        self.assertFalse(out["verified_actual_over_under"])
        self.assertFalse(out["verified_physical_occlusion"])

    def test_b_reference_crop_offset_applied(self):
        c=calibration_fields(reference(),original_camera_crop_origin=(250,310))
        # Zoom B1 x=80 -> camera x=290 including crop x0 250.
        self.assertAlmostEqual(c["B_origin"][0],290)
        self.assertAlmostEqual(c["B_origin"][1],370)
        self.assertAlmostEqual(c["pitch"],10)

    def test_missing_image_profile_cannot_be_scored_as_zero(self):
        a={"lab":[120,128,128],"luma_profile":[90,100,110],
           "local_luma_spread":5}
        result=morphology_pair(a,None)
        self.assertIsNone(result["profile_dissimilarity"])
        self.assertIsNone(result["appearance_lab_delta_scaled"])
        e=rank_evidence(propose_candidates([makef("a",0,20,2),
                                           makef("b",40,60,3)],mockcal()))[0]
        self.assertIsNone(e["rank_among_all_forward_alternatives"]["profile_dissimilarity"])
        self.assertIsNone(e["pareto_dominated"])

    def test_end_signature_uses_visible_fragment_pixels_not_gap(self):
        img=np.full((160,160,3),90,np.uint8)
        img[70:76,20:100]=230
        sig=endpoint_signature(img,[28,72],[1,0],40,18,+1)
        self.assertIsNotNone(sig)
        self.assertLess(sig["camera_endpoint"][0],40)
        self.assertEqual(len(sig["luma_profile"]),17)


if __name__=="__main__":
    unittest.main()
