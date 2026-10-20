from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine.pipeline import run_measurement

selected = json.loads((ROOT / "tmp" / "quality_selected_050.json").read_text(encoding="utf-8"))["samples"]
results = []
for index, old in enumerate(selected, 1):
    name = old["image"]
    raw = (ROOT / "tmp" / "user_samples" / name).read_bytes()
    measurement = run_measurement(raw, raw, mm_per_px_x=0.0078125, mm_per_px_y=0.0083333, warp_axis_hint="vertical")
    results.append({"image": name, "fabricnet_texture": old.get("fabricnet_texture"), "reference_warp": old.get("fabricnet_warp"), "reference_weft": old.get("fabricnet_weft"), "measurement": measurement})
    print(f"{index}/50 {name}", flush=True)
(ROOT / "tmp" / "quality_selected_authenticity50.json").write_text(json.dumps({"count": 50, "samples": results}, ensure_ascii=False, indent=2), encoding="utf-8")
