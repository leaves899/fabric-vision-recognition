"""双图（反射/透射）全链路测试：rectified_1(front) + rectified_2(transmission)。"""
import sys, os, json, io
import numpy as np
import cv2

ROOT = os.path.dirname(os.path.abspath(__file__))
SHIBIE = os.path.abspath(os.path.join(ROOT, "..", ".."))
sys.path.insert(0, SHIBIE)

from engine.config import EngineConfig
from engine import gate2, width, pipeline


def imread_u(path, flags=cv2.IMREAD_COLOR):
    return cv2.imdecode(np.fromfile(path, dtype=np.uint8), flags)


def imwrite_u(path, img):
    ext = os.path.splitext(path)[1]
    ok, buf = cv2.imencode(ext, img)
    if ok:
        buf.tofile(path)
    return ok


def brief(d, keys):
    return {k: d.get(k) for k in keys if k in d}


front_path = os.path.join(ROOT, "front.png")
trans_path = os.path.join(ROOT, "transmission.png")
front = imread_u(front_path)
trans = imread_u(trans_path)
print("front", front.shape, "| trans", trans.shape)

fb = open(front_path, "rb").read()
tb = open(trans_path, "rb").read()

cfg = EngineConfig()
g = gate2.gate2(front, trans, 0.0125, 0.0125, cfg)
print("\n=== GATE2 ===", g["status"], g["reasons"])
print(json.dumps(g["metrics"], ensure_ascii=False, indent=1)[:1200])

reg = width.estimate_reflection_registration(
    cv2.cvtColor(front, cv2.COLOR_BGR2GRAY),
    cv2.cvtColor(trans, cv2.COLOR_BGR2GRAY),
    cfg,
)
print("\n=== REGISTRATION ===", json.dumps({k: v for k, v in reg.items() if k != "matrix"}, ensure_ascii=False, default=str))
if isinstance(reg.get("matrix"), np.ndarray):
    print("matrix=", reg["matrix"].round(3).tolist())

print("\n=== FULL PIPELINE (mm/px 0.0125) ===")
res = pipeline.run_measurement(
    fb, tb,
    mm_per_px_x=0.0125, mm_per_px_y=0.0125,
    warp_axis_hint="vertical",
    evidence_output_dir=os.path.join(ROOT, "evidence"),
    sample_id="pair01",
)
print("overall:", res.get("status"), res.get("gate3", {}).get("status"))
print("overall reasons:", json.dumps(res.get("overall", {}).get("reasons", res.get("reasons")), ensure_ascii=False))
print("density:", json.dumps(brief(res.get("density", {}), [
    "status", "warp_density_per_cm", "weft_density_per_cm", "warp_weft_ratio",
    "warp_center_spacing_px", "weft_center_spacing_px",
    "warp_count_density", "weft_count_density", "reasons",
]), ensure_ascii=False, indent=1))
print("width:", json.dumps(brief(res.get("width", {}), ["status", "reasons", "warp", "weft"]), ensure_ascii=False, indent=1)[:1600])
print("twill:", json.dumps(brief(res.get("twill", {}), [
    "status", "direction", "direction_status", "angle_deg", "angle_status",
    "dominance", "band_direction_support", "direction_support", "angle_spread_deg",
    "scale_consensus", "reasons",
]), ensure_ascii=False, indent=1))
print("weave:", json.dumps(brief(res.get("weave", {}) if isinstance(res.get("weave"), dict) else {}, [
    "status", "candidate", "best", "scores", "reasons",
]), ensure_ascii=False, indent=1)[:900])
print("yarn_advisory:", json.dumps(res.get("yarn_advisory", {}), ensure_ascii=False, default=str)[:600])
print("gate3:", json.dumps(res.get("gate3", {}), ensure_ascii=False, default=str)[:900])

with open(os.path.join(ROOT, "result_pair01.json"), "w", encoding="utf-8") as f:
    json.dump(res, f, ensure_ascii=False, indent=1, default=str)
print("\nsaved result_pair01.json")
