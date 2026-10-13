"""Only software contracts & synthetic negative controls; not real-yarn accuracy."""
import copy
import cv2
import numpy as np
from benchmark.p0_g1_probe import native, geometry, infer, a3_post_audit, morphology, feature_maps

def sample():
    return {
        "sample_id":"SYNTH_PRINTED_STRIPES",
        "coordinate_space":"ZOOM_2X_NATIVE_PIXELS",
        "enlargement_scale":2, "crop_original_xyxy":[0,0,560,560],
        "reference_confirmed":True, "same_family_intervals_confirmed":True,
        "same_family_intervals":1,
        "segments":{
            "reference":[[90,552],[1020,552]],
            "check_same":[[90,600],[1020,600]],
            "holdout_same":[[90,650],[1020,650]],
            "check_cross":[[560,100],[560,900]],
            "check_cross_second":[[700,100],[700,900]]
        }
    }

def printed():
    x=np.arange(560)[None,:]
    y=np.arange(560)[:,None]
    arr=np.clip(120+42*np.cos(2*np.pi*y/24)+11*np.cos(2*np.pi*x/32),0,255)
    return cv2.cvtColor(arr.astype(np.uint8),cv2.COLOR_GRAY2BGR)

def test_annotation_coords_and_native_pitch():
    a=sample()
    assert np.allclose(native(a,"reference"),[[45,276],[510,276]])
    im,mask,ra,p,geo=geometry(printed(),native(a,"reference"),native(a,"check_same"),1)
    assert abs(p-24)<1e-4
    assert geo["pitch_original_px"]==24

def test_a3_and_b_are_strictly_excluded():
    ann=sample()
    first,_=infer(printed(),ann)
    other=copy.deepcopy(ann)
    other["segments"]["holdout_same"]=[[100,185],[500,195]]
    other["segments"]["check_cross"]=[[100,60],[100,990]]
    other["segments"]["check_cross_second"]=[[200,60],[200,990]]
    second,_=infer(printed(),other)
    assert first==second
    assert a3_post_audit(ann,first)!=a3_post_audit(other,first)

def test_printed_optical_stripes_never_certified():
    out,_=infer(printed(),sample())
    assert out["decision"].startswith("G1_NOT_EVALUATED")
    assert out["physical_identity_verified"] is False
    assert out["physical_yarn_count"] is None
    assert out["density_per_cm"] is None
    assert "HALF_PITCH_GAP_PHASE" in out["hypotheses"]
    assert "DIAGONAL_TEXTURE_PLUS" in out["hypotheses"]

def test_too_small_camera_pixel_pitch_abstains():
    a=sample()
    a["segments"]["check_same"]=[[90,558],[1020,558]]
    out,_=infer(printed(),a)
    assert out["decision"]=="ABSTAIN_NATIVE_PITCH_UNRESOLVABLE"

def test_morphology_remains_image_score_not_ground_truth():
    im=printed()
    mask=np.ones(im.shape[:2],dtype=bool)
    out=morphology(feature_maps(im,mask),mask,220,276,24)
    assert out is not None
    assert all(k in out for k in ("paired_edges","center_flank","fiber_direction_cue"))
    assert "physical_identity_probability" not in out
