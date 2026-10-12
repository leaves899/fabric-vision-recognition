"""Batch comparison of saved V5 candidates against independently confirmed GT.

Does not call /api/analyze; human reference points must not be invented.
Does not require a transmission image or camera calibration profile.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

from benchmark.adapters.v5 import load_v5
from benchmark.dataset import (
    GROUND_TRUTH_FIELDS, KEY, MANIFEST_FIELDS, load_csv, resolve_local, validate,
)
from benchmark.metrics import axis_error_deg, density_error_pct, summarize

METRICS = {
    "warp_axis_deg": ("warp_axis_error_deg", axis_error_deg),
    "weft_axis_deg": ("weft_axis_error_deg", axis_error_deg),
    "warp_density_per_cm": ("warp_density_error_pct", density_error_pct),
    "weft_density_per_cm": ("weft_density_error_pct", density_error_pct),
}
RESULT_FIELDS = (
    "fabric_id", "position_id", "face", "split", "status", "failure_reason",
    "gt_warp_axis_deg", "pred_warp_axis_deg", "warp_axis_error_deg",
    "gt_weft_axis_deg", "pred_weft_axis_deg", "weft_axis_error_deg",
    "gt_warp_density_per_cm", "pred_warp_density_per_cm", "warp_density_error_pct",
    "gt_weft_density_per_cm", "pred_weft_density_per_cm", "weft_density_error_pct",
    "source", "candidate_only", "latency_ms", "peak_memory_mb",
)


def _numeric(value: str):
    return float(value) if value else None


def benchmark(manifest: list[dict], gt: list[dict], root: Path) -> tuple[list[dict], dict]:
    labels = {tuple(row[k] for k in KEY): row for row in gt}
    results = []
    all_errors = defaultdict(list)
    evaluated_by_metric = defaultdict(int)
    truth_by_metric = defaultdict(int)
    for row in manifest:
        key = tuple(row[k] for k in KEY)
        truth = labels.get(key, {})
        confirmed = truth.get("review_status") == "CONFIRMED"
        record = {name: "" for name in RESULT_FIELDS}
        record.update({name: row[name] for name in (*KEY, "split")})
        reasons = []
        pred = None
        if not row["result_json_path"]:
            reasons.append("NO_V5_RESULT_JSON")
        else:
            try: pred = load_v5(resolve_local(root, row["result_json_path"]))
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                reasons.append(f"INVALID_V5_RESULT: {exc}")
        if pred:
            reasons.extend(pred["reasons"])
            record["source"] = pred["source"]
            record["candidate_only"] = "YES"
        observed = 0
        for metric, (output_name, measure) in METRICS.items():
            base = _numeric(truth.get(metric, "")) if confirmed else None
            predicted = pred.get(metric) if pred else None
            record["gt_" + metric] = base if base is not None else ""
            record["pred_" + metric] = predicted if predicted is not None else ""
            if base is None:
                continue
            truth_by_metric[output_name] += 1
            if predicted is None:
                reasons.append(f"ABSTAINED_{metric.upper()}")
                continue
            error = measure(predicted, base)
            record[output_name] = round(error, 6)
            all_errors[output_name].append(error)
            evaluated_by_metric[output_name] += 1
            observed += 1
        if not confirmed:
            record["status"] = "NOT_EVALUATED"
            reasons.append("GROUND_TRUTH_NOT_CONFIRMED")
        elif not any(truth.get(key, "") for key in METRICS):
            record["status"] = "NOT_EVALUATED"
            reasons.append("NO_MEASURABLE_GROUND_TRUTH")
        elif observed:
            record["status"] = "EVALUATED_CANDIDATE" if pred else "NOT_EVALUATED"
        else:
            record["status"] = "ABSTAINED"
        record["failure_reason"] = " | ".join(dict.fromkeys(reasons))
        results.append(record)
    metric_summary = {
        name: {
            **summarize(all_errors[name]),
            "truth_available": truth_by_metric[name],
            "candidate_evaluated": evaluated_by_metric[name],
            "abstained": truth_by_metric[name] - evaluated_by_metric[name],
        }
        for name, _ in METRICS.values()
    }
    summary = {
        "status": "EVALUATED_CANDIDATES" if any(r["status"] == "EVALUATED_CANDIDATE" for r in results) else "NOT_EVALUATED",
        "caution": "Metrics describe V5 candidate-vs-confirmed-GT agreement, not released yarn-recognition accuracy.",
        "sample_rows": len(manifest),
        "confirmed_gt_rows": sum(r.get("review_status") == "CONFIRMED" for r in gt),
        "candidate_evaluated_rows": sum(r["status"] == "EVALUATED_CANDIDATE" for r in results),
        "abstained_rows": sum(r["status"] == "ABSTAINED" for r in results),
        "metrics": metric_summary,
    }
    return results, summary


def render_markdown(summary: dict) -> str:
    lines = ["# Fabric Benchmark — saved V5 candidate baseline", "",
             f"**Status:** `{summary['status']}`", "",
             "**Not a certified accuracy claim.** V5 lines and counts are candidate outputs; positive benchmark agreement does not prove one-to-one physical yarn identification.", "",
             f"Rows: {summary['sample_rows']} | Confirmed GT: {summary['confirmed_gt_rows']} | Candidate evaluated: {summary['candidate_evaluated_rows']} | Abstained: {summary['abstained_rows']}", "",
             "| Metric | GT available | Evaluated | Abstained | Mean error | P95 error |",
             "|---|---:|---:|---:|---:|---:|"]
    for name, metric in summary["metrics"].items():
        mean = f"{metric['mean']:.3f}" if metric["mean"] is not None else "NOT_EVALUATED"
        p95 = f"{metric['p95']:.3f}" if metric["p95"] is not None else "NOT_EVALUATED"
        lines.append(f"| {name} | {metric['truth_available']} | {metric['candidate_evaluated']} | {metric['abstained']} | {mean} | {p95} |")
    lines += ["", "Direction metrics are in degrees (0° ≡ 180°); density metrics are absolute percent errors (MAPE when averaged), not yarns/cm MAE.",
              "Latency and peak memory remain blank until reproducible measurements are captured.", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare saved V5 candidate JSON with manual textile GT")
    parser.add_argument("--manifest", type=Path, default=Path("datasets/manifest.csv"))
    parser.add_argument("--ground-truth", type=Path, default=Path("datasets/ground_truth.csv"))
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--out", type=Path, default=Path("experiments/step0-baseline"))
    parser.add_argument("--check-images", action="store_true")
    args = parser.parse_args(argv)
    try:
        manifest = load_csv(args.manifest, MANIFEST_FIELDS)
        truth = load_csv(args.ground_truth, GROUND_TRUTH_FIELDS)
        report = validate(manifest, truth, args.root, args.check_images)
        if report["errors"]:
            print(json.dumps(report, indent=2, ensure_ascii=False))
            return 2
        rows, summary = benchmark(manifest, truth, args.root)
    except (OSError, ValueError) as exc:
        print(f"DATASET_ERROR: {exc}")
        return 2
    args.out.mkdir(parents=True, exist_ok=True)
    with (args.out / "benchmark.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=RESULT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    (args.out / "benchmark_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (args.out / "benchmark_summary.md").write_text(render_markdown(summary), encoding="utf-8")
    print(f"{summary['status']}: {summary['sample_rows']} rows; reports in {args.out}")
    return 0 if summary["status"] == "EVALUATED_CANDIDATES" else 3


if __name__ == "__main__":
    raise SystemExit(main())
