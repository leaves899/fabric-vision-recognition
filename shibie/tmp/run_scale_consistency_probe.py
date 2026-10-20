from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.pipeline import run_measurement


SAMPLES = ("W096.jpg", "W067.jpg", "W073.jpg", "W088.jpg", "W012.jpg", "W100.jpg")
MM_X = 0.0078125
MM_Y = 0.0083333


def direction_result(measurement: dict, direction: str) -> dict:
    item = measurement["density_debug"][direction]
    return {
        "density_per_cm": item["density"]["density_per_cm"],
        "confidence_status": item["confidence"]["status"],
        "confidence_reasons": item["confidence"]["reasons"],
        "selected_response": item["steerable"]["response_key"],
        "scale_consistency": item["steerable"]["scale_consistency"],
    }


def main() -> None:
    rows = []
    for index, name in enumerate(SAMPLES, 1):
        raw = (ROOT / "tmp" / "user_samples" / name).read_bytes()
        measurement = run_measurement(raw, raw, mm_per_px_x=MM_X, mm_per_px_y=MM_Y, warp_axis_hint="vertical")
        rows.append({
            "image": name,
            "overall_status": measurement["status"],
            "warp": direction_result(measurement, "warp"),
            "weft": direction_result(measurement, "weft"),
        })
        print(f"{index}/{len(SAMPLES)} {name}", flush=True)
    output = ROOT / "tmp" / "steerable_scale_consistency_probe.json"
    output.write_text(json.dumps({"samples": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
