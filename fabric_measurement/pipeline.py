"""Executable paired-image implementation of the report's full technical route."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import time

import cv2
import numpy as np
from PIL import Image

from . import VERSION
from .centerlines import detect_pair
from .config import Settings
from .geometry import calibration, quality, rectify, register_pair
from .measurements import density_summary, measure_widths
from .structure import twill_analysis, weave_analysis, yarn_reference
from .primitives import _overlay, load_rgb, save_rgb


def quality_gate(result):
    """The report permits auxiliary warnings when core input/density/width pass."""
    reasons = []
    if result.get('input_mode') == 'REFLECTION_ONLY':
        reasons.append('transmission_not_provided')
    if any(q['status'] != 'PASS' for q in result['image_quality'].values()):
        reasons.append('input_quality')
    if result['registration']['status'] != 'PASS':
        reasons.append('registration')
    if result['calibration']['status'] != 'CONFIRMED':
        reasons.append('physical_scale_not_confirmed')
    if len(result['families']) != 2 or any(f['status'] != 'INTERNAL_CONSISTENT_CANDIDATE' for f in result['families']):
        reasons.append('density_or_centerlines')
    if {f['identity'] for f in result['families']} != {'warp_candidate', 'weft_candidate'}:
        reasons.append('warp_weft_identity_not_mapped')
    if len(result['widths']) != 2 or any(w['status'] != 'PASS' for w in result['widths']):
        reasons.append('widths')
    if result.get('evidence', {}).get('status') != 'PASS':
        reasons.append('evidence')
    warnings = []
    if result['twill']['status'] != 'PASS':
        warnings.append('twill_low_confidence')
    if result['weave']['status'] != 'CANDIDATE':
        warnings.append('weave_low_confidence')
    if not result['yarn_reference'] or any(y['status'] != 'AVAILABLE' for y in result['yarn_reference']):
        warnings.append('Ne_tex_reference_unavailable')
    return dict(status='PASS' if not reasons else 'LOW_CONFIDENCE', reasons=reasons,
                auxiliary_warnings=warnings, physical_accuracy='NOT_EVALUATED',
                eligible_for_physical_release=False,
                meaning='implementation quality conditions, not physical ground-truth accuracy')


def analyze_pair(front, back=None, cfg=None, *, mm_per_px=None, scale_confirmed=False,
                 warp_angle=None, prealigned=False, front_corners=None, back_corners=None,
                 target_size=None, roi=None):
    cfg = cfg or Settings()
    started = time.perf_counter()
    if warp_angle is not None and not np.isfinite(warp_angle):
        raise ValueError('warp_angle must be finite')
    # Validate both arrays before any rectification/OpenCV operation.
    quality(front, cfg)
    if back is not None:
        quality(back, cfg)
    def display_rgb(image):
        image = np.asarray(image)
        if not np.issubdtype(image.dtype, np.integer) and image.max() <= 1:
            image = image * 255
        image = np.uint8(image)
        return np.repeat(image[...,None],3,axis=2) if image.ndim == 2 else image.copy()
    front = display_rgb(front)
    back = display_rgb(back) if back is not None else None
    if back is not None and (front_corners is None) != (back_corners is None):
        raise ValueError('Provide corners for both images or for neither')
    if back is None and back_corners is not None:
        raise ValueError('Transmission corners require a transmission image')
    front, fm = rectify(front, front_corners, target_size, roi)
    if max(front.shape[:2]) > 1200:
        raise ValueError('Select a native-pixel ROI with both sides at most 1200 px')
    bm = None
    if back is not None:
        back, bm = rectify(back, back_corners, target_size, roi)
    cal = calibration(mm_per_px, scale_confirmed)
    if back is not None:
        registered, valid, registration = register_pair(front, back, cfg, prealigned)
    else:
        registered, valid = None, np.ones(front.shape[:2], dtype=bool)
        registration = dict(status='NOT_APPLICABLE', reasons=['single_reflection_image'],
                            method=None, median_local_residual_px=None)
    families, direction, responses, local = detect_pair(front, registered, valid, cfg,
                                                        cal['mm_per_px'], warp_angle)
    widths = measure_widths(front, families, cfg, cal['mm_per_px'], back is None or registration['status'] == 'PASS')
    density = density_summary(families, cal)
    twill = twill_analysis(front, families, cfg)
    weave = weave_analysis(front, families, responses, cfg, back is None or registration['status'] == 'PASS')
    yarn = yarn_reference(widths, density, cfg.yarn_reference_rules)
    image_quality = {'reflection': quality(front, cfg)}
    if back is not None:
        image_quality['transmission'] = quality(back, cfg)
    result = dict(version=VERSION, settings=asdict(cfg), input_shape_hw=list(front.shape[:2]),
                  input_mode='PAIRED' if back is not None else 'REFLECTION_ONLY',
                  warp_hint_deg=warp_angle, warp_hint_coordinate_space='FINAL_ROI',
                  geometry=dict(front_source_to_roi=fm.tolist(), transmission_source_to_roi=bm.tolist() if bm is not None else None,
                                roi_xywh=roi, camera_profile=cfg.camera_profile,
                                camera_profile_usage='metadata only; no unspecified camera correction applied'),
                  calibration=cal, registration=registration,
                  image_quality=image_quality,
                  direction_analysis=direction, families=families, density=density,
                  widths=widths, twill=twill, weave=weave, yarn_reference=yarn,
                  evidence=dict(status='NOT_WRITTEN'), physical_accuracy='NOT_EVALUATED',
                  eligible_for_physical_release=False,
                  reproduction_scope='feasibility-report technical route; independent implementation choices',
                  original_report_sample_reproduction='NOT_EVALUATED; this implementation does not reproduce the report sample numbers',
                  elapsed_seconds=time.perf_counter() - started)
    buffers = dict(front=front, back=registered, valid=valid, responses=responses, local=local)
    return result, buffers


def _json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def _stages(result):
    f = result['families']
    width_status = 'PASS' if len(result['widths']) == 2 and all(w['status'] == 'PASS' for w in result['widths']) else 'LOW_CONFIDENCE'
    return [
        ('01', '图片质量 Gate', 'PASS' if all(x['status'] == 'PASS' for x in result['image_quality'].values()) else 'LOW_CONFIDENCE'),
        ('02', '有效织物 ROI', 'PASS'),
        ('03', '几何与光照归一化、双图配准', result['registration']['status']),
        ('04', 'Structure Tensor 局部方向场', result['direction_analysis']['status']),
        ('05', '分方向滤波增强', 'PASS' if len(f) == 2 else 'UNAVAILABLE'),
        ('06', 'Ridge Detection 与中心线连接', 'PASS' if len(f) == 2 and all(x['retained_tracks'] for x in f) else 'LOW_CONFIDENCE'),
        ('07', '中心线清洗', 'PASS' if len(f) == 2 and all(x['retained_tracks'] for x in f) else 'LOW_CONFIDENCE'),
        ('08', '经向提示映射', 'PASS' if {x['identity'] for x in f} == {'warp_candidate', 'weft_candidate'} else 'UNAVAILABLE'),
        ('09', '计数与中位间距双路径密度', 'PASS' if len(f) == 2 and all(x['status'] == 'INTERNAL_CONSISTENT_CANDIDATE' for x in f) else 'LOW_CONFIDENCE'),
        ('10', '经密、纬密与经纬比', 'PASS' if result['density']['ratio_count'] is not None and result['calibration']['status'] == 'CONFIRMED' else 'LOW_CONFIDENCE'),
        ('11', '经纬纱表观宽度', width_status),
        ('12', '左斜右斜与斜纹角度', result['twill']['status']),
        ('13', '交点浮沉与组织候选', result['weave']['status']),
        ('14', 'Gate 3 综合质量判断', result['gate3']['status']),
    ]


def _review_page(result, out):
    h, w = result['input_shape_hw']
    groups = []
    options = ['<option value="all">全部轨迹</option>']
    for family, color in zip(result['families'], ['#1ee6ff', '#ff64dc']):
        parts = []
        for track in family['tracks']:
            if not track['accepted_candidate']:
                continue
            key = f"{family['id']}{track['id']}"
            options.append(f'<option value="{key}">{key}</option>')
            pts, frame = track['points_xy'], track['points']
            edges = []
            for i in range(1, len(pts)):
                a, b = pts[i - 1], pts[i]
                gap = frame[i][0] - frame[i - 1][0] > 1.5 * family['linking']['sample_step_px']
                dash = 'stroke-dasharray="4 4"' if gap else ''
                edges.append(f'<path d="M{a[0]:.2f},{a[1]:.2f} L{b[0]:.2f},{b[1]:.2f}" {dash}/>')
            dots = ''.join(f'<circle class="point" cx="{p[0]:.2f}" cy="{p[1]:.2f}" r="1.6" fill="{color}"/>' for p in pts)
            mid = pts[len(pts) // 2]
            label = f'<text x="{mid[0]:.2f}" y="{mid[1]:.2f}" fill="{color}" stroke="none" font-size="11">{key}</text>'
            parts.append(f'<g class="track" data-id="{key}"><title>{key} {family["source"]} {family["polarity"]}</title>'+''.join(edges)+dots+label+'</g>')
        groups.append(f'<g id="{family["id"]}" fill="none" stroke="{color}" stroke-width="1.2">'+''.join(parts)+'</g>')
    rows = ''.join(f'<tr><td>{number}</td><td>{escape(name)}</td><td>{escape(status)}</td></tr>' for number, name, status in _stages(result))
    counts = '；'.join(f'{f["id"]}组 {f["retained_tracks"]} 个候选片段，{f["angle_deg"]:.2f}°，来源 {f["source"]}，{f["polarity"]}' for f in result['families']) or '未形成两组中心线'
    transmission_button = ('<button onclick="document.getElementById(\'base\').setAttribute(\'href\',\'transmission_registered.png\')">透射图</button>'
                           if result.get('input_mode') == 'PAIRED' else '<span>单张反射图：无透射证据</span>')
    short = dict(density=result['density'], widths=[{k: v for k, v in x.items() if k != 'samples'} for x in result['widths']],
                 twill={k: v for k, v in result['twill'].items() if k not in ('spectra', 'segments')},
                 weave={k: v for k, v in result['weave'].items() if k not in ('matrix', 'intersections', 'float_lengths')},
                 yarn_reference=result['yarn_reference'], gate3=result['gate3'])
    page=f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>技术路线复现结果</title><style>body{{font:16px system-ui;background:#18202a;color:#eee;max-width:1200px;margin:24px auto;padding:0 16px}}a{{color:#8de}}label{{margin-right:16px}}.viewport{{overflow:auto}}svg{{width:100%;height:auto}}.point{{display:none}}table{{border-collapse:collapse;width:100%}}td,th{{text-align:left;border:1px solid #53616d;padding:8px}}pre{{white-space:pre-wrap;overflow-wrap:anywhere}}.evidence img{{max-width:100%}}button,select{{padding:6px}}</style>
<h1>可行性报告技术路线复现</h1><p>版本 {VERSION}；Gate 3：{result['gate3']['status']}。{escape(counts)}</p>
<p>候选片段编号不等于物理纱线根数。实线连接相邻观测，虚线跨越缺失采样。未有独立真值的准确率记为 NOT_EVALUATED。</p>
<p><label><input id="showA" type="checkbox" checked onchange="toggle('A',this.checked)">A组</label><label><input id="showB" type="checkbox" checked onchange="toggle('B',this.checked)">B组</label>
<label><input type="checkbox" onchange="document.querySelectorAll('.point').forEach(n=>n.style.display=this.checked?'inline':'none')">采样点</label>
<select aria-label="选择候选轨迹" onchange="document.querySelectorAll('.track').forEach(n=>n.style.display=this.value==='all'||n.dataset.id===this.value?'inline':'none')">{''.join(options)}</select>
<button onclick="document.getElementById('base').setAttribute('href','reflection.png')">反射图</button>{transmission_button}</p>
<p>缩放 <input aria-label="缩放" type="range" min="100" max="250" value="100" oninput="document.getElementById('canvas').style.width=this.value+'%'"> · <a href="result.json">完整逐点JSON</a> · <a href="run_summary.json">运行记录</a></p>
<div class="viewport"><svg id="canvas" viewBox="0 0 {w} {h}"><image id="base" href="reflection.png" width="{w}" height="{h}"/>{''.join(groups)}</svg></div>
<h2>技术路线各步骤</h2><table><tr><th>步骤</th><th>模块</th><th>本次输出状态</th></tr>{rows}</table>
<h2>测量与质量结果</h2><pre>{escape(json.dumps(short,ensure_ascii=False,indent=2))}</pre>
<h2>可视化证据</h2><div class="evidence">'''
    for filename, title in [('direction_field.png', '局部方向场'), ('centerlines_A.png', 'A组中心线'),
                            ('centerlines_B.png', 'B组中心线'), ('width_edges.png', '宽度边缘'),
                            ('twill.png', '斜纹线段'), ('float_matrix.png', '交点浮沉矩阵')]:
        page += f'<h3>{title}</h3><a href="{filename}"><img loading="lazy" src="{filename}" alt="{title}"></a>'
    page += '</div><script>function toggle(id,on){document.getElementById(id)?.setAttribute("visibility",on?"visible":"hidden")}</script></html>'
    (out/'review.html').write_text(page, encoding='utf-8')


def write_artifacts(result, buffers, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    front, back = buffers['front'], buffers['back']
    save_rgb(out/'reflection.png', front)
    if back is not None:
        save_rgb(out/'transmission_registered.png', back)
    save_rgb(out/'valid_mask.png', buffers['valid'].astype(np.uint8)*255)
    field = front.copy()
    angles, coherence, _ = buffers['local']
    h, w = front.shape[:2]
    for y in range(8, angles.shape[0]-8, 16):
        for x in range(8, angles.shape[1]-8, 16):
            if coherence[y,x] < .35:
                continue
            angle=np.deg2rad(angles[y,x])
            center=np.array([x*w/angles.shape[1], y*h/angles.shape[0]])
            delta=8*np.array([np.cos(angle),np.sin(angle)])
            cv2.line(field,tuple(np.rint(center-delta).astype(int)),tuple(np.rint(center+delta).astype(int)),(40,255,110),1,cv2.LINE_AA)
    save_rgb(out/'direction_field.png',field)
    combined=front.copy()
    for index in range(2):
        family=result['families'][index] if len(result['families'])>index else None
        image=_overlay(front,family['tracks'],[(30,230,255),(255,100,220)][index],family['linking']['sample_step_px']) if family else front.copy()
        save_rgb(out/f'centerlines_{"AB"[index]}.png',image)
        if family:
            combined=_overlay(combined,family['tracks'],[(30,230,255),(255,100,220)][index],family['linking']['sample_step_px'])
            save_rgb(out/f'response_{family["id"]}.png',np.uint8(np.clip(buffers['responses'][family['id']]/2,0,1)*255))
    save_rgb(out/'centerlines_both.png',combined)
    edges=front.copy()
    for width,color in zip(result['widths'],[(30,230,255),(255,190,30)]):
        for sample in width['samples']:
            if not sample['retained']:
                continue
            a,b=np.rint(sample['edges_xy']).astype(int)
            cv2.line(edges,tuple(a),tuple(b),color,1,cv2.LINE_AA)
            for p in (a,b):
                cv2.circle(edges,tuple(p),2,(255,255,255),-1)
    save_rgb(out/'width_edges.png',edges)
    twill=front.copy()
    for segment in result['twill']['segments']:
        if segment['supports_candidate']:
            a,b=np.rint(segment['xy']).astype(int)
            cv2.line(twill,tuple(a),tuple(b),(255,60,60),2,cv2.LINE_AA)
    save_rgb(out/'twill.png',twill)
    matrix=np.asarray(result['weave']['matrix'],int)
    if not matrix.size:
        matrix=np.full((1,1),-1)
    palette=np.array([[130,130,130],[220,65,65],[50,175,70]],np.uint8)
    cells=palette[matrix+1]
    matrix_image=cv2.resize(cells,None,fx=32,fy=32,interpolation=cv2.INTER_NEAREST)
    for row in range(matrix.shape[0]):
        for col in range(matrix.shape[1]):
            label='?' if matrix[row,col]<0 else '+' if matrix[row,col] else '-'
            cv2.putText(matrix_image,label,(col*32+9,row*32+22),cv2.FONT_HERSHEY_SIMPLEX,.55,(255,255,255),1,cv2.LINE_AA)
    save_rgb(out/'float_matrix.png',matrix_image)
    evidence=[]
    for file in sorted(out.glob('*.png')):
        with Image.open(file) as image:
            image.verify()
        evidence.append(dict(path=file.name,sha256=sha256(file.read_bytes()).hexdigest(),bytes=file.stat().st_size))
    result['evidence']=dict(status='PASS',meaning='files generated and decoded successfully; not recognition accuracy',files=evidence)
    result['gate3']=quality_gate(result)
    result['stages']=[dict(id=i,name=n,status=s,implemented=True,executed=True) for i,n,s in _stages(result)]
    _json(out/'result.json',result)
    _review_page(result,out)
    _json(out/'run_summary.json',dict(version=VERSION,created_utc=datetime.now(timezone.utc).isoformat(),
                                    gate3=result['gate3'],stages=result['stages'],source=result.get('source'),
                                    source_hashes={p.name:sha256(p.read_bytes()).hexdigest() for p in sorted(Path(__file__).parent.glob('*.py'))},
                                    outputs=['result.json','review.html']+[e['path'] for e in evidence]))


def run_files(front_path, back_path, output, cfg=None, **kwargs):
    output=Path(output)
    if output.exists():
        raise FileExistsError('Choose a new output directory: '+str(output))
    front_path=Path(front_path)
    back_path=Path(back_path) if back_path is not None else None
    result,buffers=analyze_pair(load_rgb(front_path),load_rgb(back_path) if back_path else None,cfg,**kwargs)
    result['source']=dict(reflection=str(front_path.resolve()),transmission=str(back_path.resolve()) if back_path else None,
                          reflection_sha256=sha256(front_path.read_bytes()).hexdigest(),
                          transmission_sha256=sha256(back_path.read_bytes()).hexdigest() if back_path else None)
    write_artifacts(result,buffers,output)
    return result
