"""E5 regression: native sampling, phase invariance and UNKNOWN control labels."""
import unittest

import cv2
import numpy as np

from benchmark.p0_cross_fabric_phase import (
    predicted_crossing_centers, oriented_energy_maps,
    local_dominance, sample_crossing_phase, fixed_phase_sensitivity_audit,
)


def cal(pitch=12.,bpitch=20.):
    return {"pitch":float(pitch),"tangent":np.array([1.,0.]),
            "normal":np.array([0.,1.]),"B_tangent":np.array([0.,1.]),
            "B_normal":np.array([-1.,0.]),
            "B_origin":np.array([40.,130.]),
            "B_pitch_signed":-float(bpitch)}


def stripes():
    """Synthetic-only crossed-color bands; *not* actual yarn occlusion GT."""
    im=np.full((280,280,3),78,np.uint8)
    cv2.rectangle(im,(0,128),(279,132),(155,155,155),-1)
    for x in range(40,221,20):
        cv2.rectangle(im,(x-2,0),(x+2,279),(220,220,220),-1)
    return im


class CrossFabricPhaseTests(unittest.TestCase):
    def test_lattice_not_a_physical_crossing_label(self):
        sites=predicted_crossing_centers([[10,130],[250,130]],cal())
        self.assertGreater(len(sites),6)
        self.assertTrue(all(isinstance(s["B_lattice_index_NOT_verified_crossing"],int)
                            for s in sites))
        self.assertTrue(all(10<=s["predicted_camera_xy"][0]<=250 for s in sites))

    def test_phase_sampler_positive_on_synthetic_crossed_bands_only(self):
        r=sample_crossing_phase(stripes(),[[10,130],[250,130]],cal())
        self.assertGreater(r["summary_A1_operator_reference"]["available_sites"],5)
        self.assertFalse(r["crossing_over_under_verified"])
        self.assertFalse(r["actual_physical_same_yarn_verified"])
        self.assertTrue(all(not s["B_lattice_site_is_verified_occlusion"] for s in r["sites"]))
        self.assertTrue(all(c["physical_class_of_both_locations"]=="UNKNOWN"
                            for s in r["sites"] for c in s["offset_A_pitch_controls"]))

    def test_change_photo_resolution_changes_pixels_not_normalized_sampling(self):
        img=stripes()
        doubled=cv2.resize(img,None,fx=2,fy=2,interpolation=cv2.INTER_NEAREST)
        a=sample_crossing_phase(img,[[10,130],[250,130]],cal())
        c=cal(24,40)
        c["B_origin"]=np.array([80.,260.])
        b=sample_crossing_phase(doubled,[[20,260],[500,260]],c)
        self.assertEqual(len(a["sites"]),len(b["sites"]))
        self.assertTrue(all(c["physical_class_of_both_locations"]=="UNKNOWN"
                            for row in b["sites"] for c in row["offset_A_pitch_controls"]))

    def test_rotate_90_degrees_preserves_phase_order(self):
        img=stripes()
        rotated=cv2.rotate(img,cv2.ROTATE_90_CLOCKWISE)
        # For an N×N source (x,y) -> (N-1-y, x)
        w=img.shape[0]
        c=cal()
        c["tangent"]=np.array([0.,1.])
        c["normal"]=np.array([-1.,0.])
        c["B_tangent"]=np.array([-1.,0.])
        c["B_normal"]=np.array([0.,-1.])
        c["B_origin"]=np.array([w-1-130.,40.])
        a=sample_crossing_phase(img,[[10,130],[250,130]],cal())
        b=sample_crossing_phase(rotated,[[w-1-130,10],[w-1-130,250]],c)
        self.assertEqual(len(a["sites"]),len(b["sites"]))
        va=a["summary_A1_operator_reference"]["median_B_dominance_phase_difference"]
        vb=b["summary_A1_operator_reference"]["median_B_dominance_phase_difference"]
        self.assertIsNotNone(va)
        self.assertIsNotNone(vb)
        self.assertLess(abs(va-vb),.075)

    def test_phase_sweep_is_symmetric_and_cannot_choose_winning_offset(self):
        result=fixed_phase_sensitivity_audit(stripes(),[[10,130],[250,130]],cal())
        self.assertEqual(result["preselected_symmetric_fractions"],[-.5,-.25,0.,.25,.5])
        self.assertEqual(len(result["curve"]),5)
        self.assertTrue(result["no_parameter_optimization_or_phase_selection"])
        self.assertFalse(result["actual_physical_crossing_certified"])
        self.assertTrue(all("best_offset" not in p for p in result["curve"]))
        self.assertTrue(all(p["proves_B_over_A"] is False for p in result["curve"]))

    def test_flat_image_returns_unknown_no_fabricated_phase(self):
        img=np.full((280,280,3),128,np.uint8)
        r=sample_crossing_phase(img,[[10,130],[250,130]],cal())
        self.assertIsNone(r["summary_A1_operator_reference"]["median_B_dominance_phase_difference"])
        self.assertEqual(r["summary_A1_operator_reference"]["available_sites"],0)

    def test_gradients_come_from_original_camera_not_enlarged_crop(self):
        img=stripes()
        a,b=oriented_energy_maps(img,[1,0],[0,1])
        self.assertEqual(a.shape,img.shape[:2])
        self.assertEqual(b.shape,img.shape[:2])
        check=local_dominance(a,b,[60,130],[1,0],12.,20.)
        self.assertIsNotNone(check)
        self.assertTrue(-1<=check["B_minus_A_normalized"]<=1)
        self.assertIsNone(local_dominance(a,b,[-2,-2],[1,0],12,20))


if __name__=="__main__":
    unittest.main()
