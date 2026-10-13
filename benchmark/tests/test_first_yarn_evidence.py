"""Research-only contracts and synthetic controls; no real-fabric truth asserted."""
import unittest
import numpy as np
import cv2

from benchmark.first_yarn_evidence import (
    axis_deg, axis_diff, manual_interval_pitch, crop_from_reference,
    rectify_axis, fit_from_reference, profile_peaks, diagnostic_one
)


class FirstYarnEvidenceTests(unittest.TestCase):
    def test_unsigned_axis(self):
        self.assertAlmostEqual(axis_deg([[0,0],[100,0]]),0)
        self.assertAlmostEqual(axis_deg([[5,5],[5,205]]),90)
        self.assertAlmostEqual(axis_diff(179,1),2)

    def test_manually_verified_intervals_only_in_evaluation(self):
        a=[[10,10],[410,10]]
        b=[[10,106],[410,106]]
        self.assertEqual(manual_interval_pitch(a,b,3),32)
        self.assertIsNone(manual_interval_pitch(a,b,None))

    def test_reference_crop_independent_of_holdouts(self):
        frame=np.zeros((1300,1300,3),np.uint8)
        crop, origin=crop_from_reference(frame,[[200,300],[600,400]],margin=110)
        self.assertEqual(tuple(origin),(90,190))
        self.assertEqual(crop.shape[:2],(320,620))

    def test_axis_rotation_90(self):
        frame=np.zeros((150,180,3),np.uint8)
        _,_,ref=rectify_axis(frame,[[50,10],[50,140]])
        self.assertLess(abs(ref[1,1]-ref[0,1]),1e-5)

    def test_striped_synthetic_anchor_and_holdout(self):
        h=w=460
        yy=np.arange(h,dtype=np.float32)[:,None]
        xx=np.arange(w,dtype=np.float32)[None,:]
        distance=((yy-24+16)%32)-16
        body=np.exp(-0.5*(distance/3.)**2)
        # vary yarn response along length to include approximate occlusions
        modulation=(.68+.32*np.sin(xx/35.)**2)
        image=np.clip(65+130*body*modulation,0,255).astype(np.uint8)
        bgr=cv2.merge([image,image,image])
        ann={"sample_id":"SYNTHETIC",
             "image_sha256":"synthetic","annotation_origin":"SYNTHETIC",
             "same_family_intervals":3,
             "segments":{"reference":[[45,120],[415,120]],
                         "check_same":[[40,216],[400,216]],
                         "holdout_same":[[42,312],[400,312]]}}
        result, payload=diagnostic_one(ann,bgr)
        self.assertEqual(result["status"],"CANDIDATE_LINES_NOT_PHYSICAL_PROOF",result)
        self.assertLess(result["checks"]["holdout_same"]["center_dist_to_nearest_photo_peak_px"],8,result)
        self.assertLess(result["checks"]["check_same"]["center_dist_to_nearest_photo_peak_px"],8,result)

    def test_no_yarn_flat_photo_abstains(self):
        gray=np.full((340,340,3),127,np.uint8)
        fitted,_=fit_from_reference(gray,[[50,170],[290,170]])
        self.assertEqual(fitted["status"],"ABSTAIN_REFERENCE_NOT_RIDGE_LIKE")

if __name__=="__main__":
    unittest.main()
