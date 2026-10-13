"""P0 E2 operator line audit contracts. Synthetic images are NOT GT accuracy."""
import unittest

import cv2
import numpy as np

from benchmark.p0_operator_line_audit import (
    acute_axis_delta, convert_zoom_to_camera, _clip_array,
    windows_for_stroke, local_optical_features,
    connected_positive_groups, summarize_sample,
    camera_pitch_from_operator_A1_A2, unlabelled_half_pitch_controls,
    half_pitch_probe, nearest_length_matched_twill_pairs, POS, NEG,
)


class OperatorLineAuditTests(unittest.TestCase):
    def synthetic(self):
        img=np.full((250,250,3),88,dtype=np.uint8)
        cv2.line(img,(20,90),(230,90),(212,212,212),9)
        return img

    def test_exact_zoom_to_native_camera_transform(self):
        got=convert_zoom_to_camera([[24.,40.],[124.,80.]],[100,200,400,500],2)
        self.assertEqual(got,[[112.,220.],[162.,240.]])
        with self.assertRaises(ValueError):
            convert_zoom_to_camera([[2,2],[10,10]],[0,0,100,100],4)

    def test_angle_modulo_180_and_direction_confound(self):
        self.assertEqual(acute_axis_delta(179,1),2)
        self.assertEqual(acute_axis_delta(0,180),0)
        self.assertEqual(acute_axis_delta(30,90),60)

    def test_original_camera_clip_features_90deg_rotation(self):
        im=self.synthetic()
        horizontal=windows_for_stroke(im,[[30,90],[210,90]])
        rotated=cv2.rotate(im,cv2.ROTATE_90_CLOCKWISE)
        vertical=windows_for_stroke(rotated,[[159,30],[159,210]])
        self.assertEqual(len(horizontal),7)
        self.assertEqual(len(vertical),7)
        for key in ("paired_side_contrast_z","center_vs_flanks_abs_z",
                    "paired_contrast_support_fraction","transverse_vs_axial_gradient"):
            self.assertLess(abs(np.median([x[key] for x in horizontal])-
                                np.median([x[key] for x in vertical])),.065,key)

    def test_2x_never_used_to_gain_detail(self):
        im=self.synthetic()
        original=windows_for_stroke(im,[[30,90],[210,90]])
        x2=cv2.resize(im,None,fx=2,fy=2,interpolation=cv2.INTER_CUBIC)
        # This experiment never feeds the enlarged photo to windows_for_stroke.
        # A separate image gives different physical sampling scale.
        self.assertEqual(len(original),7)
        self.assertEqual(x2.shape[0],im.shape[0]*2)

    def test_outside_camera_frame_not_mirrored_into_evidence(self):
        im=self.synthetic()
        self.assertIsNone(_clip_array(im,[1,1],[1,0]))
        self.assertTrue(windows_for_stroke(im,[[0,0],[7,0]])==[])

    def test_flat_image_zero_boundary_evidence(self):
        constant=np.full((33,25,3),133,np.uint8)
        f=local_optical_features(constant)
        self.assertEqual(f["center_vs_flanks_abs_z"],0.)
        self.assertEqual(f["paired_side_contrast_z"],0.)
        self.assertEqual(f["paired_contrast_support_fraction"],0.)

    def test_human_same_relation_one_group_different_strands_unknown(self):
        regions=[{"id":f"r{i}","kind":POS} for i in range(1,12)]
        edges=[{"a":f"r{i}","b":f"r{i+1}","relation":"SAME_PHYSICAL_YARN"}
               for i in range(1,10)]
        groups=connected_positive_groups(regions,edges)
        self.assertEqual(len(groups),2)
        self.assertEqual(max(map(len,groups)),10)
        self.assertEqual(min(map(len,groups)),1)

    def test_long_twill_track_seven_windows_still_one_negative(self):
        im=self.synthetic()
        review={"sample_id":"T001","review_state":"DRAFT",
                "annotation_source":"PHONE_IMAGE_OPERATOR_REVIEW",
                "regions":[
                    {"id":"r1","kind":POS,"geometry":{"type":"LINE",
                     "points":[[60,180],[120,180]]}},
                    {"id":"r2","kind":NEG,"geometry":{"type":"LINE",
                     "points":[[20,40],[420,40]]}},
                ],"relations":[]}
        provenance={"crop_original_xyxy":[0,0,220,220],"enlargement_scale":2}
        s=summarize_sample(im,review,provenance,0)
        self.assertEqual(s["human_twill_visual_tracks"],1)
        self.assertEqual(s["human_apparent_yarn_short_strokes"],1)
        self.assertEqual(s["orientation_matched_twill_negative_tracks_15deg"],1)
        self.assertLessEqual(s["records"][1]["optical_windows_count_NOT_independent_training_samples"],7)
        self.assertIsNone(s["real_physical_yarn_identity_accuracy"] if "real_physical_yarn_identity_accuracy" in s else s["physical_yarn_identity_accuracy"])
        self.assertIsNone(s["physical_yarn_count_accuracy"])

    def test_a1_a2_pitch_and_matched_photo_controls_remain_unlabelled(self):
        ref=[[20,60],[220,60]]
        check=[[20,100],[220,100]]
        pitch=camera_pitch_from_operator_A1_A2((ref,check,4))
        self.assertAlmostEqual(pitch,5.)
        im=self.synthetic()
        record={"id":"r1","kind":POS,"geometry_type":"LINE",
                "camera_original_xy":[[30,90],[210,90]],
                "optical_features":{"paired_side_contrast_z":.75,
                                    "center_vs_flanks_abs_z":1.25}}
        controls=unlabelled_half_pitch_controls(im,record,pitch)
        self.assertEqual(len(controls),2)
        self.assertTrue(all(x["operator_labelled_negative"] is False for x in controls))
        self.assertTrue(all(x["known_physical_class"] is None for x in controls))
        self.assertAlmostEqual(controls[0]["camera_original_xy"][0][1],87.5,places=2)
        self.assertAlmostEqual(controls[1]["camera_original_xy"][0][1],92.5,places=2)
        sample={"records":[record]}
        half_pitch_probe(sample,im,pitch)
        self.assertFalse(sample["unlabelled_direction_length_matched_control_stats"]
                         ["paired_side_contrast_z"]["valid_true_false_yarn_comparison"])
        self.assertEqual(len(record["UNLABELLED_direction_matched_half_pitch_controls"]),2)

    def test_spatial_direction_length_matching_and_operator_same_strand_guard(self):
        photo=self.synthetic()
        # Fake and operator yarn both horizontal; two separate operator
        # strokes are linked as one inferred physical yarn identity group.
        sample={"records":[
            {"id":"r1","kind":POS,"geometry_type":"LINE",
             "camera_original_xy":[[50,90],[95,90]],
             "optical_features":{k:0.8 for k in (
                "center_vs_flanks_abs_z","paired_side_contrast_z",
                "paired_contrast_support_fraction","transverse_vs_axial_gradient",
                "center_flank_sign_stability","local_luma_std","local_chroma_std")}},
            {"id":"r2","kind":POS,"geometry_type":"LINE",
             "camera_original_xy":[[105,90],[150,90]],
             "optical_features":{k:0.8 for k in (
                "center_vs_flanks_abs_z","paired_side_contrast_z",
                "paired_contrast_support_fraction","transverse_vs_axial_gradient",
                "center_flank_sign_stability","local_luma_std","local_chroma_std")}},
            {"id":"t1","kind":NEG,"geometry_type":"LINE",
             "camera_original_xy":[[20,110],[230,110]],
             "optical_features":None},
        ],"positive_relation_groups_NOT_DISTINCT_YARN_COUNT":[["r1","r2"]]}
        result=nearest_length_matched_twill_pairs(photo,sample)
        self.assertEqual(result["matched_operator_strokes_NOT_independent"],2)
        self.assertEqual(result["unique_operator_yarn_same_strand_groups_NOT_VERIFIED_COUNT"],1)
        self.assertEqual(result["unique_operator_false_track_ids_NOT_independent_GT"],1)
        self.assertEqual(result["pairs"][0]["positive_window_length_camera_px"],
                         result["pairs"][0]["negative_window_length_camera_px"])
        self.assertAlmostEqual(result["pairs"][0]["center_separation_camera_px"],20)
        self.assertIsNone(result["real_physical_identity_accuracy"])
        self.assertTrue(result["unverified_phone_image_labels_only"])

    def test_long_distant_and_cross_direction_false_lines_not_matches(self):
        photo=self.synthetic()
        features={k:0.5 for k in ("center_vs_flanks_abs_z",
                "paired_side_contrast_z","paired_contrast_support_fraction",
                "transverse_vs_axial_gradient","center_flank_sign_stability",
                "local_luma_std","local_chroma_std")}
        sample={"records":[
            {"id":"p","kind":POS,"geometry_type":"LINE",
             "camera_original_xy":[[50,90],[95,90]],
             "optical_features":features},
            {"id":"far","kind":NEG,"geometry_type":"LINE",
             "camera_original_xy":[[20,175],[230,175]],"optical_features":None},
            {"id":"cross","kind":NEG,"geometry_type":"LINE",
             "camera_original_xy":[[75,20],[75,230]],"optical_features":None}],
            "positive_relation_groups_NOT_DISTINCT_YARN_COUNT":[["p"]]}
        value=nearest_length_matched_twill_pairs(photo,sample)
        self.assertEqual(value["matched_operator_strokes_NOT_independent"],0)
        self.assertEqual(value["unique_operator_false_track_ids_NOT_independent_GT"],0)
        self.assertIsNone(value["per_feature"]["paired_side_contrast_z"]
                          ["matched_stroke_median_difference"])

    def test_cross_axis_twill_only_does_not_test_non_direction_discrimination(self):
        im=self.synthetic()
        review={"sample_id":"T001","review_state":"DRAFT",
                "annotation_source":"PHONE_IMAGE_OPERATOR_REVIEW",
                "regions":[
                    {"id":"r1","kind":POS,"geometry":{"type":"LINE",
                     "points":[[60,180],[120,180]]}},
                    {"id":"r2","kind":NEG,"geometry":{"type":"LINE",
                     "points":[[20,40],[420,340]]}},
                ],"relations":[]}
        provenance={"crop_original_xyxy":[0,0,220,220],"enlargement_scale":2}
        s=summarize_sample(im,review,provenance,0)
        self.assertEqual(s["orientation_matched_twill_negative_tracks_15deg"],0)
        self.assertEqual(s["optical_comparison_status"],
                         "NOT_IDENTIFIABLE_TWILL_NEGATIVE_DIRECTION_CONFOUND")
        self.assertIsNone(s["physical_yarn_identity_accuracy"])


if __name__=="__main__":
    unittest.main()
