"""Analytic module checks; these do not assert real-fabric accuracy."""
from dataclasses import replace
from pathlib import Path
import json

import cv2
import numpy as np
import pytest
from scipy.ndimage import gaussian_filter

from fabric_measurement.config import Settings
from fabric_measurement.geometry import calibration, quality, rectify, register_pair
from fabric_measurement.measurements import density_summary, profile_width
from fabric_measurement.structure import (_intersection, _track_segments, template_match,
                                           twill_analysis, weave_analysis, yarn_reference)
from fabric_measurement.pipeline import quality_gate, run_files


def rgb(gray):
    return np.repeat(np.uint8(np.clip(gray,0,1)*255)[...,None],3,axis=2)


def paired_stripes(size=256, angles=(0,90), pitches=(24,32)):
    y,x=np.mgrid[:size,:size]
    values=[]
    for angle,pitch in zip(angles,pitches):
        n=-x*np.sin(np.deg2rad(angle))+y*np.cos(np.deg2rad(angle))
        distance=(n+pitch/2)%pitch-pitch/2
        values.append(np.exp(-.5*(distance/2.2)**2))
    return rgb(.15+.38*values[0]+.32*values[1])


@pytest.mark.parametrize('value',[0.,float('nan'),-1.,float('inf')])
def test_invalid_scale(value):
    with pytest.raises(ValueError):calibration(value,True)


def test_unconfirmed_scale_stays_candidate():
    assert calibration(.02,False)['mm_per_px'] is None
    assert calibration(.02,False)['candidate_mm_per_px']==.02
    assert calibration(.02,True)['mm_per_px']==.02


def test_flat_image_quality_rejected():
    result=quality(np.full((128,128,3),128,np.uint8),Settings())
    assert result['status']=='LOW_CONFIDENCE'
    assert 'insufficient_contrast' in result['reasons']


def test_rectification_maps_supplied_corners():
    im=paired_stripes()
    corners=np.float32([[10,12],[235,20],[240,238],[15,240]])
    transformed,m=rectify(im,corners,(160,180))
    actual=cv2.perspectiveTransform(corners[None],m)[0]
    assert transformed.shape==(180,160,3)
    assert np.allclose(actual,[[0,0],[159,0],[159,179],[0,179]],atol=1e-3)


@pytest.mark.parametrize('roi',[(0,0,10,10),(-1,0,128,128),(200,0,128,128)])
def test_invalid_roi(roi):
    with pytest.raises(ValueError):rectify(paired_stripes(),roi=roi)


def test_registration_identity():
    im=paired_stripes()
    aligned,valid,result=register_pair(im,im,Settings(),prealigned=True)
    assert result['status']=='PASS'
    assert result['median_local_residual_px']<.01
    assert valid.all() and np.array_equal(im,aligned)


def test_registration_translation():
    noise=gaussian_filter(np.random.default_rng(8).normal(size=(256,256)),2)
    im=rgb(.5+noise/np.std(noise)*.12)
    moved=cv2.warpAffine(im,np.float32([[1,0,3],[0,1,-2]]),(256,256))
    aligned,valid,result=register_pair(im,moved,Settings())
    assert result['status']=='PASS'
    assert result['median_local_residual_px']<.5
    assert np.mean(abs(im[valid].astype(float)-aligned[valid]))<2


@pytest.mark.parametrize('polarity',[1,-1])
def test_gradient_width_analytic_gaussian(polarity):
    x=np.arange(-15,15.01,.5)
    p=.5+polarity*.35*np.exp(-.5*(x/3)**2)
    width,reason=profile_width(p,x)
    assert reason is None
    assert abs(width['width_px']-6)<=1
    assert width['polarity']==('bright' if polarity>0 else 'dark')


def test_flat_profile_has_no_width():
    result,reason=profile_width(np.full(61,.5),np.linspace(-15,15,61))
    assert result is None and reason


@pytest.mark.parametrize('name,repeat,top',[('1/1',2,1),('2/1',3,2),('3/1',4,3)])
def test_template_analytic_truth(name,repeat,top):
    y,x=np.indices((12,12))
    m=((y+x)%repeat<top).astype(int)
    result=template_match(m,Settings())
    assert result['candidate']==name
    assert result['ranked_templates'][0]['agreement']==1


def test_unknown_matrix_does_not_classify():
    r=template_match(np.full((8,8),-1),Settings())
    assert r['candidate'] is None and r['known_cells']==0


def test_invalid_float_matrix():
    with pytest.raises(ValueError):template_match(np.full((8,8),2),Settings())


def test_gaps_do_not_form_observed_intersection():
    t={'points_xy':[[0,5],[30,5]],'points':[[0,5,1],[30,5,1]]}
    a,b=_track_segments(t,5)
    assert _intersection(a,b,np.array([[15,0]]),np.array([[15,10]])) is None


def test_observed_intersection():
    p=_intersection(np.array([[0,5]]),np.array([[30,5]]),np.array([[15,0]]),np.array([[15,10]]))
    assert np.allclose(p,[15,5])


