"""Launch: uvicorn server:app --host 127.0.0.1 --port 8008"""
from __future__ import annotations
import json
from pathlib import Path
from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from v4_analysis import analyze

ROOT=Path(__file__).resolve().parent
app=FastAPI(title='织物十大参数识别 Demo',version='0.3.0-v5')
app.mount('/assets',StaticFiles(directory=ROOT/'web'),name='web')
app.mount('/samples',StaticFiles(directory=ROOT/'samples'),name='samples')

@app.get('/')
def index():
    return FileResponse(ROOT/'web'/'index.html')

@app.get('/api/health')
def health():
    return {'status':'ok','version':'0.3.0-v5','disclaimer':'prototype; no verified yarn classification'}

@app.post('/api/analyze')
async def analyze_api(
    image: UploadFile=File(...),
    corners: str=Form('null'),
    confirm_corners: bool=Form(False),
    reference_points: str=Form('null'),
    confirm_reference: bool=Form(False),
    warp_family: str=Form(''),
    weave_override: str=Form(''),
    confirm_weave: bool=Form(False),
):
    try:
        pts=json.loads(corners)
        if pts is not None and (not isinstance(pts,list) or len(pts)!=4):
            raise ValueError('corners must be [tl,tr,br,bl]')
        points=json.loads(reference_points)
        result,images=analyze(await image.read(),pts,confirm_corners,points,
                              confirm_reference,warp_family or None,
                              weave_override or None,confirm_weave)
        return {'result':result,'visuals':images}
    except (ValueError,cv_error()) as exc:
        raise HTTPException(status_code=422,detail=str(exc)) from exc
    except Exception as exc:
        # Bubble actionable errors without dumping tracebacks in UI.
        raise HTTPException(status_code=500,detail='分析失败：'+str(exc)) from exc

def cv_error():
    import cv2
    return cv2.error
