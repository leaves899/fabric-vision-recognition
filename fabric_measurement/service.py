"""Shared request contract and durable results for the web UI and batch runner."""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from typing import Annotated

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .config import Settings
from .pipeline import analyze_pair, write_artifacts

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 20 * 1024 * 1024
MAX_PIXELS = 32_000_000
Point = tuple[float, float]
PositiveRange = tuple[Annotated[float, Field(gt=0, allow_inf_nan=False)],
                      Annotated[float, Field(gt=0, allow_inf_nan=False)]]


class ReferenceRule(BaseModel):
    model_config = ConfigDict(extra='forbid')
    identity: str | None = None
    width_mm: PositiveRange
    density_per_cm: PositiveRange
    Ne: PositiveRange
    source: str = Field(min_length=1, max_length=500)

    @model_validator(mode='after')
    def validate_ranges(self):
        if self.identity not in (None, 'warp_candidate', 'weft_candidate'):
            raise ValueError('纱支规则 identity 仅支持 warp_candidate / weft_candidate')
        if not self.source.strip() or any(a > b for a, b in (self.width_mm, self.density_per_cm, self.Ne)):
            raise ValueError('纱支规则区间必须递增，并填写来源')
        return self


class AnalysisOptions(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    roi: tuple[int, int, int, int] | None = None
    warp_angle: float | None = Field(default=None, ge=0, lt=180)
    mm_per_px: float | None = Field(default=None, gt=0, le=100)
    scale_confirmed: bool = False
    prealigned: bool = False
    front_corners: tuple[Point, Point, Point, Point] | None = None
    back_corners: tuple[Point, Point, Point, Point] | None = None
    target_size: tuple[int, int] | None = None
    yarn_reference_rules: list[ReferenceRule] = Field(default_factory=list, max_length=100)
    camera_profile: str = Field(default='', max_length=120)

    @model_validator(mode='after')
    def validate_options(self):
        if self.scale_confirmed and self.mm_per_px is None:
            raise ValueError('确认标定前必须输入 mm_per_px')
        if self.roi and (min(self.roi[:2]) < 0 or min(self.roi[2:]) < 128 or max(self.roi[2:]) > 1200):
            raise ValueError('ROI 起点不能为负，宽高须为 128..1200 原生像素')
        if self.front_corners is not None and self.target_size is None:
            raise ValueError('透视校正必须指定 target_size')
        if self.target_size and (min(self.target_size) < 128 or max(self.target_size) > 1200):
            raise ValueError('校正后尺寸须为 128..1200 像素')
        if self.target_size and self.front_corners is None:
            raise ValueError('target_size 需要透视四角，不能静默缩放原图')
        return self

    def pipeline_arguments(self):
        return self.model_dump(exclude={'yarn_reference_rules', 'camera_profile'})

    def settings(self):
        rules = tuple(r.model_dump(exclude_none=True) for r in self.yarn_reference_rules)
        return Settings(yarn_reference_rules=rules,
                        camera_profile={'name': self.camera_profile} if self.camera_profile else {})


def decode_image(data):
    if not data or len(data) > MAX_BYTES:
        raise ValueError('每张图片须为非空文件，且不超过 20 MB')
    try:
        with Image.open(BytesIO(data)) as image:
            if image.width * image.height > MAX_PIXELS or max(image.size) > 10000 or min(image.size) < 128:
                raise ValueError('图片短边须至少 128 px，最长边至多 10000 px，总像素至多 3200 万')
            if image.format not in ('JPEG', 'PNG', 'WEBP', 'BMP', 'TIFF'):
                raise ValueError('请使用 JPG、PNG、WEBP、BMP 或 TIFF')
            return np.array(ImageOps.exif_transpose(image).convert('RGB'))
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError('无法解码图片，请检查文件格式和完整性') from exc


def catalog():
    return json.loads((Path(__file__).parent / 'sample_catalog.json').read_text(encoding='utf-8'))


def sample_by_id(sample_id):
    for sample in catalog():
        if sample['id'] == sample_id:
            return sample
    raise KeyError(sample_id)


def sample_bytes(sample, kind):
    if kind not in ('reflection', 'transmission') or not sample.get(kind):
        raise KeyError(kind)
    data = (ROOT / sample[kind]).read_bytes()
    if sha256(data).hexdigest() != sample[kind + '_sha256']:
        raise ValueError('样本哈希与登记记录不一致：' + sample['id'])
    return data


def execute(reflection, transmission, options, output, *, names=None, sample_id=None):
    """Write once to a new directory; expose completion only after evidence verification."""
    if Path(output).exists():
        raise FileExistsError('结果目录已存在，拒绝覆盖')
    if transmission is not None and sha256(reflection).digest() == sha256(transmission).digest():
        raise ValueError('反射图与透射图完全相同，请提供两种光照的不同图片')
    front = decode_image(reflection)
    back = decode_image(transmission) if transmission is not None else None
    result, buffers = analyze_pair(front, back, options.settings(), **options.pipeline_arguments())
    result['source'] = {
        'sample_id': sample_id,
        'filenames': [str(n).replace('\\', '/').split('/')[-1] for n in (names or [])],
        'reflection_sha256': sha256(reflection).hexdigest(),
        'transmission_sha256': sha256(transmission).hexdigest() if transmission is not None else None,
        'reflection_shape_hw': list(front.shape[:2]),
        'transmission_shape_hw': list(back.shape[:2]) if back is not None else None,
        'options': options.model_dump(),
        'coordinate_convention': 'EXIF oriented source; ROI in source pixels, or rectified pixels when corners supplied',
    }
    write_artifacts(result, buffers, output)
    return result


def summary(result):
    """Small frontend record; all sample points remain in the downloadable JSON."""
    return {
        'version': result['version'], 'input_mode': result['input_mode'],
        'source': result.get('source'), 'input_shape_hw': result['input_shape_hw'],
        'elapsed_seconds': result['elapsed_seconds'],
        'calibration': result['calibration'], 'registration': result['registration'],
        'gate3': result['gate3'], 'stages': result['stages'],
        'image_quality': result['image_quality'], 'density': result['density'],
        'families': [{k: f[k] for k in ('id', 'identity', 'angle_deg', 'source', 'polarity',
                                       'retained_tracks', 'status', 'reasons', 'hypothesis_margin')}
                     | {'median_spacing_px': f['density'].get('median_spacing_px')} for f in result['families']],
        'widths': [{k: v for k, v in w.items() if k != 'samples'} for w in result['widths']],
        'twill': {k: v for k, v in result['twill'].items() if k not in ('spectra', 'segments')},
        'weave': {k: v for k, v in result['weave'].items() if k not in ('matrix', 'intersections', 'float_lengths')},
        'yarn_reference': result['yarn_reference'], 'evidence': result['evidence'],
        'physical_accuracy': result['physical_accuracy'],
    }
