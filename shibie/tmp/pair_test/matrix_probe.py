"""收紧参数后的回归：grace 与 min_peak 两档。"""
import sys, os, json, time, dataclasses
import numpy as np
import openpyxl

ROOT = os.path.dirname(os.path.abspath(__file__))
SHIBIE = os.path.abspath(os.path.join(ROOT, "..", ".."))
sys.path.insert(0, SHIBIE)

from engine.config import EngineConfig
from engine import pipeline
import engine.pipeline as P

SAMPLES_DIR = os.path.join(SHIBIE, "tmp", "fabricnet")
MM_X, MM_Y = 0.0078125, 0.0083333

wb = openpyxl.load_workbook(os.path.join(SAMPLES_DIR, "FabricNet_parameters.xlsx"), data_only=True)
rows = list(wb.active.iter_rows(values_only=True))[1:]
truth = {int(r[0]): (r[2], r[3], r[4]) for r in rows if r[0] is not None}

pick = [f"W{i:03d}.jpg" for i in range(1, 131)][::7][:20]

CONFIGS = {
    "off": {"steerable_periodicity_tiebreak": False},
    "on_grace06": {},
    "on_grace02": {"steerable_quality_close_margin": 0.02},
    "on_grace06_peak35": {"steerable_periodicity_tiebreak_min_peak": 0.35},
}

res = {}
for cname, over in CONFIGS.items():
    cfg = dataclasses.replace(EngineConfig(), **over)
    P.DEFAULT_CONFIG = cfg
    vals = {}
    for nm in pick:
        p = os.path.join(SAMPLES_DIR, nm)
        if not os.path.exists(p):
            continue
        data = open(p, "rb").read()
        r = pipeline.run_measurement(data, data, mm_per_px_x=MM_X, mm_per_px_y=MM_Y,
                                     warp_axis_hint="vertical", sample_id=nm)
        vals[nm] = r.get("warp_density_per_cm")
    res[cname] = vals
    print(cname, "done")

print("\nimg      tex    truth   " + "  ".join(f"{k:>18}" for k in CONFIGS))
summary = {k: [] for k in CONFIGS}
for nm in pick:
    i = int(nm[1:4])
    tw, te, tex = truth.get(i, (None, None, ""))
    cells = []
    for cname in CONFIGS:
        v = res[cname].get(nm)
        if v and tw:
            e = abs(v - tw) / tw * 100
            summary[cname].append(e)
            cells.append(f"{v:8.2f}({e:5.1f}%)")
        else:
            cells.append(" " * 15)
    print(f"{nm:9}{tex:6}{tw or 0:5}   " + "  ".join(cells))

print("\n=== warp MAPE ===")
for cname in CONFIGS:
    e = summary[cname]
    print(f"  {cname:20} MAPE={np.mean(e):6.2f}%  median={np.median(e):6.2f}%  n={len(e)}")

json.dump(res, open(os.path.join(ROOT, "matrix_tiebreak.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
