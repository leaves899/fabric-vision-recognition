"""Run verified, UNMODIFIED frozen V4 yarn candidate detector.

The only generated changes in a temporary execution script are the *input path*,
*output directory*, *ROI* and *rotation parameter*. All V4 algorithms, feature
extraction, model fitting and trajectory decisions are inherited verbatim.
Neither the frozen source nor its training data is ever edited.
"""
from __future__ import annotations
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import threading
from pathlib import Path
import cv2
import numpy as np

ROOT=Path(__file__).resolve().parent
FROZEN=ROOT/'v4_frozen'
EXPECTED='dde5d84193a3f3d02bb55ad72a8c2b9f2a640034563ed936736ad46808b8dad1'
ITEMS_PATTERN=re.compile(r'(?ms)^ITEMS=\[\n.*?^\]\n')
LOCK=threading.Lock()


def check_frozen():
    source=FROZEN/'frozen/reoptimize_v4_quadgrid.py'
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    if digest!=EXPECTED:
        raise RuntimeError('V4 冻结文件的 SHA256 已变化；拒绝继续执行')
    return digest


def run_v4(roi:np.ndarray, rotation_deg:float):
    if min(roi.shape[:2])<128:
        raise ValueError('ROI 短边不能小于 128px')
    if not np.isfinite(rotation_deg) or not -180<=rotation_deg<=180:
        raise ValueError('V4 图像旋转角度必须在 -180 至 180 度范围内')
    check_frozen()
    h,w=roi.shape[:2]
    # Reuse output for exactly identical decoded pixels and algorithm settings.
    pixels_hash=hashlib.sha256(roi.tobytes()).hexdigest()
    key=hashlib.sha256(f'{EXPECTED}:{rotation_deg}:{h}:{w}:{pixels_hash}:v2'.encode()).hexdigest()[:28]
    run_dir=ROOT/'v4_cache'/key
    tracks_path=run_dir/'img1_tracks.json'
    summary_path=run_dir/'summary.json'
    with LOCK:
        if not (tracks_path.is_file() and summary_path.is_file()):
            run_dir.mkdir(parents=True,exist_ok=True)
            # Unicode-safe across Chinese Windows paths.
            ok,encoded=cv2.imencode('.png',roi)
            if not ok:raise RuntimeError('暂存 ROI 编码失败')
            encoded.tofile(str(run_dir/'v4_input.png'))
            spec=importlib.util.spec_from_file_location('local_v4_harness',FROZEN/'run_v4_tests.py')
            module=importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module.check_frozen_inputs(module.load_manifest())
            # A disposable runtime configuration: no source code/model change.
            src=module.make_execution_copy(module.select_inputs('regression',None),run_dir)
            cfg=("ITEMS=[\n"
                 f"    ('img1', {str(run_dir/'v4_input.png')!r}, (0, {h}, 0, {w}), {float(rotation_deg)!r}),\n"
                 "]\n")
            src,n=ITEMS_PATTERN.subn(lambda _:cfg,src,count=1)
            if n!=1:raise RuntimeError('V4 输入配置结构不符合冻结版本')
            # I/O compatibility shim only. Windows OpenCV builds may fail to
            # read/write Unicode paths; model/detection logic remains frozen.
            unicode_io = """
import cv2 as _cv2_uio
import numpy as _np_uio
from pathlib import Path as _Path_uio
def _imread_uio(path, flags=_cv2_uio.IMREAD_COLOR):
    try:
        return _cv2_uio.imdecode(_np_uio.fromfile(str(path), dtype=_np_uio.uint8), flags)
    except (OSError, ValueError):
        return None
def _imwrite_uio(path, img, params=None):
    suffix = _Path_uio(str(path)).suffix or '.png'
    ok, data = _cv2_uio.imencode(suffix, img, [] if params is None else params)
    if ok:
        data.tofile(str(path))
    return bool(ok)
_cv2_uio.imread = _imread_uio
_cv2_uio.imwrite = _imwrite_uio
"""
            src=unicode_io+src
            compile(src,'v4_temporary_execution.py','exec')
            temp_script=run_dir/'v4_temporary_execution.py'
            temp_script.write_text(src,encoding='utf-8')
            with (run_dir/'stdout.txt').open('w',encoding='utf-8') as out, \
                 (run_dir/'stderr.txt').open('w',encoding='utf-8') as err:
                try:
                    proc=subprocess.run([sys.executable,str(temp_script)],cwd=str(FROZEN),
                                        stdout=out,stderr=err,timeout=240,check=False)
                except subprocess.TimeoutExpired as exc:
                    raise RuntimeError('V4 推理超过 240 秒，请检查图像尺寸与运行设备') from exc
            if proc.returncode != 0:
                stderr=(run_dir/'stderr.txt').read_text(encoding='utf-8',errors='replace')[-1200:]
                raise RuntimeError('V4 算法执行失败：'+stderr)
            if not (tracks_path.is_file() and summary_path.is_file()):
                raise RuntimeError('V4 没有输出完整候选轨迹与统计数据')
        tracks=json.loads(tracks_path.read_text(encoding='utf-8'))
        summary=json.loads(summary_path.read_text(encoding='utf-8'))[0]
    return {'first':tracks['first'],'second':tracks['second'],
            'summary':summary,'frozen_sha256':EXPECTED,
            'adapter_roi':[0,h,0,w],'adapter_rotation_deg':rotation_deg,
            'warning':'冻结 V4 的候选轨迹不等于经人工确认的真实物理纱线'}
