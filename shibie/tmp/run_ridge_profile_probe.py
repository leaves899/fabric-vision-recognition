from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.pipeline import run_measurement


NAMES = ["W066.jpg", "W114.jpg", "W042.jpg", "W063.jpg", "W046.jpg", "W073.jpg", "W088.jpg"]


def main() -> None:
    rows = []
    for name in NAMES:
        raw = (ROOT / "tmp" / "user_samples" / name).read_bytes()
        result = run_measurement(raw, raw, mm_per_px_x=0.0078125, mm_per_px_y=0.0083333)
        debug = result["density_debug"]
        rows.append({
            "image": name,
            "warp_density_per_cm": result["warp_density_per_cm"],
            "weft_density_per_cm": result["weft_density_per_cm"],
            "status": result["status"],
            "warp_profile_rejected": debug["warp"]["ridge"]["track_profile_rejected_count"],
            "weft_profile_rejected": debug["weft"]["ridge"]["track_profile_rejected_count"],
        })
        print(name, flush=True)
    out = ROOT / "tmp" / "ridge_profile_probe.json"
    out.write_text(json.dumps({"samples": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
