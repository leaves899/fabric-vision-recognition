"""Small contract tests for research candidate detector; no accuracy GT invented."""
import unittest
import numpy as np
from benchmark.orthogonal_evidence import axis_deg, diff180, get_roi, pitch_from_manual, detect, cross_pitch_candidates


class OrthogonalEvidenceTests(unittest.TestCase):
    def test_axial_direction_wrap(self):
        self.assertAlmostEqual(axis_deg([[0,0],[100,0]]),0)
        self.assertAlmostEqual(axis_deg([[10,10],[10,110]]),90)
        self.assertAlmostEqual(diff180(179,1),2)
        self.assertAlmostEqual(diff180(1,179),2)

    def test_pitch_geometry_uses_declared_interval_not_euclidean_line_length(self):
        a=[[100,10],[100,100]]
        b=[[140,10],[140,100]]
        self.assertEqual(pitch_from_manual(a,b,90,4),10.)
        self.assertIsNone(pitch_from_manual(a,b,90,0))

    def test_roi_uses_first_reference_only(self):
        img=np.zeros((1200,1200,3),np.uint8)
        roi,orig=get_roi(img,[[650,700],[650,950]],side=500)
        self.assertEqual(roi.shape,(500,500,3))
        self.assertEqual(orig,(400,575))

    def test_one_dimensional_period_hypotheses_on_synthetic_stripes(self):
        import cv2
        yy=np.arange(480,dtype=np.float32)[:,None]
        phase=(2*np.pi/32)*yy
        shade=(120+46*np.sin(phase)).astype(np.uint8)
        img=np.repeat(shade,480,axis=1)
        bgr=cv2.merge([img,img,img])
        found=cross_pitch_candidates(bgr,90)
        candidates=[r["period_px"] for r in found["pitch_candidates_px"]]
        self.assertTrue(any(abs(v-32)<=2 for v in candidates),found)
        rotated=cv2.rotate(bgr,cv2.ROTATE_90_CLOCKWISE)
        rotated_found=cross_pitch_candidates(rotated,0)
        self.assertTrue(any(abs(r["period_px"]-32)<=2
                            for r in rotated_found["pitch_candidates_px"]),rotated_found)

    def test_blank_and_periodic_dots_cannot_count_as_yarn(self):
        plain=np.full((400,400,3),128,dtype=np.uint8)
        out,pts,edges=detect(plain,20)
        self.assertIsNone(out['candidate_cross_deg'])
        self.assertEqual(len(edges),0)
        dots=plain.copy()
        import cv2
        for x in range(15,390,23):
            for y in range(14,390,29):
                cv2.circle(dots,(x,y),3,(210,210,210),-1)
        out,_,_=detect(dots,0)
        self.assertFalse(out['status'].startswith('IMAGE_SUPPORTED'))

if __name__=='__main__':
    unittest.main()
