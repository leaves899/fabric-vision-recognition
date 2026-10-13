"""Strict E6.3b optical observation contract and falsification fixtures."""
import unittest
import numpy as np
from benchmark.p0_native_occlusion_audit import observe_gap, audit_alternatives

class NativeObservationTests(unittest.TestCase):
    def setUp(self):
        self.src={"id":"s","end":[25., 30.]}
        self.dst={"id":"t","start":[75., 30.]}

    def test_uniform_photo_not_promoted_to_yarn(self):
        x=np.full((100,100,3),120,dtype=np.uint8)
        r=observe_gap(x,self.src,self.dst,10.)
        self.assertEqual(r["status"],"DESCRIPTIVE_ONLY")
        self.assertEqual(r["physical_identity"],"UNKNOWN")
        self.assertIsNone(r["observed_over_under"])
        self.assertTrue(all(s["cross_section_range"]==0 for s in r["sections"]))

    def test_optical_boundary_still_not_physical_certificate(self):
        x=np.zeros((100,100,3),dtype=np.uint8)
        x[30:,:,:]=255
        r=observe_gap(x,self.src,self.dst,10.)
        self.assertGreater(max(s["cross_section_range"] for s in r["sections"]),0)
        self.assertFalse(r["physical_boundary_termination_verified"])
        self.assertIsNone(r["observed_over_under"])

    def test_out_of_frame_is_missing_not_zero(self):
        a={"end":[3.,3.]}
        b={"start":[6.,3.]}
        r=observe_gap(np.zeros((20,20,3),np.uint8),a,b,20.)
        self.assertEqual(r["valid_section_count"],0)
        self.assertIsNone(r["sections"][0]["cross_section_range"])

    def test_order_independent_alternatives_and_no_auto_selection(self):
        im=np.full((100,100,3),100,dtype=np.uint8)
        f=[{"id":"s","end":[25,30]},{"id":"t","start":[75,30]},
           {"id":"u","start":[75,35]}]
        a=audit_alternatives(im,f,[("s","u"),("s","t")],10)
        b=audit_alternatives(im,f[::-1],[("s","t"),("s","u")],10)
        self.assertEqual(a,b)
        self.assertEqual(a["automatically_confirmed_physical_connections"],0)

    def test_invalid_camera_or_pitch_refused(self):
        with self.assertRaises(ValueError):
            observe_gap(np.zeros((10,10),np.uint8),self.src,self.dst,10)
        with self.assertRaises(ValueError):
            observe_gap(np.zeros((100,100,3),np.uint8),self.src,self.dst,0)

if __name__=="__main__":
    unittest.main()
