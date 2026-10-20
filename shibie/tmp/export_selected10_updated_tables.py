from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAMES = ["W088.jpg", "W004.jpg", "W063.jpg", "W012.jpg", "W014.jpg", "W001.jpg", "W003.jpg", "W100.jpg", "W096.jpg", "W050.jpg"]
reference = {
    1: (32, 30, "twill"), 3: (32, 30, "twill"), 4: (32, 30, "twill"),
    12: (38, 33, "plain"), 14: (38, 33, "plain"), 50: (62, 30, "plain"),
    63: (26, 18, "plain"), 88: (30, 45, "satin"), 96: (30, 15, "plain"),
    100: (30, 50, "satin"),
}

payload = json.loads((ROOT / "tmp" / "quality_selected_conservative_050.json").read_text(encoding="utf-8"))
items = {item["image"]: item["measurement"] for item in payload["samples"]}

density_fields = ["sample", "reference_warp", "algorithm_warp", "warp_error", "reference_weft", "algorithm_weft", "weft_error", "warp_weft_ratio", "main_status", "gate3_status"]
yarn_fields = ["sample", "warp_range_ne", "warp_range_tex", "weft_range_ne", "weft_range_tex", "status", "warp_confidence", "weft_confidence", "reference_only", "basis"]

with (ROOT / "tmp" / "report_selected10_density_updated.csv").open("w", newline="", encoding="utf-8-sig") as handle:
    writer = csv.DictWriter(handle, fieldnames=density_fields)
    writer.writeheader()
    for name in NAMES:
        m = items[name]
        image_id = int(Path(name).stem[1:])
        ref_warp, ref_weft, _ = reference[image_id]
        algorithm_warp = float(m["warp_density_per_cm"])
        algorithm_weft = float(m["weft_density_per_cm"])
        writer.writerow({
            "sample": name, "reference_warp": ref_warp, "algorithm_warp": round(algorithm_warp, 3),
            "warp_error": round(algorithm_warp - ref_warp, 3), "reference_weft": ref_weft,
            "algorithm_weft": round(algorithm_weft, 3), "weft_error": round(algorithm_weft - ref_weft, 3),
            "warp_weft_ratio": round(float(m["warp_weft_ratio"]), 6), "main_status": m.get("status"),
            "gate3_status": m.get("gate3", {}).get("status"),
        })

with (ROOT / "tmp" / "report_selected10_yarn_updated.csv").open("w", newline="", encoding="utf-8-sig") as handle:
    writer = csv.DictWriter(handle, fieldnames=yarn_fields)
    writer.writeheader()
    for name in NAMES:
        m = items[name]
        y = m.get("yarn_advisory") or {}
        warp, weft = y.get("warp") or {}, y.get("weft") or {}
        writer.writerow({
            "sample": name, "warp_range_ne": warp.get("range_ne"), "warp_range_tex": warp.get("range_tex"),
            "weft_range_ne": weft.get("range_ne"), "weft_range_tex": weft.get("range_tex"),
            "status": y.get("status"), "warp_confidence": warp.get("confidence"),
            "weft_confidence": weft.get("confidence"), "reference_only": y.get("reference_only"),
            "basis": y.get("method"),
        })

print(ROOT / "tmp" / "report_selected10_density_updated.csv")
print(ROOT / "tmp" / "report_selected10_yarn_updated.csv")