def test_empirical_reference_conversion():
    widths=[dict(family='A',identity='warp_candidate',p10_p50_p90_mm=[.15,.2,.25],status='PASS')]
    densities={'families':{'warp_candidate':{'count_per_cm':25}}}
    rules=[dict(width_mm=[.15,.25],density_per_cm=[20,30],Ne=[10,20],source='analytic software fixture')]
    r=yarn_reference(widths,densities,rules)[0]
    assert r['status']=='AVAILABLE'
    assert r['reference_only'] is True
    assert r['tex']==[29.525,59.05]


def test_empirical_reference_missing_rule_abstains():
    widths=[dict(family='A',identity='warp_candidate',p10_p50_p90_mm=None,status='LOW_CONFIDENCE')]
    r=yarn_reference(widths,{'families':{}},[])[0]
    assert r['Ne'] is None and r['tex'] is None and r['status']=='UNAVAILABLE'


def test_twill_is_independent_of_yarn_axes():
    y,x=np.indices((256,256))
    angle=150
    n=-x*np.sin(np.deg2rad(angle))+y*np.cos(np.deg2rad(angle))
    image=rgb(.5+.25*np.cos(2*np.pi*n/12))
    r=twill_analysis(image,[{'angle_deg':0},{'angle_deg':90}],Settings())
    distance=abs((r['image_angle_deg']-angle+90)%180-90)
    assert distance<=6
    assert r['direction']=='right_rising'


@pytest.fixture(scope='module')
def full_run(tmp_path_factory):
    from PIL import Image
    directory=tmp_path_factory.mktemp('report_route')
    image=paired_stripes()
    file=directory/'source.png'
    Image.fromarray(image).save(file)
    output=directory/'result'
    result=run_files(file,file,output,mm_per_px=.02,scale_confirmed=True,warp_angle=0,prealigned=True)
    return result,output,file


def test_full_route_executes_all_stages(full_run):
    result,output,_=full_run
    assert len(result['stages'])==14
    assert all(s['implemented'] and s['executed'] for s in result['stages'])
    assert len(result['families'])==2
    assert len(result['widths'])==2
    assert len(result['yarn_reference'])==2
    assert (output/'review.html').is_file()


def test_full_route_density_and_units(full_run):
    result,_,_=full_run
    families=result['families']
    for angle,pitch in [(0,24),(90,32)]:
        f=min(families,key=lambda f:abs((f['angle_deg']-angle+90)%180-90))
        assert abs((f['angle_deg']-angle+90)%180-90)<=3
        value=f['density']['count_density_per_px']
        assert value and abs(value*pitch-1)<.08
        assert abs(f['density']['count_density_per_cm']-value*500)<1e-8


def test_evidence_is_decodeable_and_indexed(full_run):
    from PIL import Image
    result,output,_=full_run
    assert result['evidence']['status']=='PASS'
    for entry in result['evidence']['files']:
        with Image.open(output/entry['path']) as image:image.verify()
    saved=json.loads((output/'result.json').read_text(encoding='utf-8'))
    assert saved['version']==result['version']


def test_physical_accuracy_not_inferred_from_gate(full_run):
    result,_,_=full_run
    assert result['physical_accuracy']=='NOT_EVALUATED'
    assert result['eligible_for_physical_release'] is False
    assert result['gate3']['eligible_for_physical_release'] is False


def test_output_is_not_overwritten(full_run):
    _,output,source=full_run
    before=(output/'result.json').read_bytes()
    with pytest.raises(FileExistsError):run_files(source,source,output)
    assert before==(output/'result.json').read_bytes()


def test_flat_pair_full_route_abstains(tmp_path):
    from PIL import Image
    source=tmp_path/'flat.png'
    Image.fromarray(np.full((128,128,3),128,np.uint8)).save(source)
    r=run_files(source,source,tmp_path/'result',prealigned=True)
    assert not r['families']
    assert r['gate3']['status']=='LOW_CONFIDENCE'
    assert r['weave']['candidate'] is None
    assert r['twill']['image_angle_deg'] is None
    assert r['density']['ratio_count'] is None


def test_measurements_use_transmission_centers(full_run):
    r,_,_=full_run
    assert all(f['source']=='transmission' for f in r['families'])


def test_hint_changes_only_identity():
    from fabric_measurement.pipeline import analyze_pair
    im=paired_stripes(192)
    a,_=analyze_pair(im,im,warp_angle=0,prealigned=True)
    b,_=analyze_pair(im,im,warp_angle=90,prealigned=True)
    assert [f['tracks'] for f in a['families']]==[f['tracks'] for f in b['families']]
    assert [f['identity'] for f in a['families']]==list(reversed([f['identity'] for f in b['families']]))


def test_unconfirmed_full_run_no_physical_units():
    from fabric_measurement.pipeline import analyze_pair
    im=paired_stripes(192)
    r,_=analyze_pair(im,im,mm_per_px=.02,scale_confirmed=False,warp_angle=0,prealigned=True)
    assert r['calibration']['mm_per_px'] is None
    assert all(w['p10_p50_p90_mm'] is None for w in r['widths'])
    assert all(d['count_per_cm'] is None for d in r['density']['families'].values())
    assert any(d['candidate_count_per_cm'] for d in r['density']['families'].values())
