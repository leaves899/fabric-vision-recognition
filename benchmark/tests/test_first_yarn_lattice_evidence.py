"""Synthetic controls for physically indexed A1+A2 image evidence.

Synthetic stripes are not real-yarn recognition accuracy. A3 is strictly held
out, even when changed to an intentionally conflicting location.
"""
import unittest
import cv2
import numpy as np

from benchmark.first_yarn_lattice_evidence import infer_lattice, check_a3_holdout


def stripes():
    y=np.arange(560,dtype=np.float32)[:,None]
    x=np.arange(560,dtype=np.float32)[None,:]
    d=(y-16+16)%32-16
    lines=np.exp(-.5*(d/4)**2)*(.80+.20*np.cos(x/31)**2)
    gray=np.uint8(np.clip(70+155*lines,0,255))
    return cv2.merge([gray,gray,gray])


def annotation():
    return {
        "annotation_target":"PHYSICAL_YARN_REFERENCE",
        "segments":{"reference":[[30,80],[530,80]],
                    "check_same":[[30,240],[530,240]],
                    "holdout_same":[[30,336],[530,336]],
                    "check_cross":None,"check_cross_second":None},
        "same_family_intervals":5,
        "same_family_intervals_confirmed":True,
    }


def prepared(image):
    detector={"status":"IMAGE_TEXTURE_RIDGE_CANDIDATES_REQUIRE_YARN_CONFIRMATION",
              "selected_channel":"L","selected_polarity":"light",
              "selected_cross_scale_px":5}
    affine=np.array([[1.,0,0],[0,1.,0]])
    return detector,(image,np.arange(16,560,32),affine,np.array([0,0]))


class FirstYarnLatticeEvidenceTests(unittest.TestCase):
    def test_physical_pitch_and_image_only_supported_candidate_not_real_yarn(self):
        image=stripes()
        lattice,visual=infer_lattice(image,annotation(),prepared=prepared(image))
        self.assertEqual(lattice["nominal_physical_pitch_2x_px"],32)
        self.assertGreaterEqual(lattice["longitudinal_image_supported_site_count_NOT_actual_yarn_count"],8)
        self.assertEqual(lattice["status"],
                         "IMAGE_SUPPORTED_PHYSICAL_LATTICE_HYPOTHESIS_NOT_IDENTIFIED_YARNS")
        self.assertIsNone(lattice["verified_real_yarn_count"])
        self.assertIsNone(lattice["density_per_cm"])
        self.assertTrue(all(s["confirmed_actual_physical_yarn"] is False for s in lattice["sites"]))
        held=check_a3_holdout(annotation(),lattice,visual)
        self.assertEqual(held["status"],"APPROXIMATE_GEOMETRY_MATCH")
        self.assertFalse(held["used_for_calibration"])

    def test_changed_a3_cannot_change_any_inference_or_parameters(self):
        image=stripes()
        a=annotation()
        lattice,visual=infer_lattice(image,a,prepared=prepared(image))
        old=check_a3_holdout(a,lattice,visual)
        a["segments"]["holdout_same"]=[[30,349],[530,349]]
        changed,_=infer_lattice(image,a,prepared=prepared(image))
        new=check_a3_holdout(a,changed,visual)
        self.assertEqual(changed,lattice)
        self.assertNotEqual(new["holdout_residual_fraction_pitch"],
                            old["holdout_residual_fraction_pitch"])

    def test_occlusion_and_random_dots_do_not_certify_physical_yarns(self):
        blank=np.full((560,560,3),110,np.uint8)
        result,_=infer_lattice(blank,annotation(),prepared=prepared(blank))
        self.assertEqual(result["status"],"ABSTAIN_UNSTABLE_IMAGE_SUPPORT")
        self.assertEqual(result["longitudinal_image_supported_site_count_NOT_actual_yarn_count"],0)
        self.assertIsNone(result["verified_real_yarn_count"])

    def test_photo_90_degree_rotation_same_lattice_if_affine_correct(self):
        original=stripes()
        clockwise=cv2.rotate(original,cv2.ROTATE_90_CLOCKWISE)
        data=annotation()
        for role in ("reference","check_same","holdout_same"):
            data["segments"][role]=[[559-y,x] for x,y in data["segments"][role]]
        det,(_,peaks,_,_)=prepared(original)
        affine=np.array([[0.,1.,0.],[-1.,0.,559.]])
        rotated_visual=(original,peaks,affine,np.array([0,0]))
        out,_=infer_lattice(clockwise,data,prepared=(det,rotated_visual))
        orig,_=infer_lattice(original,annotation(),prepared=prepared(original))
        self.assertEqual(out["nominal_physical_pitch_2x_px"],
                         orig["nominal_physical_pitch_2x_px"])
        self.assertEqual(out["longitudinal_image_supported_site_count_NOT_actual_yarn_count"],
                         orig["longitudinal_image_supported_site_count_NOT_actual_yarn_count"])

    def test_unconfirmed_physical_intervals_and_small_pitch_rejected(self):
        image=stripes()
        ann=annotation()
        ann["same_family_intervals_confirmed"]=False
        result,_=infer_lattice(image,ann,prepared=prepared(image))
        self.assertEqual(result["status"],"ABSTAIN_UNCONFIRMED_DISTINCT_PHYSICAL_ANCHORS")
        ann["same_family_intervals_confirmed"]=True
        ann["same_family_intervals"]=40
        result,_=infer_lattice(image,ann,prepared=prepared(image))
        self.assertEqual(result["status"],"ABSTAIN_INSUFFICIENT_NATIVE_PITCH_RESOLUTION")

    def test_texture_band_false_positive_is_still_not_identity_truth(self):
        # A perfectly periodic *printed* stripe can pass all optical tests.
        # That is deliberately NOT called a real physical yarn.
        im=stripes()
        candidate,_=infer_lattice(im,annotation(),prepared=prepared(im))
        self.assertGreater(candidate["longitudinal_image_supported_site_count_NOT_actual_yarn_count"],0)
        self.assertIsNone(candidate["verified_real_yarn_count"])
        self.assertFalse(any(s["confirmed_actual_physical_yarn"] for s in candidate["sites"]))


if __name__=="__main__":
    unittest.main()
