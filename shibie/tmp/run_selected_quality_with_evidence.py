from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.pipeline import run_measurement


ROOT = Path(__file__).resolve().parent.parent
selected = json.loads((ROOT / "tmp" / "quality_selected_050.json").read_text(encoding="utf-8"))["samples"]
results = []
for index, old in enumerate(selected, 1):
    name = old["image"]
    raw = (ROOT / "tmp" / "user_samples" / name).read_bytes()
    result = run_measurement(
        raw, raw, mm_per_px_x=0.0078125, mm_per_px_y=0.0083333,
        warp_axis_hint="vertical", evidence_output_dir=ROOT / "tmp" / "evidence_050_latest",
        sample_id=Path(name).stem,
    )
    results.append({"image": name, "fabricnet_texture": old.get("fabricnet_texture"), "measurement": result})
    print(f"{index}/50", flush=True)
(ROOT / "tmp" / "quality_selected_latest_evidence_050.json").write_text(
    json.dumps({"count": 50, "samples": results}, ensure_ascii=False, indent=2), encoding="utf-8"
)
