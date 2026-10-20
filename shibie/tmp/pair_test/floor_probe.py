"""验证：density_min_per_cm 决定 ridge 的 min_spacing_px，可能强行合并 28px 的真实间距。
0.0125 mm/px 下：
  density_min_per_cm=15 -> min_spacing = 53.3px  (28px 真实间距被挡)
  density_min_per_cm=30 -> 26.7px
  density_min_per_cm=40 -> 20.0px
"""
import sys, os, json, time
import numpy as np
import dataclasses

ROOT = os.path.dirname(os.path.abspath(__file__))
SHIBIE = os.path.abspath(os.path.join(ROOT, "..", ".."))
sys.path.insert(0, SHIBIE)

from engine.config import EngineConfig
from engine import pipeline
import engine.pipeline as P

front = open(os.path.join(ROOT, "front.png"), "rb").read()
trans = open(os.path.join(ROOT, "transmission.png"), "rb").read()
MM = 0.0125
REF = 10.0 / (28.0 * MM)


def run(tag, over):
    cfg = dataclasses.replace(EngineConfig(), **over)
    P.DEFAULT_CONFIG = cfg
    t0 = time.time()
    r = pipeline.run_measurement(front, trans, mm_per_px_x=MM, mm_per_px_y=MM,
                                 warp_axis_hint="vertical", sample_id=tag)
    dt = time.time() - t0
    dbg = r.get("density_debug", {}).get("warp", {})
    cl = dbg.get("centerline", {})
    out = {
        "tag": tag, "over": over,
        "status": r.get("status"),
        "warp_density": None if r.get("warp_density_per_cm") is None else round(r["warp_density_per_cm"], 3),
        "weft_density": None if r.get("weft_density_per_cm") is None else round(r["weft_density_per_cm"], 3),
        "warp_err_vs_28px_pct": None if r.get("warp_density_per_cm") is None else round(abs(r["warp_density_per_cm"] - REF) / REF * 100, 1),
        "spacing_px": cl.get("median_center_spacing_px"),
        "lines": cl.get("valid_centerline_count"),
        "cv": cl.get("spacing_cv"),
        "coverage": cl.get("mean_coverage"),
        "selected": dbg.get("steerable", {}).get("response_key"),
        "width_status": (r.get("apparent_width") or {}).get("status"),
        "warp_p50_mm": ((r.get("apparent_width") or {}).get("warp") or {}).get("p50_mm"),
        "sec": round(dt, 1),
    }
    print(json.dumps(out, ensure_ascii=False))
    with open(os.path.join(ROOT, f"floor_{tag}.json"), "w", encoding="utf-8") as f:
        json.dump(r, f, ensure_ascii=False, indent=1, default=str)
    return out


print(f"REF = {REF:.2f} 根/cm (28px @ 0.0125mm/px)\n")
outs = []
for tag, over in [
    ("min15_base", {"density_min_per_cm": 15.0}),
    ("min30", {"density_min_per_cm": 30.0}),
    ("min40", {"density_min_per_cm": 40.0}),
    ("min40_max200", {"density_min_per_cm": 40.0, "density_max_per_cm": 200.0}),
]:
    try:
        outs.append(run(tag, over))
    except Exception as e:
        print(tag, "ERROR", repr(e))

json.dump(outs, open(os.path.join(ROOT, "floor_summary.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("done")
