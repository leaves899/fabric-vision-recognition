"""Re-run the eight archived real-photo cases without using labels in inference."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
from html import escape
import itertools
import json
from pathlib import Path
import shutil
import time
from uuid import uuid4

import numpy as np
from PIL import Image

from . import VERSION
from .primitives import angular_distance
from .service import AnalysisOptions, ROOT, catalog, execute, sample_bytes, summary


def direction_check(sample_id, result):
    path = ROOT / 'datasets/annotations/drafts' / (sample_id + '.json')
    if not path.is_file():
        return {'status': 'NOT_EVALUATED', 'reason': 'no_operator_reference'}
    label = json.loads(path.read_text(encoding='utf-8'))
    if not label.get('reference_confirmed') or label.get('review_state') != 'OPERATOR_REVIEWED':
        return {'status': 'NOT_EVALUATED', 'reason': 'unconfirmed_operator_reference'}
    if label.get('original_image_sha256') != result['source']['reflection_sha256']:
        raise ValueError('Operator reference image hash differs from inference input')
    references = []
    for key in ('holdout_same', 'check_cross'):
        a, b = np.asarray(label['segments'][key], float)
        references.append(float(np.degrees(np.arctan2(*(b-a)[::-1])) % 180))
    predicted = [f['angle_deg'] for f in result['families']]
    comparison = {'status': 'GEOMETRIC_COMPARISON_ONLY', 'used_for_inference': False,
                  'reference_axes_deg': references, 'predicted_axes_deg': predicted,
                  'reference_semantics': 'Operator physical-continuity hypotheses; not visible-pixel or physical ground truth',
                  'coordinate_conversion': 'Uniform 2x display scaling and translation do not alter axis angles'}
    if len(predicted) == 2:
        permutation = min(itertools.permutations(predicted), key=lambda p: sum(angular_distance(a,b) for a,b in zip(p,references)))
        comparison['optimal_assignment_disagreements_deg'] = [angular_distance(a,b) for a,b in zip(permutation,references)]
    else:
        comparison['optimal_assignment_disagreements_deg'] = None
    return comparison


def run(output, publish_history=False):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    records = []
    started = time.perf_counter()
    for sample in catalog():
        print('RUN', sample['id'], flush=True)
        try:
            front = sample_bytes(sample, 'reflection')
            back = sample_bytes(sample, 'transmission') if sample.get('transmission') else None
            options = AnalysisOptions(**sample['options'])
            result = execute(front, back, options, output / sample['id'], names=[Path(sample[k]).name for k in ('reflection','transmission') if sample.get(k)], sample_id=sample['id'])
            # Verify durable artifacts through fresh file reads, not the return value alone.
            saved = json.loads((output / sample['id'] / 'result.json').read_text(encoding='utf-8'))
            assert saved == json.loads(json.dumps(result, ensure_ascii=False, allow_nan=False)), 'Saved result differs after JSON normalization'
            assert len(saved['stages']) == 14 and all(s['executed'] for s in saved['stages'])
            for item in saved['evidence']['files']:
                p = output / sample['id'] / item['path']
                assert sha256(p.read_bytes()).hexdigest() == item['sha256']
                with Image.open(p) as im:
                    im.verify()
            assert result['physical_accuracy'] == 'NOT_EVALUATED'
            assert not result['eligible_for_physical_release']
            if not options.scale_confirmed:
                assert all(d['count_per_cm'] is None and d['spacing_per_cm'] is None for d in result['density']['families'].values())
                assert all(w['p10_p50_p90_mm'] is None for w in result['widths'])
            record = {'sample_id': sample['id'], 'label': sample['label'], 'execution': 'PASS',
                      'output': sample['id'], 'summary': summary(result),
                      'operator_direction_comparison': direction_check(sample['id'], result)}
            if publish_history:
                run_id = uuid4().hex
                destination = ROOT / 'fabric_measurement/runs' / run_id
                shutil.copytree(output / sample['id'], destination)
                assert (destination / 'result.json').read_bytes() == (output / sample['id'] / 'result.json').read_bytes()
                record['web_run_id'] = run_id
            records.append(record)
            print('DONE', sample['id'], 'Gate3='+result['gate3']['status'],
                  'tracks='+str([f['retained_tracks'] for f in result['families']]),
                  'seconds='+str(round(result['elapsed_seconds'],2)), flush=True)
        except Exception as exc:
            error = type(exc).__name__ + ': ' + str(exc)
            records.append({'sample_id':sample['id'], 'label':sample['label'], 'execution':'FAILED',
                            'error':error})
            print('FAILED', sample['id'], error, flush=True)
    report = {'version': VERSION, 'created_utc': datetime.now(timezone.utc).isoformat(),
              'elapsed_seconds': time.perf_counter()-started,
              'case_count': len(records), 'input_photo_count': 9,
              'execution_passed': sum(r['execution']=='PASS' for r in records),
              'physical_accuracy': 'NOT_EVALUATED', 'records': records}
    (output/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    write_report(report, output)
    print('REPORT', (output/'index.html').resolve(), flush=True)
    return report


def write_report(report, output):
    lines = ['# 此前照片的真实运行记录', '',
             f"{report['case_count']} 个案例、{report['input_photo_count']} 张输入照片；完整执行 {report['execution_passed']}/{report['case_count']}。",
             '未修改阈值以适配这些照片。所有人工方向标注只在推理完成后作几何对照，没有用于自动取向、选参或连线。', '',
             '| 样本 | 输入 | A/B 方向角 | A/B 候选片段 | 双路径像素密度 A/B | 宽度有效剖面 A/B | Gate 3 |',
             '|---|---|---|---|---|---|---|']
    sections = []
    for record in report['records']:
        sid = record['sample_id']
        if record['execution'] != 'PASS':
            lines.append(f"| {sid} | FAILED | {record['error']} | — | — | — | — |")
            sections.append('<p>'+escape(sid+': '+record['error'])+'</p>')
            continue
        r = record['summary']
        angles = ' / '.join(f"{f['angle_deg']:.2f}°" for f in r['families']) or '无双方向'
        tracks = ' / '.join(str(f['retained_tracks']) for f in r['families']) or '0'
        density = '；'.join(f"{d['family']}: "+(f"{d['count_per_px']:.5f} / {d['spacing_per_px']:.5f}" if d['count_per_px'] else '无可用截线') for d in r['density']['families'].values()) or '不可计算'
        widths = ' / '.join(str(w['valid_profiles']) for w in r['widths']) or '0'
        lines.append(f"| {sid} | {r['input_mode']} | {angles} | {tracks} | {density} | {widths} | {r['gate3']['status']} |")
        sections.append(f'<section><h2>{escape(record["label"])} · {sid}</h2><p>{escape(angles)}；候选片段 {tracks}；Gate 3 {r["gate3"]["status"]}</p><p><a href="{sid}/review.html">逐条查看轨迹和全部模块</a> · <a href="{sid}/result.json">完整 JSON</a></p><a href="{sid}/review.html"><img loading="lazy" src="{sid}/centerlines_both.png" alt="{sid} 中心线候选"></a></section>')
    lines += ['', '## 核验方式与结果边界', '',
              '- 每张输入按登记 SHA-256 核验；原生 ROI 和输入条件随 JSON 保存。',
              '- 逐个重新读取结果 JSON，核对 14 个步骤状态，并重新解码所有证据 PNG 和校验哈希。',
              '- 单图不伪造透射图；未确认尺度时，正式物理密度与毫米宽度为 null。双图历史尺度仅进入 candidate 字段。',
              '- 中心线是候选片段，可能漏检、断裂或重复，不等于实际物理纱线数量。两条密度路径共享检测结果。',
              '- Gate 3 与模块 PASS 只代表内部条件；本轮没有独立逐根计数、宽度或浮沉真值，识别准确率仍为 NOT_EVALUATED。',
              '- 报告 W088/W114/W054 的原始配对输入、尺度和参数未提供，本轮不声称复现其数值。',
              '- Ne/tex 规则表未提供，当前案例保留 UNAVAILABLE；规则引擎的换算通过合成数值检查。', '',
              '## 人工方向对照', '',
              '以下仅比较自动双方向与已有操作员轨迹方向。标注不是可见像素真值；差异不能转换为逐根识别准确率。', '']
    for record in report['records']:
        check = record.get('operator_direction_comparison', {})
        if check.get('optimal_assignment_disagreements_deg') is not None:
            lines.append(f"- {record['sample_id']}："+' / '.join(f'{x:.3f}°' for x in check['optimal_assignment_disagreements_deg']))
    (output/'results.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    page='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>此前照片测试结果</title><style>body{max-width:1100px;margin:30px auto;padding:0 20px;background:#f3f6f4;color:#243b36;font:15px system-ui;line-height:1.8}section{background:white;padding:22px;border:1px solid #d4dfda;border-radius:12px;margin:24px 0}img{width:100%;max-height:720px;object-fit:contain}a{color:#127364}</style><h1>此前照片测试结果</h1>'
    page += f'<p>{report["case_count"]} 个案例，9 张输入照片，完整执行 {report["execution_passed"]}/{report["case_count"]}。质量未通过的案例完整保留。候选片段不是物理纱线根数；真实识别准确率未评估。</p><p><a href="results.md">测试说明</a> · <a href="summary.json">逐项数据与方向对照</a></p>'
    (output/'index.html').write_text(page+''.join(sections)+'</html>',encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--publish-history', action='store_true')
    args = parser.parse_args()
    result = run(args.output, args.publish_history)
    raise SystemExit(0 if result['execution_passed'] == result['case_count'] else 1)


if __name__ == '__main__':
    main()
