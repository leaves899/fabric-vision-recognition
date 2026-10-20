from __future__ import annotations

"""R/T capture-conditioned diagnostic sweep, not a formal accuracy benchmark.

Pairs are NEVER fabricated by duplicating a single image. Absolute density is
not certified because the checked-in pair lacks validated calibration/camera metadata.
"""

import csv
import dataclasses
import json
import sys
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from engine.config import EngineConfig
from engine import pipeline
from engine.width import map_centerlines_to_reflection

PAIRED = HERE / "tmp" / "pair_test"
OUT = REPO / "experiments" / "shibie-capture-conditioned-20261020"
# All variants are registered before looking at results. First is frozen default.
VARIANTS = {
    "default_v063": {},
    "min_density_10": {"density_min_per_cm": 10.0},
    "min_density_8": {"density_min_per_cm": 8.0},
    "min_density_10_roi96": {"density_min_per_cm": 10.0, "roi_ratio": 0.96},
}


def imread(path: Path):
    image = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"DECODING_FAILED {path}")
    return image


def lines_overlay(image, lines, tone, max_lines=150):
    for line in lines[:max_lines]:
        pts = np.asarray(line, dtype=np.float32)
        if len(pts) < 2:
            continue
        cv2.polylines(image, [np.rint(pts).astype(np.int32)], False, tone, 2, cv2.LINE_AA)
    return image


def run_once(name, override, front_bytes, trans_bytes, raw_trans):
    cfg = dataclasses.replace(EngineConfig(), **override)
    pipeline.DEFAULT_CONFIG = cfg
    cache = {}
    original = pipeline._run_direction

    def save_seed(normalized, angle, mmx, mmy):
        obj = original(normalized, angle, mmx, mmy)
        cache[round(float(angle) % 180.0, 4)] = obj
        return obj

    pipeline._run_direction = save_seed
    try:
        result = pipeline.run_measurement(
            front_bytes, trans_bytes,
            # Nominal camera-profile target only. There is no frame calibration
            # metadata in this pair; printed density is therefore diagnostic.
            mm_per_px_x=0.0125, mm_per_px_y=0.0125,
            warp_axis_hint="vertical",
            sample_id="paired_"+name,
        )
    finally:
        pipeline._run_direction = original
        pipeline.DEFAULT_CONFIG = EngineConfig()

    status = result.get("status", "FAIL")
    orientation = result.get("orientation") or {}
    normalization = result.get("normalization") or {}
    image = raw_trans.copy()
    identity = np.array([[1., 0., 0.], [0., 1., 0.]], np.float32)
    line_count = {}
    # Draw in ORIGINAL transmission coordinates: no R/T registration necessary.
    # Only the chosen pair is shown, never all candidate/alternative lines.
    for family, color in (("warp", (0, 30, 255)), ("weft", (255, 240, 0))):
        angle = orientation.get(f"{family}_direction_deg")
        selection = cache.get(round(float(angle) % 180.0, 4)) if angle is not None else None
        lines = map_centerlines_to_reflection(
            selection["_width_seed"], normalization, identity
        ) if selection is not None and normalization else []
        line_count[family] = len(lines)
        lines_overlay(image, lines, color)
    folder = OUT / "overlays"
    folder.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(folder / f"{name}.png"), image)
    twill = result.get("twill") or {}
    dens = result.get("density_debug") or {}
    row = {
        "variant": name, "parameters": json.dumps(override, ensure_ascii=False),
        "status": status, "gate3": (result.get("gate3") or {}).get("status"),
        "warp_line_count": line_count.get("warp"),
        "weft_line_count": line_count.get("weft"),
        "warp_spacing_px": ((dens.get("warp") or {}).get("centerline") or {}).get("median_center_spacing_px"),
        "weft_spacing_px": ((dens.get("weft") or {}).get("centerline") or {}).get("median_center_spacing_px"),
        "warp_acf_px": ((dens.get("warp") or {}).get("periodicity") or {}).get("spacing_px"),
        "weft_acf_px": ((dens.get("weft") or {}).get("periodicity") or {}).get("spacing_px"),
        "warp_reasons": "|".join((((dens.get("warp") or {}).get("confidence") or {}).get("reasons") or [])),
        "weft_reasons": "|".join((((dens.get("weft") or {}).get("confidence") or {}).get("reasons") or [])),
        "weave_candidate": twill.get("weave_candidate"),
        "weave_status": twill.get("weave_status"),
        "assumed_mm_per_px": 0.0125, "certified_physical_density": False,
        "overlay": str((folder / f"{name}.png").relative_to(OUT)),
    }
    print(json.dumps(row, ensure_ascii=False), flush=True)
    return row


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    front_path = PAIRED / "front.png"
    trans_path = PAIRED / "transmission.png"
    if not front_path.exists() or not trans_path.exists():
        raise FileNotFoundError("TRUE_PAIRED_REFLECTION_TRANSMISSION_REQUIRED")
    fb = front_path.read_bytes()
    tb = trans_path.read_bytes()
    fimg, timg = imread(front_path), imread(trans_path)
    cv2.imwrite(str(OUT / "original_transmission.png"), timg)
    cv2.imwrite(str(OUT / "original_reflection.png"), fimg)
    rows = []
    for name, overrides in VARIANTS.items():
        rows.append(run_once(name, overrides, fb, tb, timg))
    with (OUT / "measurements.csv").open("w", encoding="utf-8-sig", newline="") as h:
        w = csv.DictWriter(h, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    (OUT / "measurements.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    report = [
        "# 真实反射/透射双图：采集条件针对性参数消融",
        "",
        "本实验仅使用仓库已存在的真正 R/T 双图，同位置假设基于原文件名和既有配对记录，未取得 Camera Profile。",
        f"反射和透射图像尺寸：{fimg.shape[1]}×{fimg.shape[0]} / {timg.shape[1]}×{timg.shape[0]}。",
        "图像不符合 8000×6000 原生分辨率条件，因此仅是 PoC 失败机制排查，不属于正式采集工位的精度验证。",
        "0.0125mm/px 仅是目标工位名义值，本图没有独立标尺标定，不输出正式根/cm。",
        "红线为推理得到的 warp 候选中心线，青色为 weft 候选中心线；图覆盖在真实透射图上，而非绘制在没有验证配准的反射图上。",
        "ACF 峰仅作为辅助周期，不是单根物理纱线真值。任何看似增加线数的变化仍需视觉检查。",
        "",
        "| 参数 | warp中心线 | 纬向中心线 | warp中心间距px | 纬向中心间距px | warp ACFpx | 纬向ACFpx | 状态 |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for r in rows:
        report.append(f"| {r['variant']} | {r['warp_line_count']} | {r['weft_line_count']} | {r['warp_spacing_px']} | {r['weft_spacing_px']} | {r['warp_acf_px']} | {r['weft_acf_px']} | {r['status']} |")
    report.extend([
        "",
        "## 检视入口",
        "在 GitHub Actions 的图像 artifact 中查看 `original_transmission.png`、`original_reflection.png` 和 `overlays/*.png`，对比每条线是否为实体纱线。",
        "目前不存在通过认证的 50MP 原始 R/T Golden Dataset，禁止以本试验的线数与 PASS 状态宣称量产准确率。",
        "仅当留出布料的中心线/截线真值检查没有回归时，才可以冻结和合入新参数。",
    ])
    (OUT / "report.md").write_text("\n".join(report)+"\n", encoding="utf-8")


if __name__ == "__main__":
    main()
