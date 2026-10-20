from __future__ import annotations

"""Re-run shibie without changing its algorithm or using known weave labels as priors.

Important: one-photo duplicated inputs and unverified mm/px values are ENGINE
DIAGNOSTICS, not calibrated physical-density or width measurements.
"""

import argparse
import csv
import json
import os
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
from engine.pipeline import run_measurement

OUT = REPO / "experiments" / "shibie-review-20261020"
PHOTO_DIR = REPO / "datasets" / "user_contributed" / "2026-10-13-six-fabric-images" / "images"
FABRIC_DIR = HERE / "tmp" / "user_samples"
PAIR_DIR = HERE / "tmp" / "pair_test"

SMOKE_FABRIC = (1, 12, 32, 37, 42, 67, 82, 88, 96, 100, 114, 125)
REVIEW_FABRIC = set(SMOKE_FABRIC)


def cases(scope: str):
    for number in range(1, 7):
        sample = f"U20261013_{number:02d}"
        source = PHOTO_DIR / f"{sample}.jpg"
        yield sample, source, source, "DUPLICATED_SINGLE_REFLECTION", 0.0100, True
    yield "PAIRED_TEST", PAIR_DIR / "front.png", PAIR_DIR / "transmission.png", "PAIRED_UNVERIFIED_SCALE", 0.0125, True
    numbers = range(1, 131) if scope == "full" else SMOKE_FABRIC
    for number in numbers:
        source = FABRIC_DIR / f"W{number:03d}.jpg"
        yield f"W{number:03d}", source, source, "FABRICNET_DUPLICATED_SINGLE", 0.0100, number in REVIEW_FABRIC


def safe_get(obj, *keys):
    for key in keys:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)
    return obj


def run_case(case):
    sample, front, transmission, mode, assumed_scale, make_evidence = case
    rec = {
        "sample": sample, "source": str(front.relative_to(REPO)),
        "test_mode": mode, "mm_per_px_assumed": assumed_scale,
        "calibrated_physical_measurement": False,
        "status": "NOT_RUN", "gate3": None,
    }
    if not front.is_file() or not transmission.is_file():
        rec["status"] = "INPUT_MISSING"
        return rec
    try:
        evidence_dir = OUT / "evidence" / sample if make_evidence else None
        result = run_measurement(
            front.read_bytes(), transmission.read_bytes(),
            mm_per_px_x=assumed_scale, mm_per_px_y=assumed_scale,
            warp_axis_hint="vertical",
            evidence_output_dir=str(evidence_dir) if evidence_dir else None,
            sample_id=sample,
        )
        twill = result.get("twill") or {}
        orient = result.get("orientation") or {}
        warp = safe_get(result, "density_debug", "warp", "centerline") or {}
        weft = safe_get(result, "density_debug", "weft", "centerline") or {}
        rec.update({
            "status": result.get("status"),
            "gate3": safe_get(result, "gate3", "status"),
            "warp_density_computational_only": result.get("warp_density_per_cm"),
            "weft_density_computational_only": result.get("weft_density_per_cm"),
            "direction_a_deg": orient.get("direction_a_deg"),
            "direction_b_deg": orient.get("direction_b_deg"),
            "direction_pair_score": orient.get("pair_quality"),
            "warp_centerlines": warp.get("valid_centerline_count"),
            "weft_centerlines": weft.get("valid_centerline_count"),
            "warp_spacing_px": warp.get("median_center_spacing_px"),
            "weft_spacing_px": weft.get("median_center_spacing_px"),
            "twill_direction": twill.get("direction"),
            "twill_direction_status": twill.get("direction_status"),
            "weave_candidate": twill.get("weave_candidate"),
            "weave_status": twill.get("weave_status"),
            "failure_reasons": "|".join(result.get("failure_reasons") or []),
            "gate3_warnings": "|".join(safe_get(result, "gate3", "warnings") or []),
            "evidence_dir": str(evidence_dir.relative_to(OUT)) if evidence_dir and evidence_dir.is_dir() else None,
        })
        # Keep compact evidence/provenance and quantitative outputs, never claim true mm-based accuracy.
        (OUT / "json").mkdir(parents=True, exist_ok=True)
        details = {
            "sample": sample, "test_mode": mode, "mm_per_px_is_assumed": True,
            "calibrated_physical_measurement": False,
            "orientation": orient,
            "density_debug": result.get("density_debug"),
            "twill": twill,
            "gate3": result.get("gate3"),
            "centerline_evidence": result.get("centerline_evidence"),
            "evidence": result.get("evidence"),
        }
        (OUT / "json" / f"{sample}.json").write_text(
            json.dumps(details, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )
    except Exception as error:
        rec.update({"status": "EXCEPTION", "failure_reasons": f"{type(error).__name__}: {error}"})
    return rec


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", choices=("smoke", "full"), default="smoke")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    data = []
    for case in cases(args.scope):
        record = run_case(case)
        data.append(record)
        print(json.dumps({k: record.get(k) for k in ("sample", "test_mode", "status", "gate3", "failure_reasons")}, ensure_ascii=False), flush=True)
    fields = list(dict.fromkeys(k for row in data for k in row))
    with (OUT / "summary.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(data)
    (OUT / "summary.json").write_text(
        json.dumps({"scope": args.scope, "git_sha": os.environ.get("GITHUB_SHA"), "cases": data}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    counts = dict(Counter(str(item["status"]) for item in data))
    gate = dict(Counter(str(item["gate3"]) for item in data))
    lines = [
        "# shibie V0.6.3 冻结参数回归（自动执行报告）",
        "",
        f"- Scope: {args.scope}; Git commit: {os.environ.get('GITHUB_SHA', 'local')}",
        f"- 样本数：{len(data)}；运行状态分布：{counts}；Gate 3：{gate}",
        "- 真实手机单图及 FabricNET 均采用同图重复输入，仅用于算法诊断，不是反射/透射双图。",
        "- mm/px 未经物理标定；本次所有数字密度和宽度均不可用于绝对精度验收。",
        "- 已知织物组织标签没有输入推理函数；PASS 只表示内部质量门限，不是 Ground Truth 正确率。",
        "- 来源：codex/photo1.0 的 shibie 原版算法，未修改参数。",
        "- 审核方式：查看 summary.csv、json/ 和 GitHub Actions artifact 内 evidence/ 图。",
        "",
        "| 样本 | 输入类型 | 算法状态 | Gate3 | A/B方向 | 组织候选 |",
        "|---|---|---|---|---|---|",
    ]
    for row in data:
        a, b = row.get("direction_a_deg"), row.get("direction_b_deg")
        dire = f"{a}/{b}" if a is not None and b is not None else "-"
        lines.append(f"| {row['sample']} | {row['test_mode']} | {row['status']} | {row.get('gate3') or '-'} | {dire} | {row.get('weave_candidate') or '-'} |")
    (OUT / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
