from __future__ import annotations

import json
import argparse
from collections import Counter
from functools import reduce
from pathlib import Path


ROOT = Path(__file__).resolve().parent
def read_samples(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["samples"]


def get(item: dict, *keys: str):
    value = item.get("measurement", item)
    return reduce(lambda current, key: current.get(key) if isinstance(current, dict) else None, keys, value)


def counts(samples: list[dict], *keys: str) -> dict[str, int]:
    return dict(Counter(str(get(item, *keys)) for item in samples))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, default=ROOT / "quality_selected_baseline_050.json")
    parser.add_argument("--optimized", type=Path, default=ROOT / "quality_selected_latest_050.json")
    parser.add_argument("--output", type=Path, default=ROOT / "quality_selected_comparison_050.json")
    args = parser.parse_args()
    baseline = read_samples(args.baseline)
    optimized = read_samples(args.optimized)
    if [item["image"] for item in baseline] != [item["image"] for item in optimized]:
        raise ValueError("SAMPLE_ORDER_MISMATCH")

    metrics = {
        "main_status": ("status",),
        "gate3_status": ("gate3", "status"),
        "width_status": ("apparent_width", "status"),
        "warp_width_status": ("apparent_width", "warp", "status"),
        "weft_width_status": ("apparent_width", "weft", "status"),
        "twill_direction_status": ("twill", "direction_status"),
        "twill_angle_status": ("twill", "angle_status"),
        "weave_status": ("twill", "weave_status"),
    }
    summary = {}
    for name, keys in metrics.items():
        before, after = counts(baseline, *keys), counts(optimized, *keys)
        summary[name] = {"baseline": before, "optimized": after, "changed": before != after}

    warning_before = Counter(
        warning for item in baseline for warning in get(item, "gate3", "warnings") or []
    )
    warning_after = Counter(
        warning for item in optimized for warning in get(item, "gate3", "warnings") or []
    )
    changed_samples = []
    for before, after in zip(baseline, optimized):
        before_reasons = get(before, "twill", "weave_reasons") or []
        after_reasons = get(after, "twill", "weave_reasons") or []
        if before_reasons != after_reasons:
            changed_samples.append({
                "image": before["image"],
                "baseline_weave_reasons": before_reasons,
                "optimized_weave_reasons": after_reasons,
            })

    payload = {
        "sample_count": len(optimized),
        "baseline": str(args.baseline),
        "optimized": str(args.optimized),
        "metrics": summary,
        "gate3_warning_frequency": {
            "baseline": dict(warning_before),
            "optimized": dict(warning_after),
        },
        "changed_weave_warning_samples": changed_samples,
    }
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(args.output)
    print("changed_weave_warning_samples", len(changed_samples))


if __name__ == "__main__":
    main()
