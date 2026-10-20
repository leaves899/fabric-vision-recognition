"""反事实：只改 steerable sigma 组，看密度能否收敛到自相关周期(28px -> 28.57根/cm)。"""
import sys, os, json, time
import numpy as np
import cv2

ROOT = os.path.dirname(os.path.abspath(__file__))
SHIBIE = os.path.abspath(os.path.join(ROOT, "..", ".."))
sys.path.insert(0, SHIBIE)

from engine.config import EngineConfig, DEFAULT_CONFIG
from engine import pipeline
import engine.pipeline as P

front = open(os.path.join(ROOT, "front.png"), "rb").read()
trans = open(os.path.join(ROOT, "transmission.png"), "rb").read()

MM = 0.0125
REF_PERIOD_PX = 28.0
REF_DENSITY = 10.0 / (REF_PERIOD_PX * MM)


def run(tag, sigmas, tensor_sigma, extra=None):
    import dataclasses
    over = {"steerable_sigmas": tuple(sigmas), "tensor_sigma": float(tensor_sigma)}
    if extra:
        over.update(extra)
    cfg = dataclasses.replace(EngineConfig(), **over)
    P.DEFAULT_CONFIG = cfg          # pipeline 内部按模块全局名查找，替换即可生效
    t0 = time.time()
    r = pipeline.run_measurement(
        front, trans, mm_per_px_x=MM, mm_per_px_y=MM,
        warp_axis_hint="vertical", sample_id=tag,
    )
    dt = time.time() - t0
    dw = r.get("warp_density_per_cm")
    dp = r.get("weft_density_per_cm")
    cl = r.get("density_debug", {}).get("warp", {}).get("centerline", {})
    per = r.get("density_debug", {}).get("warp", {}).get("periodicity", {})
    st = r.get("density_debug", {}).get("warp", {}).get("steerable", {})
    out = {
        "tag": tag,
        "sigmas": list(sigmas),
        "tensor_sigma": tensor_sigma,
        "status": r.get("status"),
        "warp_density": None if dw is None else round(float(dw), 3),
        "warp_err_pct": None if dw is None else round(abs(dw - REF_DENSITY) / REF_DENSITY * 100, 1),
        "weft_density": None if dp is None else round(float(dp), 3),
        "warp_spacing_px": cl.get("median_center_spacing_px"),
        "valid_centerlines": cl.get("valid_centerline_count"),
        "spacing_cv": cl.get("spacing_cv"),
        "coverage": cl.get("mean_coverage"),
        "autocorr_px": per.get("spacing_px"),
        "selected": st.get("response_key"),
        "reasons": r.get("density_debug", {}).get("warp", {}).get("confidence", {}).get("reasons"),
        "sec": round(dt, 1),
    }
    print(json.dumps(out, ensure_ascii=False))
    return out, r


print(f"REF density from autocorr 28px = {REF_DENSITY:.3f} 根/cm\n")
results = []
for tag, sig, ts in [
    ("base_x1", (2.3, 3.6, 4.3, 5.0, 6.0), 2.0),
    ("sig_x2", (4.6, 7.2, 8.6, 10.0, 12.0), 4.0),
    ("sig_x3", (6.9, 10.8, 12.9, 15.0, 18.0), 6.0),
    ("sig_x4", (9.2, 14.4, 17.2, 20.0, 24.0), 8.0),
]:
    try:
        o, r = run(tag, sig, ts)
        results.append(o)
        with open(os.path.join(ROOT, f"scale2_{tag}.json"), "w", encoding="utf-8") as f:
            json.dump(r, f, ensure_ascii=False, indent=1, default=str)
    except Exception as e:
        print(tag, "ERROR", repr(e))

with open(os.path.join(ROOT, "scale2_summary.json"), "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=1)
print("\nsaved scale2_summary.json")
