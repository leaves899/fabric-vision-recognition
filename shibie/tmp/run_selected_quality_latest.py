from __future__ import annotations
import json
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine.pipeline import run_measurement

parser = argparse.ArgumentParser()
parser.add_argument("--output", default="tmp/quality_selected_latest_050.json")
args = parser.parse_args()

selected = json.loads(Path("tmp/quality_selected_050.json").read_text(encoding="utf-8"))["samples"]
results = []
for index, old in enumerate(selected, 1):
    name = old["image"]
    raw = (Path("tmp/user_samples") / name).read_bytes()
    result = run_measurement(raw, raw, mm_per_px_x=0.0078125, mm_per_px_y=0.0083333, warp_axis_hint="vertical")
    twill = result.get("twill", {})
    width = result.get("apparent_width") or {}
    yarn = result.get("yarn_advisory") or {}
    results.append({"image": name, "fabricnet_texture": old.get("fabricnet_texture"), "measurement": result})
    print(f"{index}/50", flush=True)
Path(args.output).write_text(json.dumps({"count": 50, "samples": results}, ensure_ascii=False, indent=2), encoding="utf-8")
