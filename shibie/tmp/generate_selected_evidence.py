from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.evidence import generate_evidence
from engine.gate3 import summarize_gate3
from engine.pipeline import decode_image


RESULT_PATH = ROOT / "tmp" / "quality_selected_latest_050.json"
IMAGE_DIR = ROOT / "tmp" / "user_samples"
EVIDENCE_DIR = ROOT / "tmp" / "evidence_050"


def main() -> None:
    payload = json.loads(RESULT_PATH.read_text(encoding="utf-8"))
    for index, item in enumerate(payload.get("samples", []), 1):
        name = item["image"]
        measurement = item["measurement"]
        image_path = IMAGE_DIR / name
        front = decode_image(image_path.read_bytes())
        sample_id = Path(name).stem
        evidence = generate_evidence(
            front,
            measurement,
            EVIDENCE_DIR / sample_id,
            sample_id,
        )
        measurement["evidence"] = evidence
        measurement["gate3"] = summarize_gate3(
            measurement.get("gate2"),
            {"status": measurement.get("status"), "reasons": measurement.get("failure_reasons", [])},
            measurement.get("apparent_width"),
            measurement.get("twill"),
            measurement.get("yarn_advisory"),
            evidence,
        )
        print(f"{index}/{payload.get('count', len(payload.get('samples', [])))} {name}", flush=True)
    RESULT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
