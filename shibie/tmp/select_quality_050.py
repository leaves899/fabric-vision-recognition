from __future__ import annotations
import json
from pathlib import Path

data = json.loads(Path("tmp/full_quality_batch_001_130.json").read_text(encoding="utf-8"))["samples"]

def score(item: dict) -> tuple:
    warp, weft = item["warp_width"], item["weft_width"]
    both_pass = int(warp.get("status") == "PASS" and weft.get("status") == "PASS")
    both_usable = int(warp.get("status") in {"PASS", "LOW_CONFIDENCE"} and weft.get("status") in {"PASS", "LOW_CONFIDENCE"})
    p10_ok = int((warp.get("p10_mm") or 0) > 0 and (weft.get("p10_mm") or 0) > 0)
    valid = min(warp.get("valid_sample_count", 0), weft.get("valid_sample_count", 0))
    status = {"PASS": 2, "LOW_CONFIDENCE": 1, "FAIL": 0}.get(item.get("width_status"), 0)
    return (both_pass, both_usable, p10_ok, status, valid)

selected = sorted(data, key=score, reverse=True)[:50]
output = {
    "count": 50,
    "selection": "full 130-sample rerun ranked by warp/weft apparent-width quality",
    "samples": selected,
}
Path("tmp/quality_selected_050.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
print("selected", len(selected))
from collections import Counter
for key in ("width_status", "direction_status", "angle_status", "weave_status", "fabricnet_texture", "weave_candidate"):
    print(key, Counter(item.get(key) for item in selected))
print("width axes", Counter((item["warp_width"].get("status"), item["weft_width"].get("status")) for item in selected))
