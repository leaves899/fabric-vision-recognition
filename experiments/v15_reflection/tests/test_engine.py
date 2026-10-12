"""Synthetic math/protocol tests. NOT cross-fabric accuracy evidence."""
import json
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter
from experiments.v15_reflection.engine import (
    _pitch, axis_angle, analyze_axis, gate2, measure, prepare_roi,
)


def weave(size=640, a=16, b=24, twill=18):
    y,x=np.indices((size,size))
    z=(128+41*np.cos(2*np.pi*y/a)+36*np.cos(2*np.pi*x/b)
       +twill*np.cos(2*np.pi*(x+y)/60))
    rgb=np.stack([z*.78,z*.89,z],axis=2).clip(0,255).astype("uint8")
    return Image.fromarray(rgb,"RGB")


def corners(n):
    return [[0,0],[n-1,0],[n-1,n-1],[0,n-1]]


class MetrologyTest(unittest.TestCase):
    def test_manual_axis_order_invariant(self):
        self.assertAlmostEqual(axis_angle([[10,20],[210,20]]),
                               axis_angle([[210,20],[10,20]]))
        with self.assertRaises(ValueError):
            axis_angle([[0,0],[1,0]])

    def test_projection_period_on_synthetic_woven_image(self):
        img=weave()
        a=analyze_axis(img,0,50/640)
        b=analyze_axis(img,90,50/640)
        self.assertAlmostEqual(a["pitch_px"],16,delta=2,msg=str(a))
        self.assertAlmostEqual(b["pitch_px"],24,delta=3,msg=str(b))
        self.assertLess(a["strip_cv"],.085)
        self.assertLess(b["strip_cv"],.085)

    def test_scale_and_manual_assignment_are_separate(self):
        img=weave()
        result=measure(img,[[90,200],[450,200]],True,corners(640),True,"A")
        self.assertEqual(result["orientation"]["source"],"USER_CONFIRMED_REAL_YARN_REFERENCE")
        self.assertEqual(result["geometry"]["frame_mm"],50)
        self.assertEqual(result["ten_parameters"]["01"]["status"],"CANDIDATE")
        self.assertEqual(result["ten_parameters"]["08"]["status"],"CANDIDATE",str(result["axes"]["A"]))
        self.assertAlmostEqual(result["ten_parameters"]["08"]["value"],200/16,delta=1.2)
        self.assertAlmostEqual(result["ten_parameters"]["09"]["value"],200/24,delta=1.2)
        self.assertEqual(result["ten_parameters"]["05"]["status"],"UNAVAILABLE")
        self.assertEqual(result["ten_parameters"]["07"]["status"],"UNAVAILABLE")
        self.assertTrue(result["candidate_only"])

    def test_absent_or_unconfirmed_frame_cannot_output_density(self):
        img=weave()
        for corners_input, verified in [(None,False),(corners(640),False)]:
            result=measure(img,[[90,200],[450,200]],True,corners_input,verified,"A")
            self.assertIsNone(result["ten_parameters"]["08"]["value"])
            self.assertIsNone(result["ten_parameters"]["09"]["value"])
            self.assertFalse(result["geometry"]["confirmed"])

    def test_unconfirmed_identity_and_reference_not_promoted(self):
        img=weave()
        result=measure(img,[[90,200],[450,200]],False,corners(640),True,"A")
        self.assertEqual(result["ten_parameters"]["01"]["status"],"UNAVAILABLE")
        self.assertEqual(result["ten_parameters"]["08"]["status"],"UNAVAILABLE")
        self.assertIn("AUTO_DIRECTION_NOT_VALIDATED",result["failure_reasons"])

    def test_rotated_90(self):
        img=weave().rotate(90,expand=False)
        result=measure(img,[[200,90],[200,450]],True,corners(640),True,"A")
        self.assertEqual(result["ten_parameters"]["01"]["status"],"CANDIDATE")
        self.assertAlmostEqual(result["ten_parameters"]["01"]["value"],90,delta=.1)
        self.assertAlmostEqual(result["axes"]["A"]["pitch_px"],16,delta=2)

    def test_unusable_flat_image_is_rejected(self):
        img=Image.new("RGB",(640,640),(128,128,128))
        result=measure(img)
        self.assertEqual(result["status"],"REJECTED")
        self.assertIn("LOW_CONTRAST",result["failure_reasons"])

    def test_invalid_geometry_rejected(self):
        with self.assertRaises(ValueError):
            measure(weave(),[[90,200],[450,200]],True,[[0,0]]*4,True,"A")
        with self.assertRaises(ValueError):
            measure(weave(),[[90,200],[450,200]],True,
                    [[0,0],[1,0],[1,1],[0,1]],True,"A")

    def test_harmonic_should_not_be_silently_inferred_as_certified(self):
        p=np.cos(2*np.pi*np.arange(500)/18)+np.cos(2*np.pi*np.arange(500)/9)
        outcome=_pitch(p*30)
        self.assertIn("reason",outcome) if "reason" in outcome else self.assertIn(
            "period_px",outcome)
        # Even when internally periodic, candidate_only is immutable.
        self.assertTrue(measure(weave(),[[90,200],[450,200]],True,
                                corners(640),True,"A")["candidate_only"])

    def test_cli_writes_json_without_touching_v5(self):
        with tempfile.TemporaryDirectory() as tmp:
            inp=Path(tmp)/"fabric.png"
            out=Path(tmp)/"measurement.json"
            weave().save(inp)
            cmd=[sys.executable,"-m","experiments.v15_reflection.engine",
                 "--image",str(inp),"--reference","90,200,450,200",
                 "--confirm-reference","--corners",json.dumps(corners(640)),
                 "--confirm-corners","--warp-family","A","--out",str(out)]
            proc=subprocess.run(cmd,capture_output=True,text=True)
            self.assertIn(proc.returncode,(0,3),msg=proc.stderr)
            data=json.loads(out.read_text())
            self.assertEqual(len(data["ten_parameters"]),10)
            self.assertEqual(data["source"],"INDEPENDENT_V15_REFLECTION")


if __name__=="__main__":
    unittest.main()
