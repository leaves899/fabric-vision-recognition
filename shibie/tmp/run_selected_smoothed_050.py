from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine.pipeline import run_measurement

selected = json.loads((ROOT / "tmp" / "quality_selected_050.json").read_text(encoding="utf-8"))["samples"]
out = []
for i, old in enumerate(selected, 1):
    name = old["image"]
    raw = (ROOT / "tmp" / "user_samples" / name).read_bytes()
    measurement = run_measurement(raw, raw, mm_per_px_x=0.0078125, mm_per_px_y=0.0083333, warp_axis_hint="vertical")
    out.append({"image": name, "fabricnet_texture": old.get("fabricnet_texture"), "measurement": measurement})
    print(f"{i}/50", flush=True)
(ROOT / "tmp" / "quality_selected_smoothed_050.json").write_text(
    json.dumps({"count": 50, "samples": out}, ensure_ascii=False, indent=2), encoding="utf-8"
)
