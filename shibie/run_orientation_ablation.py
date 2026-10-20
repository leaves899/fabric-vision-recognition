from __future__ import annotations

"""Isolated orientation-parameter ablation for shibie.

Human-marked physical-yarn directions are used only AFTER inference for evaluation.
This experiment cannot establish yarn-centerline identity or absolute density.
"""

import csv
import dataclasses
import json
import math
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from engine.config import EngineConfig
from engine import pipeline

OUT = ROOT / "experiments" / "shibie-orientation-ablation-20261020"
DATA = ROOT / "datasets" / "user_contributed" / "2026-10-13-six-fabric-images" / "images"
ANNOT = ROOT / "datasets" / "annotations" / "drafts"
DEV = ("U20261013_01", "U20261013_03", "U20261013_05")
HOLDOUT = ("U20261013_02", "U20261013_06")
CANDIDATES = {
    "baseline": {},
    "tensor_sigma_1p2": {"tensor_sigma": 1.2},
    "tensor_sigma_3p2": {"tensor_sigma": 3.2},
    "tensor_q_0p40": {"tensor_energy_quantile": 0.40},
}


def angle(points):
    dx = float(points[1][0]) - float(points[0][0])
    dy = float(points[1][1]) - float(points[0][1])
    return math.degrees(math.atan2(dy, dx)) % 180.0


def median(vals):
    vals = sorted(vals)
    n = len(vals)
    return vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2


def reference(sample):
    data = json.loads((ANNOT / (sample + ".json")).read_text(encoding="utf-8"))
    if not data.get("reference_confirmed") or data.get("annotation_target") != "PHYSICAL_YARN_REFERENCE":
        raise RuntimeError(f"{sample}: MISSING_OPERATOR_DIRECTION_REFERENCE")
    s = data["segments"]
    f1 = median([angle(s[k]) for k in ("reference", "check_same", "holdout_same") if k in s])
    f2 = median([angle(s[k]) for k in ("check_cross", "check_cross_second") if k in s])
    return (f1, f2)


def direction_error(estimated, truth):
    if estimated is None:
        return (90., 90.)
    a, b = estimated
    def diff(x, y):
        return abs((x - y + 90.0) % 180.0 - 90.0)
    direct = (diff(a, truth[0]), diff(b, truth[1]))
    swapped = (diff(a, truth[1]), diff(b, truth[0]))
    return direct if sum(direct) <= sum(swapped) else swapped


def run_one(sample, variant, cfg):
    pipeline.DEFAULT_CONFIG = cfg
    raw = (DATA / (sample + ".jpg")).read_bytes()
    t0 = time.perf_counter()
    measured = pipeline.run_measurement(
        raw, raw, mm_per_px_x=0.01, mm_per_px_y=0.01, warp_axis_hint="vertical"
    )
    duration = time.perf_counter() - t0
    orient = measured.get("orientation") or {}
    a, b = orient.get("direction_a_deg"), orient.get("direction_b_deg")
    candidate = (float(a), float(b)) if a is not None and b is not None else None
    errors = direction_error(candidate, reference(sample))
    return {
        "sample": sample, "split": "dev" if sample in DEV else "holdout",
        "variant": variant, "status": measured.get("status"),
        "gate3": (measured.get("gate3") or {}).get("status"),
        "angle_a": a, "angle_b": b,
        "axis_error_1_deg": round(errors[0], 4),
        "axis_error_2_deg": round(errors[1], 4),
        "mean_angle_error_deg": round(sum(errors) / 2, 4),
        "pair_quality": orient.get("pair_quality"),
        "seconds": round(duration, 2),
    }


def average(rows):
    return sum(float(row["mean_angle_error_deg"]) for row in rows) / len(rows)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    # Select solely on DEV; never look at holdout scores to choose a variant.
    for variant, overrides in CANDIDATES.items():
        cfg = dataclasses.replace(EngineConfig(), **overrides)
        for sample in DEV:
            result = run_one(sample, variant, cfg)
            rows.append(result)
            print(json.dumps(result, ensure_ascii=False), flush=True)

    dev_means = {
        variant: average([r for r in rows if r["variant"] == variant and r["sample"] in DEV])
        for variant in CANDIDATES
    }
    selected = min(CANDIDATES, key=lambda variant: (dev_means[variant], list(CANDIDATES).index(variant)))
    # Holdout evaluation of BASELINE and SELECTED only (no holdout selection).
    for variant in dict.fromkeys(("baseline", selected)):
        cfg = dataclasses.replace(EngineConfig(), **CANDIDATES[variant])
        for sample in HOLDOUT:
            result = run_one(sample, variant, cfg)
            rows.append(result)
            print(json.dumps(result, ensure_ascii=False), flush=True)

    fields = list(rows[0].keys())
    with (OUT / "direction_ablation.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    holdout_means = {
        v: average([r for r in rows if r["variant"] == v and r["sample"] in HOLDOUT])
        for v in dict.fromkeys(("baseline", selected))
    }
    improved_holdout = selected == "baseline" or holdout_means[selected] < holdout_means["baseline"]
    data = {
        "split": {"development": DEV, "holdout": HOLDOUT},
        "candidates": CANDIDATES,
        "selection_only_uses_dev": True,
        "baseline_and_selected_holdout_evaluated_after_selection": True,
        "selected_by_dev_error": selected,
        "dev_average_errors_deg": dev_means,
        "holdout_average_errors_deg": holdout_means,
        "holdout_improvement": improved_holdout,
        "promotion_recommendation": "ONLY_RESEARCH_CANDIDATE__NEEDS_REAL_YARN_VALIDATION",
        "rows": rows,
    }
    (OUT / "direction_ablation.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# shibie 方向参数小范围消融试验",
        "",
        "本轮采用原版 pipeline：仅分别替换结构张量的 sigma 或能量分位数。未更改主分支、未使用组织真值输入推理。",
        "同图重复作为双输入，mm/px 为未核实的诊断占位值；结果仅用于**方向误差**对照。",
        "",
        f"开发集：{', '.join(DEV)}；独立留出集：{', '.join(HOLDOUT)}。",
        "",
        "| 参数组合 | 开发集平均轴向误差(°) |",
        "|---|---:|",
        *[f"| {k} | {v:.3f} |" for k, v in dev_means.items()],
        "",
        f"**仅根据开发集选出的候选**：{selected}。",
        f"留出集 baseline：{holdout_means['baseline']:.3f}°；候选：{holdout_means[selected]:.3f}°。",
        f"留出集平均角度误差是否降低：{'是' if improved_holdout else '否'}。",
        "",
        "这不是实际密度/完整中心线识别准确率，不能因为几个样本方向角改善就直接推广。",
        "单次试验样本量小；运行重复性、90°/180°旋转、逐根纱线真值、R/T双图和真实5cm标尺仍待验证。",
    ]
    (OUT / "direction_ablation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    pipeline.DEFAULT_CONFIG = EngineConfig()


if __name__ == "__main__":
    main()
