"""Local application: python -m uvicorn fabric_measurement.server:app --port 8018."""
from __future__ import annotations

import asyncio
from io import BytesIO
import json
import logging
from pathlib import Path
import re
from uuid import uuid4
from zipfile import ZipFile, ZIP_DEFLATED

import cv2
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from . import VERSION
from .service import (AnalysisOptions, MAX_BYTES, catalog, execute, sample_by_id,
                      sample_bytes, summary)

PACKAGE = Path(__file__).resolve().parent
RUNS = PACKAGE / 'runs'
app = FastAPI(title='织物图像识别工作台', version=VERSION)
app.mount('/assets', StaticFiles(directory=PACKAGE / 'web'), name='assets')
processing = asyncio.Semaphore(1)
logger = logging.getLogger(__name__)
cv2.setNumThreads(2)


def parse_options(text):
    try:
        return AnalysisOptions.model_validate_json(text)
    except ValidationError as exc:
        # Do not reflect uploaded values or stack traces in the UI.
        message = '; '.join('.'.join(map(str, e['loc'])) + ': ' + e['msg'] for e in exc.errors())
        raise HTTPException(status_code=422, detail=message) from exc


def run_folder(run_id):
    if not re.fullmatch(r'[a-f0-9]{32}', run_id):
        raise HTTPException(status_code=404, detail='结果不存在')
    folder = RUNS / run_id
    if not (folder / 'run_summary.json').is_file():
        raise HTTPException(status_code=404, detail='结果尚未完成或不存在')
    return folder


def response_for(run_id, result):
    return {'run_id': run_id, 'result': summary(result),
            'review_url': f'/runs/{run_id}/review.html',
            'json_url': f'/runs/{run_id}/result.json',
            'zip_url': f'/api/runs/{run_id}/download'}


@app.get('/')
def index():
    return FileResponse(PACKAGE / 'web/index.html')


@app.get('/api/health')
def health():
    return {'status': 'ok', 'version': VERSION, 'physical_accuracy': 'NOT_EVALUATED'}


@app.get('/api/samples')
def samples():
    return [{k: v for k, v in s.items() if k not in ('reflection', 'transmission')}
            | {'paired': bool(s.get('transmission'))} for s in catalog()]


@app.get('/api/samples/{sample_id}/{kind}')
def sample_image(sample_id: str, kind: str):
    try:
        data = sample_bytes(sample_by_id(sample_id), kind)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail='样本不存在') from exc
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=409, detail='样本校验失败') from exc
    return Response(data, media_type='image/png' if data[:8] == b'\x89PNG\r\n\x1a\n' else 'image/jpeg')


@app.post('/api/analyze')
async def analyze(reflection: UploadFile = File(...), transmission: UploadFile | None = File(None),
                  options: str = Form('{}')):
    opts = parse_options(options)
    front = await reflection.read(MAX_BYTES + 1)
    back = await transmission.read(MAX_BYTES + 1) if transmission else None
    if len(front) > MAX_BYTES or (back is not None and len(back) > MAX_BYTES):
        raise HTTPException(status_code=413, detail='每张图片不得超过 20 MB')
    names = [reflection.filename or 'reflection'] + ([transmission.filename or 'transmission'] if transmission else [])
    run_id = uuid4().hex
    try:
        async with processing:
            result = await run_in_threadpool(execute, front, back, opts, RUNS / run_id, names=names)
    except (ValueError, cv2.error) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception('Analysis failed for run %s', run_id)
        raise HTTPException(status_code=500, detail='处理失败；可凭运行编号检查本地服务日志：' + run_id) from exc
    return response_for(run_id, result)


@app.get('/api/runs')
def history():
    items = []
    if RUNS.exists():
        for file in sorted(RUNS.glob('*/run_summary.json'), key=lambda p: p.stat().st_mtime, reverse=True)[:40]:
            if not re.fullmatch(r'[a-f0-9]{32}', file.parent.name):
                continue
            r = json.loads(file.read_text(encoding='utf-8'))
            items.append({'run_id': file.parent.name, 'created_utc': r['created_utc'],
                          'source': r.get('source'), 'gate3': r['gate3']})
    return items


@app.get('/api/runs/{run_id}')
def run_result(run_id: str):
    result = json.loads((run_folder(run_id) / 'result.json').read_text(encoding='utf-8'))
    return response_for(run_id, result)


@app.get('/api/runs/{run_id}/download')
def download(run_id: str):
    directory = run_folder(run_id)
    buffer = BytesIO()
    with ZipFile(buffer, 'w', ZIP_DEFLATED) as archive:
        for path in sorted(directory.iterdir()):
            if path.is_file() and path.suffix in ('.png', '.json', '.html'):
                archive.write(path, path.name)
    return Response(buffer.getvalue(), media_type='application/zip',
                    headers={'Content-Disposition': f'attachment; filename="fabric-{run_id[:8]}.zip"'})


@app.get('/runs/{run_id}/{filename}')
def artifact(run_id: str, filename: str):
    directory = run_folder(run_id)
    # Only generated top-level evidence is served, never arbitrary workspace files.
    if not re.fullmatch(r'[A-Za-z0-9_]+\.(png|json|html)', filename):
        raise HTTPException(status_code=404, detail='文件不存在')
    path = directory / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail='文件不存在')
    return FileResponse(path)
