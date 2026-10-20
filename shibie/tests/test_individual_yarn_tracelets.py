from __future__ import annotations
import unittest
import numpy as np
from engine.individual_yarn_tracelets import (
    _best_individual_center,trace_individual_entities,EntityTraceConfig)


class IndividualPhysicalYarnTests(unittest.TestCase):
    def test_core_follows_shifted_local_entity_without_gt(self):
        p=32.
        x=np.arange(520,dtype=float)
        # Independent optical central yarns are shifted by +7.7 px.
        phase=((x-(100.+7.7)+p/2)%p-p/2)
        core=np.exp(-.5*(phase/6.)**4)
        R=55+160*core
        T=220-130*core
        cfg=EntityTraceConfig()
        q=_best_individual_center(R,T,100.,100.,p,(1,-1),cfg)
        self.assertIsNotNone(q)
        self.assertLess(abs(q["normal_px"]-107.7),2.)

    def test_blank_rt_image_abstains(self):
        blank=np.full((520,520,3),120,np.uint8)
        out=trace_individual_entities(blank,blank,"warp",27.)
        self.assertNotEqual(out["status"],"PASS")
        self.assertEqual(len(out["tracks"]),0)

    def test_wrong_family_rejected(self):
        blank=np.full((520,520,3),120,np.uint8)
        with self.assertRaises(ValueError):
            trace_individual_entities(blank,blank,"bad_family",27.)

    def test_symmetric_core_does_not_hardcode_dark_or_bright(self):
        p=32.
        x=np.arange(520,dtype=float)
        core=np.exp(-.5*((((x-104.+p/2)%p)-p/2)/6.)**4)
        cfg=EntityTraceConfig()
        # A yarn bright in both modalities is legal given independent optics.
        a=60+160*core;b=90+140*core
        q=_best_individual_center(a,b,104.,104.,p,(1,1),cfg)
        self.assertIsNotNone(q)
        self.assertLess(abs(q["normal_px"]-104.),1.5)


if __name__=="__main__":
    unittest.main()
