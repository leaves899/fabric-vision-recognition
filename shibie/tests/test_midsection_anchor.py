from __future__ import annotations
import unittest
import numpy as np
from engine.midsection_anchor import validate_midsection_anchor


class MidsectionAnchorTests(unittest.TestCase):
    def test_uniform_nonentity_abstains(self):
        patch=np.full((520,520,3),128,dtype=np.uint8)
        r=validate_midsection_anchor(patch,patch,"warp",27)
        self.assertNotEqual(r["status"],"PASS")

    def test_symmetry_and_unknown_rt_signs_are_allowed(self):
        period=800./30.
        grid_y,grid_x=np.mgrid[0:520,0:520]
        x=grid_x-grid_y*.01-4.
        distance=np.abs((x/period+.5)%1.-.5)
        core=(distance<.31).astype(float)
        R=np.clip(55+153*core,0,255).astype(np.uint8)
        T=np.clip(228-153*core,0,255).astype(np.uint8)
        R=np.stack([R,R,R],axis=-1)
        T=np.stack([T,T,T],axis=-1)
        observed=validate_midsection_anchor(R,T,"warp",27)
        self.assertIn(observed["status"],("PASS","LOW_CONFIDENCE","UNDETERMINED"))
        if observed["status"]=="PASS":
            self.assertLessEqual(observed["midsection_phase_displacement_px"],
                                 .26*observed["pitch_px"]+1.e-6)
            self.assertGreater(len(observed["center_positions_px"]),8)

    def test_bad_family_is_rejected(self):
        patch=np.full((520,520,3),128,dtype=np.uint8)
        with self.assertRaises(ValueError):
            validate_midsection_anchor(patch,patch,"invalid",27)


if __name__=="__main__":
    unittest.main()
