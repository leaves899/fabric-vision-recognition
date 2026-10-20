"""纬向自相关失败排查：density_min_per_cm 决定 max_spacing（自相关搜索上界）。
0.0125 mm/px: min15 -> 53.3px (真实纬向周期约 55px 被挡) ; min8 -> 100px
"""
import sys, os, json, time, dataclasses

ROOT = os.path.dirname(os.path.abspath(__file__))
SHIBIE = os.path.abspath(os.path.join(ROOT, "..", ".."))
sys.path.insert(0, SHIBIE)

from engine.config import EngineConfig
from engine import pipeline
import engine.pipeline as P

front = open(os.path.join(ROOT, "front.png"), "rb").read()
trans = open(os.path.join(ROOT, "transmission.png"), "rb").read()
MM = 0.0125


def run(tag, over):
    cfg = dataclasses.replace(EngineConfig(), **over)
    P.DEFAULT_CONFIG = cfg
    t0 = time.time()
    r = pipeline.run_measurement(front, trans, mm_per_px_x=MM, mm_per_px_y=MM,
                                 warp_axis_hint="vertical", sample_id=tag)
    dt = time.time() - t0
    out = {"tag": tag, "over": over, "sec": round(dt, 1),
           "warp_density": round(r["warp_density_per_cm"], 3) if r.get("warp_density_per_cm") else None,
           "weft_density": round(r["weft_density_per_cm"], 3) if r.get("weft_density_per_cm") else None}
    for ax in ("warp", "weft"):
        dbg = r["density_debug"][ax]
        cl, per, st = dbg["centerline"], dbg["periodicity"], dbg["steerable"]
        out[ax] = {
            "spacing_px": cl["median_center_spacing_px"],
            "lines": cl["valid_centerline_count"],
            "autocorr": per.get("spacing_px"),
            "peak": round(per.get("autocorrelation_peak") or 0.0, 3),
            "sel": st["response_key"],
            "range": [round(v, 1) for v in (dbg.get("ridge", {}).get("min_spacing_px_from_physical_range") or [])] if False else None,
        }
    print(json.dumps(out, ensure_ascii=False))
    with open(os.path.join(ROOT, f"weft_{tag}.json"), "w", encoding="utf-8") as f:
        json.dump(r, f, ensure_ascii=False, indent=1, default=str)
    return out


outs = []
for tag, over in [
    ("min15", {"density_min_per_cm": 15.0}),
    ("min10", {"density_min_per_cm": 10.0}),
    ("min8", {"density_min_per_cm": 8.0}),
]:
    try:
        outs.append(run(tag, over))
    except Exception as e:
        print(tag, "ERROR", repr(e))
json.dump(outs, open(os.path.join(ROOT, "weft_summary.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("done")
