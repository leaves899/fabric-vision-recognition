"""回归：periodicity tiebreak 开关前后，对 FabricNET 抽样样本的密度影响。"""
import sys, os, json, time, dataclasses
import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
SHIBIE = os.path.abspath(os.path.join(ROOT, "..", ".."))
sys.path.insert(0, SHIBIE)

from engine.config import EngineConfig
from engine import pipeline
import engine.pipeline as P

SAMPLES_DIR = os.path.join(SHIBIE, "tmp", "fabricnet")
XLSX = os.path.join(SAMPLES_DIR, "FabricNet_parameters.xlsx")
MM_X, MM_Y = 0.0078125, 0.0083333


def load_truth():
    import openpyxl
    wb = openpyxl.load_workbook(XLSX, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    head = [str(c).strip() if c is not None else "" for c in rows[0]]
    iw = head.index("Warp") if "Warp" in head else 2
    ie = head.index("Weft") if "Weft" in head else 3
    ii = head.index("Image id") if "Image id" in head else 0
    out = {}
    for r in rows[1:]:
        if r[ii] is None:
            continue
        key = str(r[ii]).strip()
        out[key] = (float(r[iw]) if r[iw] is not None else None,
                    float(r[ie]) if r[ie] is not None else None)
    return out


def run_one(tag, fb, tb, tiebreak):
    cfg = dataclasses.replace(EngineConfig(), steerable_periodicity_tiebreak=tiebreak)
    P.DEFAULT_CONFIG = cfg
    t0 = time.time()
    r = pipeline.run_measurement(fb, tb, mm_per_px_x=MM_X, mm_per_px_y=MM_Y,
                                 warp_axis_hint="vertical", sample_id=tag)
    dt = time.time() - t0
    dbg = r.get("density_debug", {})
    return {
        "warp": r.get("warp_density_per_cm"),
        "weft": r.get("weft_density_per_cm"),
        "status": r.get("status"),
        "warp_sel": (dbg.get("warp", {}).get("steerable") or {}).get("response_key"),
        "weft_sel": (dbg.get("weft", {}).get("steerable") or {}).get("response_key"),
        "sec": round(dt, 1),
    }


truth = load_truth()
names = [f"W{i:03d}.jpg" for i in range(1, 131)]
# 均匀抽样 20 张，覆盖三类组织
pick = names[::7][:20]
print("samples:", pick)

rows = []
for nm in pick:
    p = os.path.join(SAMPLES_DIR, nm)
    if not os.path.exists(p):
        print("MISSING", nm)
        continue
    data = open(p, "rb").read()
    a = run_one(nm, data, data, False)
    b = run_one(nm, data, data, True)
    tw, te = truth.get(nm.replace(".jpg", ""), (None, None))
    rec = {"img": nm, "truth_warp": tw, "truth_weft": te,
           "off_warp": a["warp"], "on_warp": b["warp"],
           "off_weft": a["weft"], "on_weft": b["weft"],
           "sel_off": a["warp_sel"], "sel_on": b["warp_sel"],
           "status_off": a["status"], "status_on": b["status"]}
    rows.append(rec)
    print(json.dumps({k: (round(v, 3) if isinstance(v, float) else v) for k, v in rec.items()}, ensure_ascii=False))

json.dump(rows, open(os.path.join(ROOT, "regression_tiebreak.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def mape(key):
    errs = []
    for r in rows:
        t = r["truth_warp"]
        v = r.get(key)
        if t and v and t > 0:
            errs.append(abs(v - t) / t * 100)
    return (np.mean(errs) if errs else None, len(errs))


print("\n=== warp MAPE ===")
for k in ("off_warp", "on_warp"):
    m, n = mape(k)
    print(f"  {k}: {m:.2f}%  (n={n})" if m is not None else f"  {k}: n/a")

changed = [r for r in rows if r["off_warp"] and r["on_warp"] and abs(r["on_warp"] - r["off_warp"]) / max(r["off_warp"], 1e-6) > 0.02]
print(f"\nchanged >2%: {len(changed)}/{len(rows)}")
