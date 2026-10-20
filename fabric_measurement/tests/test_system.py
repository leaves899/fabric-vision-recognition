"""Public input boundaries, persistence, and abstention regression checks."""
from io import BytesIO
import json
from zipfile import ZipFile

import numpy as np
from PIL import Image
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from fabric_measurement import server
from fabric_measurement.geometry import rectify
from fabric_measurement.pipeline import analyze_pair, write_artifacts
from fabric_measurement.primitives import grayscale
from fabric_measurement.service import AnalysisOptions, decode_image
from test_route import paired_stripes


def png(image):
    buffer = BytesIO()
    Image.fromarray(image).save(buffer, format='PNG')
    return buffer.getvalue()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(server, 'RUNS', tmp_path / 'runs')
    with TestClient(server.app) as c:
        yield c


@pytest.mark.parametrize('options',[
    {'mm_per_px':float('nan')}, {'mm_per_px':-1}, {'scale_confirmed':True},
    {'roi':[0,0,127,300]}, {'roi':[0,0,1201,300]}, {'roi':[.5,0,300,300]},
    {'warp_angle':180}, {'warp_angle':float('inf')}, {'unexpected':'no'},
    {'target_size':[256,256]}, {'front_corners':[[0,0],[200,0],[200,200],[0,200]]},
    {'yarn_reference_rules':[{'width_mm':[.2,.1],'density_per_cm':[10,30],'Ne':[5,10],'source':'fixture'}]},
])
def test_invalid_options_rejected(options):
    with pytest.raises(ValidationError):
        AnalysisOptions(**options)


def test_dark_uint8_values_are_not_normalized_as_white():
    gray = grayscale(np.ones((128,128,3), np.uint8))
    assert np.allclose(gray,1/255)


def test_single_image_is_not_faked_as_transmission(tmp_path):
    result,buffers=analyze_pair(paired_stripes(192),None,warp_angle=0)
    write_artifacts(result,buffers,tmp_path/'result')
    assert result['input_mode']=='REFLECTION_ONLY'
    assert buffers['back'] is None
    assert result['direction_analysis']['transmission'] is None
    assert all(f['source']=='reflection' for f in result['families'])
    assert 'transmission_not_provided' in result['gate3']['reasons']
    assert not (tmp_path/'result/transmission_registered.png').exists()
    assert 'href\',\'transmission_registered.png' not in (tmp_path/'result/review.html').read_text(encoding='utf-8')


def test_roi_geometry_does_not_resize_original():
    a=paired_stripes(256)
    b,m=rectify(a,roi=[40,50,128,160])
    assert np.array_equal(a[50:210,40:168],b)
    assert np.allclose(m,[[1,0,-40],[0,1,-50],[0,0,1]])


def test_mirrored_corner_order_rejected():
    with pytest.raises(ValueError):
        rectify(paired_stripes(),[[10,10],[10,240],[240,240],[240,10]],[256,256])


def test_huge_rectification_rejected_before_allocation():
    with pytest.raises(ValueError):
        rectify(paired_stripes(),[[0,0],[255,0],[255,255],[0,255]],[99999,99999])


@pytest.mark.parametrize('data',[b'',b'not an image'])
def test_invalid_decode(data):
    with pytest.raises(ValueError):
        decode_image(data)


def test_api_bad_input_and_duplicate_pair_preserve_empty_history(client):
    assert client.post('/api/analyze',files={'reflection':('bad.png',b'abc')}).status_code==422
    image=png(paired_stripes(192))
    assert client.post('/api/analyze',files={'reflection':('a.png',image),'transmission':('b.png',image)}).status_code==422
    assert client.post('/api/analyze',files={'reflection':('a.png',image)},data={'options':'{"scale_confirmed":true}'}).status_code==422
    assert client.get('/api/runs').json()==[]


def test_api_full_persistence_and_download(client):
    image=png(paired_stripes(192))
    response=client.post('/api/analyze',files={'reflection':('fixture.png',image)},data={'options':'{"warp_angle":0}'})
    assert response.status_code==200,response.text
    data=response.json();run_id=data['run_id']
    assert data['result']['gate3']['status']=='LOW_CONFIDENCE'
    assert len(data['result']['stages'])==14
    saved=client.get(data['json_url']).json()
    assert saved['source']['filenames']==['fixture.png']
    assert saved['physical_accuracy']=='NOT_EVALUATED'
    assert saved['calibration']['mm_per_px'] is None
    assert client.get('/api/runs/'+run_id).json()==data
    assert client.get('/api/runs').json()[0]['run_id']==run_id
    for e in saved['evidence']['files']:
        raw=client.get('/runs/'+run_id+'/'+e['path'])
        assert raw.status_code==200
        Image.open(BytesIO(raw.content)).verify()
    zipped=client.get(data['zip_url'])
    with ZipFile(BytesIO(zipped.content)) as archive:
        assert json.loads(archive.read('result.json'))==saved
        assert 'review.html' in archive.namelist()
    assert client.get('/api/runs/not-an-id').status_code==404
    assert client.get('/runs/'+run_id+'/..%2Fserver.py').status_code==404


def test_api_sample_catalog_hash_and_static_ui(client):
    samples=client.get('/api/samples').json()
    assert len(samples)==8 and sum(s['paired'] for s in samples)==1
    assert client.get('/api/samples/U20261013_01/reflection').status_code==200
    assert client.get('/api/samples/U20261013_01/transmission').status_code==404
    assert client.get('/').status_code==200
    assert client.get('/assets/app.js').status_code==200
    assert 'roi' in client.get('/api/samples').text


@pytest.mark.parametrize('turns',[0,1,2,3])
def test_rotated_analytic_grid_retains_correct_pitch_candidates(turns):
    image=np.rot90(paired_stripes(256),turns).copy()
    result,_=analyze_pair(image,image,prealigned=True)
    actual=sorted(f['density'].get('median_spacing_px',0) for f in result['families'])
    assert len(actual)==2
    assert np.allclose(actual,[24,32],rtol=.08)


def test_single_diagonal_texture_does_not_fabricate_two_yarn_axes():
    y,x=np.indices((256,256))
    image=np.repeat(np.uint8((.5+.3*np.cos((x-y)*2*np.pi/16))*255)[...,None],3,axis=2)
    result,_=analyze_pair(image,None)
    assert not result['families']
    assert result['weave']['candidate'] is None
