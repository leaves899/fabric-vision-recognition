import unittest
from dataclasses import replace
import numpy as np
from synthetic_capture_8k import CaptureScene,_warp_up
from synthetic_rt_heightfield_8k import Optics,render_region,geometry,yarn_fields,validate,_dense_truth

class HeightfieldPhysics(unittest.TestCase):
    def setUp(self):
        self.s=CaptureScene(rotation_deg=0,perspective=0,shift_reflection_x=0,diagonal_decoy=0,seed=38121)
    def test_station_rejects_rotation_and_fake_inversion(self):
        for s in (replace(self.s,rotation_deg=1),replace(self.s,contrast_polarity='bright'),replace(self.s,shift_reflection_x=.8)):
            with self.assertRaises(ValueError):validate(s)
    def test_repeatability_and_strip_halo(self):
        a,b=render_region(self.s,Optics(),3700,2700,160,200)
        c,d=render_region(self.s,Optics(),3700,2740,160,120)
        np.testing.assert_array_equal(a[64:136,24:-24],c[24:96,24:-24])
        np.testing.assert_array_equal(b[64:136,24:-24],d[24:96,24:-24])
    def test_visible_owner_matches_float_topology_at_crossing_centres(self):
        for weave in ('plain','twill_2_1','twill_3_1'):
            s=replace(self.s,weave=weave,wave_fraction=0)
            # Solve actual perturbed warp/weft intersections iteratively.
            wi,fi=np.meshgrid(np.arange(-4,5),np.arange(-4,5));x=4000+wi*800/30;y=3000+fi*32
            for _ in range(8):
                x,_=yarn_fields(s,'warp',wi,y);y,_=yarn_fields(s,'weft',fi,x)
            g=geometry(s,x,y)
            np.testing.assert_array_equal(g['visible'],np.where(_warp_up(wi,fi,weave),1,2))
    def test_backlight_monotonic_absorption_and_pore_brighter_than_cross(self):
        r,t,g=render_region(self.s,Optics(noise_sigma=0),3700,2700,240,240,True)
        r,u=render_region(self.s,Optics(absorption_per_px=.28,noise_sigma=0),3700,2700,240,240)
        self.assertTrue(np.all(u<=t))
        pore=(g['warp_chord']==0)&(g['weft_chord']==0)
        cross=(g['warp_chord']>6)&(g['weft_chord']>6)
        self.assertGreater(t[:,:,0][pore].mean(),t[:,:,0][cross].mean())
    def test_light_direction_changes_reflection_not_transmission(self):
        a,b=render_region(self.s,Optics(),3700,2700,160,160)
        c,d=render_region(self.s,Optics(light_direction=(.7,.1,.7)),3700,2700,160,160)
        self.assertGreater(np.abs(a.astype(float)-c).mean(),1)
        np.testing.assert_array_equal(b,d)
    def test_weave_and_material_geometry_not_a_texture_overlay(self):
        a,b=render_region(self.s,Optics(),3700,2700,240,240)
        c,d=render_region(replace(self.s,weave='twill_3_1'),Optics(),3700,2700,240,240)
        self.assertGreater(np.abs(a.astype(float)-c).mean(),3)
        self.assertGreater(np.abs(b.astype(float)-d).mean(),0)
    def test_overlapping_ellipses_do_not_interpenetrate(self):
        y,x=np.mgrid[2700:2900,3700:3900].astype(np.float32)
        for weave in ('plain','twill_2_1','twill_3_1'):
            g=geometry(replace(self.s,weave=weave),x,y)
            overlap=(g['warp_chord']>0)&(g['weft_chord']>0)
            self.assertGreaterEqual(float(g['volume_clearance'][overlap].min()),.999)

    def test_serialized_truth_uses_scalar_ids_and_matches_renderer_centres(self):
        scene=replace(self.s,width=240,height=200)
        lines=_dense_truth(scene)
        for family,rows in lines.items():
            self.assertTrue(rows)
            for row in rows:
                pts=np.array(row['points']);axis=1 if family=='warp' else 0
                c,w=yarn_fields(scene,family,int(row['id'][1:]),pts[:,axis])
                self.assertLess(np.max(np.abs(c-pts[:,1-axis])),.001)
                self.assertEqual(len(row['widths_px']),len(pts))

    def test_width_capability_at_actual_samples(self):
        for family in ('warp','weft'):
            ids=np.arange(-70,71)[:,None];along=np.arange(1000,5000,13)[None,:]
            _,width=yarn_fields(self.s,family,ids,along)
            self.assertGreaterEqual(np.percentile(width,10),12)

if __name__=='__main__':unittest.main()
