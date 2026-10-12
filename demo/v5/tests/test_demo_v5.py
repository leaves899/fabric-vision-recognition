"""V5 geometry, API and frozen baseline. V4 is mocked in fast contract tests."""
from pathlib import Path
import sys
import numpy as np
import cv2
from fastapi.testclient import TestClient
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import v4_analysis
from reference_direction import reference_from_two_points, normalize_v4_rotation
from v4_adapter import check_frozen
from server import app


def fake_tracks():
    first=[[[80,y],[160,y],[290,y],[450,y]] for y in (120,180,240,300,360,420)]
    second=[[[x,90],[x,190],[x,290],[x,450]] for x in (100,160,220,280,340,400)]
    return {'first':first,'second':second,'summary':{'first_family_count':6,'second_family_count':6},
            'frozen_sha256':check_frozen(),'adapter_rotation_deg':0.0}


def image_bytes():
    im=np.full((600,600,3),225,np.uint8)
    cv2.rectangle(im,(50,50),(550,550),(100,120,130),-1)
    ok,data=cv2.imencode('.png',im)
    assert ok
    return data.tobytes()


REF=[[110,230],[360,230]]


@pytest.fixture(autouse=True)
def mocked_v4(monkeypatch):
    called=[]
    def run(img,ang):
        called.append((img.shape[:2],ang))
        return fake_tracks()
    monkeypatch.setattr(v4_analysis,'run_v4',run)
    return called


def test_frozen_sha():
    assert check_frozen()=='dde5d84193a3f3d02bb55ad72a8c2b9f2a640034563ed936736ad46808b8dad1'


def test_angle_near_negative_thirteen(mocked_v4):
    # Reference points along image-space up-right slope -13 deg.
    pts=[[100,250],[400,250-300*np.tan(np.deg2rad(13))]]
    result,_=v4_analysis.analyze(image_bytes(),reference_points=pts,confirm_reference=True)
    assert result['direction_evidence']['automatic_rotation_estimation'] is False
    assert abs(mocked_v4[0][1]+13)<1e-2
    assert result['manual_yarn_reference']['confirmed_by_operator']
    assert len(result['parameters'])==10
    assert result['parameters'][4]['status']=='UNAVAILABLE'
    assert result['parameters'][5]['status']=='UNAVAILABLE'


def test_angle_horizontal_vertical_and_reverse():
    f=lambda pts:reference_from_two_points(pts,(600,600,3),confirmed=True)
    assert f([[20,50],[300,50]])['v4_adapter_rotation_deg']==0
    assert f([[300,50],[20,50]])['v4_adapter_rotation_deg']==0
    assert f([[80,50],[80,500]])['v4_adapter_rotation_deg']==-90
    assert f([[80,500],[80,50]])['v4_adapter_rotation_deg']==-90
    assert normalize_v4_rotation(167)==-13
    assert normalize_v4_rotation(-13)==-13


def test_reference_after_perspective_calibration(mocked_v4):
    # Warp non-axis-aligned quadrilateral into 901 x 901 square.
    pts=[[60,60],[540,85],[515,545],[75,520]]
    # Geometry is non-degenerate and within polygon. Both points are inside.
    ref=[[150,180],[410,190]]
    result,_=v4_analysis.analyze(image_bytes(),pts,True,ref,True)
    H=np.asarray(result['calibration']['homography'])
    mapped=cv2.perspectiveTransform(np.array(ref,np.float32).reshape(1,2,2),H)[0]
    diff=mapped[1]-mapped[0]
    expected=(np.degrees(np.arctan2(diff[1],diff[0]))+90)%180-90
    assert abs(mocked_v4[0][1]-expected)<1e-3
    assert mocked_v4[0][0]==(901,901)
    assert result['manual_yarn_reference']['reference_axis_image_deg']!=result['manual_yarn_reference']['reference_axis_roi_deg']
    assert result['calibration']['confirmed']
    assert result['parameters'][7]['status']=='NEEDS_CONFIRMATION'


def test_unconfirmed_calibration_does_not_create_physical_density():
    result,_=v4_analysis.analyze(image_bytes(),[[60,60],[540,60],[540,540],[60,540]],False,
                                 REF,True)
    assert result['parameters'][7]['status']=='UNAVAILABLE'


def test_v4_counts_remain_candidate(mocked_v4):
    result,images=v4_analysis.analyze(image_bytes(),reference_points=REF,confirm_reference=True)
    assert len(result['parameters'])==10
    assert result['v4']['family_a_candidate_lines']==6
    assert result['v4']['family_b_candidate_lines']==6
    assert result['v4']['validated_yarn_accuracy'] is None
    assert images['three_panel'].startswith('data:image/jpeg;base64,')
    assert result['manual_yarn_reference']['source']=='USER_TWO_POINT_SAME_REAL_YARN'


def test_missing_reference_and_no_confirmation_rejected():
    with pytest.raises(ValueError,match='两个参考点'):
        v4_analysis.analyze(image_bytes())
    with pytest.raises(ValueError,match='确认'):
        v4_analysis.analyze(image_bytes(),reference_points=REF)


@pytest.mark.parametrize('points', [
    [[2,2],[3,3]],
    [[1,50],[800,50]],
    [[100,100]],
    [[100,100],[None,100]],
])
def test_bad_reference_rejected(points):
    with pytest.raises((ValueError,TypeError)):
        v4_analysis.analyze(image_bytes(),reference_points=points,confirm_reference=True)


def test_reference_outside_calibrated_frame_rejected():
    with pytest.raises(ValueError,match='内侧区域'):
        v4_analysis.analyze(image_bytes(),[[60,60],[540,60],[540,540],[60,540]],True,
                            [[20,20],[280,100]],True)


def test_api_success_and_errors():
    c=TestClient(app)
    assert c.get('/').status_code==200
    assert c.get('/api/health').json()['version']=='0.3.0-v5'
    file={'image':('a.png',image_bytes(),'image/png')}
    ok=c.post('/api/analyze',files=file,data={
        'reference_points':'[[110,230],[360,230]]','confirm_reference':'true'})
    assert ok.status_code==200,ok.text[:400]
    assert ok.json()['result']['v4']['family_b_candidate_lines']==6
    miss=c.post('/api/analyze',files=file)
    assert miss.status_code==422
    unconfirmed=c.post('/api/analyze',files=file,data={'reference_points':'[[100,100],[330,100]]'})
    assert unconfirmed.status_code==422
    # Old manual angle field must not silently trigger a fallback.
    old=c.post('/api/analyze',files=file,data={'manual_angle':'-13'})
    assert old.status_code==422
    bad=c.post('/api/analyze',files=file,data={
        'reference_points':'[[110,230],[360,230]]','confirm_reference':'true','weave_override':'假的组织'})
    assert bad.status_code==422


def test_transect_intersection_count():
    x=v4_analysis.v4_transects(fake_tracks()['first'],0,(600,600))
    assert len(x['transects'])==3
    assert x['candidate_count_median']>=3

def test_opencv_rotation_sign_matches_reference_axis():
    pts=[[120,200],[320,260]]
    info=reference_from_two_points(pts,(600,600,3),confirmed=True)
    M=cv2.getRotationMatrix2D((300,300),info['v4_adapter_rotation_deg'],1)
    transformed=cv2.transform(np.asarray(pts,np.float32).reshape(1,2,2),M)[0]
    assert abs(transformed[1,1]-transformed[0,1])<0.02
