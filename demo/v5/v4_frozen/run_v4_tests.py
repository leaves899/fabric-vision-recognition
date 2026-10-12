#!/usr/bin/env python3
r"""Run an unchanged V4 source using a disposable I/O-only execution copy.

This harness NEVER writes to frozen/reoptimize_v4_quadgrid.py. It replaces only
hard-coded input/output file paths in a temporary copy and inserts a vector
export AFTER all yarn detection decisions have already been made.

Usage (PowerShell 7):
    python .\run_v4_tests.py --mode regression --repeat 2
    python .\run_v4_tests.py --mode unseen --input-dir .\data\unseen --repeat 2
    python .\run_v4_tests.py --mode unseen --input-dir .\data\unseen --gt .\manual_gt.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "frozen" / "reoptimize_v4_quadgrid.py"
MANIFEST = ROOT / "freeze_manifest.json"
REFERENCE = ROOT / "baseline" / "summary.json"

ORIGINAL_PATHS = {
    "output": "/mnt/data/reoptimize_v4",
    "training": "/mnt/data/ghostwriter_images/context/cbd213a0-f246-5e17-a674-15bc3f8bbbef.jpg",
    "gt": "/mnt/data/fabric_direction_fix/registered_user_annotation_masks.npz",
    "img1": "/mnt/data/ghostwriter_images/context/c1667069-4f96-59ad-9345-b7704712fdde.jpg",
    "img2": "/mnt/data/ghostwriter_images/context/76e460f0-a54a-5114-adac-89682aeea51c.jpg",
    "img3": "/mnt/data/ghostwriter_images/context/5ffdc98f-1c47-5fea-a833-ebdd1117552a.jpg",
}

TRACK_EXPORT_ANCHOR = (
    "    panel=draw(full,first_ev,second_ev,first_lines,second_lines,orig_poly,name,angle)\n"
)
TRACK_EXPORT_LINE = (
    "    (OUT/f'{name}_tracks.json').write_text("
    "json.dumps({'first':first_lines,'second':second_lines}, "
    "ensure_ascii=False),encoding='utf-8')\n"
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_manifest() -> dict[str, Any]:
    with MANIFEST.open(encoding="utf-8") as f:
        return json.load(f)


def check_frozen_inputs(manifest: dict[str, Any]) -> None:
    expected = manifest["files_sha256"]
    errors = []
    for relative, digest in expected.items():
        path = ROOT / relative
        if not path.is_file():
            errors.append(f"缺少文件: {relative}")
        elif sha256(path) != digest:
            errors.append(f"SHA256 不匹配（已被修改）: {relative}")
    if errors:
        raise RuntimeError("冻结校验失败:\n" + "\n".join(errors))


def select_inputs(mode: str, input_dir: Path | None) -> dict[str, Path]:
    mapping = {
        "training": ROOT / "data" / "train" / "training.jpg",
        "gt": ROOT / "data" / "train" / "manual_masks.npz",
    }
    if mode == "regression":
        directory = ROOT / "data" / "regression"
    else:
        directory = input_dir or (ROOT / "data" / "unseen")
    for name in ("img1", "img2", "img3"):
        mapping[name] = directory / f"{name}.jpg"
    return mapping


def verify_input_dimensions(inputs: dict[str, Path], mode: str) -> list[str]:
    try:
        from PIL import Image
    except ImportError as e:
        raise RuntimeError("请先安装 requirements.txt（需要 Pillow）") from e

    notes = []
    for name, (y0, y1, x0, x1) in {
        "img1": (215, 1335, 355, 1715),
        "img2": (125, 1375, 255, 1765),
        "img3": (125, 1395, 235, 1780),
    }.items():
        path = inputs[name]
        if not path.is_file():
            raise FileNotFoundError(
                f"{name} 照片不存在：{path}。未见新布料时不能声称完成泛化测试。"
            )
        with Image.open(path) as im:
            w, h = im.size
        if w < x1 or h < y1:
            raise ValueError(
                f"{name} 尺寸 {w}x{h} 不满足冻结 V4 的固定 ROI "
                f"(x={x0}:{x1}, y={y0}:{y1})，不可通过自动缩放来掩盖限制。"
            )
        if (w, h) != (2048, 1536):
            notes.append(
                f"警告：{name} 输入尺寸为 {w}x{h}，与原始样本 2048x1536 不同；"
                "虽然 ROI 没有越界，固定角度和裁剪范围仍可能失效。"
            )
    if mode == "unseen":
        reference_hashes = {
            sha256(ROOT / "data" / "train" / "training.jpg")
        } | {
            sha256(ROOT / "data" / "regression" / f"img{i}.jpg")
            for i in (1, 2, 3)
        }
        for name in ("img1", "img2", "img3"):
            if sha256(inputs[name]) in reference_hashes:
                raise ValueError(
                    f"{name} 与训练/回归照片字节完全相同，不能充当未见过的新布料。"
                )
        notes.append(
            "注意：只能排除字节完全相同的照片。三张照片是否属于独立新布料，"
            "以及是否与训练布料同源，仍需人工核查。"
        )
    return notes


def make_execution_copy(inputs: dict[str, Path], output_dir: Path) -> str:
    """Replace exact string literals for paths only; preserve all V4 decisions."""
    src = SOURCE.read_text(encoding="utf-8")
    patch = {
        ORIGINAL_PATHS["output"]: output_dir.resolve(),
        ORIGINAL_PATHS["training"]: inputs["training"].resolve(),
        ORIGINAL_PATHS["gt"]: inputs["gt"].resolve(),
        ORIGINAL_PATHS["img1"]: inputs["img1"].resolve(),
        ORIGINAL_PATHS["img2"]: inputs["img2"].resolve(),
        ORIGINAL_PATHS["img3"]: inputs["img3"].resolve(),
    }
    result = src
    for old, new in patch.items():
        literal_old = repr(old)
        if result.count(literal_old) != 1:
            raise RuntimeError(f"找不到唯一冻结路径，源代码结构可能发生变化: {old}")
        result = result.replace(literal_old, repr(str(new)), 1)
    if result.count(TRACK_EXPORT_ANCHOR) != 1:
        raise RuntimeError("未找到唯一只读矢量轨迹导出插桩位置")
    result = result.replace(
        TRACK_EXPORT_ANCHOR,
        TRACK_EXPORT_LINE + TRACK_EXPORT_ANCHOR,
        1,
    )
    compile(result, "v4_temporary_execution.py", "exec")
    return result


def run_once(inputs: dict[str, Path], run_dir: Path) -> dict[str, Any]:
    run_dir.mkdir(parents=True, exist_ok=True)
    script = run_dir / "v4_temporary_execution.py"
    script.write_text(make_execution_copy(inputs, run_dir), encoding="utf-8")
    started = time.perf_counter()
    with (run_dir / "stdout.txt").open("w", encoding="utf-8") as stdout, (
        run_dir / "stderr.txt"
    ).open("w", encoding="utf-8") as stderr:
        finished = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(ROOT),
            stdout=stdout,
            stderr=stderr,
            check=False,
        )
    duration = time.perf_counter() - started
    if finished.returncode != 0:
        raise RuntimeError(
            f"V4 运行失败 (exit={finished.returncode})，请检查 {run_dir / 'stderr.txt'}"
        )

    expected = ["summary.json", "three_images_reopt_v4_comparison.png"]
    for n in ("img1", "img2", "img3"):
        expected.extend(
            (f"{n}_three_panel_reopt_v4.png", f"{n}_mask_overlay.png", f"{n}_tracks.json")
        )
    missing = [name for name in expected if not (run_dir / name).is_file()]
    if missing:
        raise RuntimeError(f"V4 运行结束但缺少结果文件: {missing}")
    with (run_dir / "summary.json").open(encoding="utf-8") as f:
        summary = json.load(f)
    return {
        "elapsed_seconds": round(duration, 3),
        "summary": summary,
        "files_sha256": {name: sha256(run_dir / name) for name in expected},
    }


def compare_reference(summary: list[dict]) -> list[str]:
    ref = {row["name"]: row for row in json.loads(REFERENCE.read_text(encoding="utf-8"))}
    diffs = []
    for row in summary:
        name = row["name"]
        if name not in ref:
            diffs.append(f"发现不在冻结回归摘要中的图片：{name}")
            continue
        for key in (
            "first_family_count", "second_family_count", "row_grid_step", "col_grid_step"
        ):
            if row[key] != ref[name][key]:
                diffs.append(f"{name}.{key}：冻结={ref[name][key]}，本次={row[key]}")
    return diffs


def compare_runs(runs: list[dict[str, Any]]) -> list[str]:
    if len(runs) < 2:
        return []
    diffs = []
    base = runs[0]
    for index, run in enumerate(runs[1:], 2):
        if run["summary"] != base["summary"]:
            diffs.append(f"第 {index} 次 summary.json 与首次不一致")
        for name, digest in base["files_sha256"].items():
            if run["files_sha256"].get(name) != digest:
                diffs.append(f"第 {index} 次结果 {name} 与首次 SHA256 不一致")
    return diffs


def main() -> int:
    parser = argparse.ArgumentParser(description="冻结 V4 只读重复/跨布料测试")
    parser.add_argument("--mode", choices=["regression", "unseen"], default="regression")
    parser.add_argument("--input-dir", type=Path, help="新布料图片所在目录，需 img1.jpg/img2.jpg/img3.jpg")
    parser.add_argument("--repeat", type=int, default=2)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "test_results")
    parser.add_argument("--gt", type=Path, help="额外提供人工逐根标注 JSON，见示例模板")
    parser.add_argument("--tolerance-px", type=float, default=5.0)
    parser.add_argument("--geometry", choices=["adaptive", "strict"],
                        help="仅 unseen：adaptive=原图尺寸兼容入口（默认）；strict=原始固定 ROI")
    parser.add_argument("--input", action="append", type=Path, default=[],
                        help="仅 unseen adaptive：可传一个或多个任意文件名的照片")
    parser.add_argument("--fabric-id", help="仅 unseen adaptive：测试者声明的布料编号")
    args = parser.parse_args()
    if args.repeat < 1:
        parser.error("--repeat 必须至少为 1")
    try:
        manifest = load_manifest()
        check_frozen_inputs(manifest)
        if args.mode == "unseen" and (args.geometry or "adaptive") == "adaptive":
            if args.gt:
                raise ValueError("自适应入口的人工标注必须使用原图坐标，旧 ROI_LOCAL GT 不可直接混用；请先运行不带 --gt 的兼容性测试")
            from run_v4_flexible import run_flexible
            return run_flexible(
                args.input_dir, args.input, args.repeat,
                args.output_dir / "unseen_flexible", fabric_id=args.fabric_id,
            )
        if args.input:
            raise ValueError("--input 仅适用于 --mode unseen --geometry adaptive")
        inputs = select_inputs(args.mode, args.input_dir)
        notes = verify_input_dimensions(inputs, args.mode)
        output_root = args.output_dir.resolve() / args.mode
        output_root.mkdir(parents=True, exist_ok=True)
        all_runs = []
        for i in range(1, args.repeat + 1):
            run_dir = output_root / f"run_{i:02d}"
            print(f"[{i}/{args.repeat}] 运行原始 V4，输出目录: {run_dir}", flush=True)
            run = run_once(inputs, run_dir)
            all_runs.append(run)
            print(f"    完成，耗时 {run['elapsed_seconds']} 秒", flush=True)
        repeat_diffs = compare_runs(all_runs)
        reference_diffs = (
            compare_reference(all_runs[0]["summary"]) if args.mode == "regression" else []
        )
        # No implied accuracy measurements from count/similarity alone.
        status = "PASS" if not repeat_diffs and not reference_diffs else "FAIL"
        if args.repeat == 1 and status == "PASS":
            status = "INCOMPLETE_ONE_RUN"
        report = {
            "status": status,
            "mode": args.mode,
            "frozen_source_sha256": sha256(SOURCE),
            "repeat": args.repeat,
            "per_run": all_runs,
            "repeat_differences": repeat_diffs,
            "baseline_differences": reference_diffs,
            "notes": notes,
            "accuracy_status": "NOT_MEASURED_NO_MANUAL_GT",
            "repeatability_status": "NOT_TESTED" if args.repeat == 1 else ("PASS" if not repeat_diffs else "FAIL"),
            "limitations": [
                "该版本固定 ROI 与旋转角度；未进行自动适配，输入分布变化可能失败",
                "同一照片多次重复只能检查确定性，不证明泛化或真实纱线正确率",
                "同一块布料的多张照片不是跨布料独立测试",
                "输出线数不是正确识别根数，更不等于准确率",
                "所有测试运行均未重训，也未修改 V4 原始算法逻辑",
            ],
        }
        if args.gt:
            from score_tracks import score_dataset
            path = output_root / "run_01"
            gt = json.loads(args.gt.read_text(encoding="utf-8"))
            report["manual_gt_evaluation"] = score_dataset(path, gt, args.tolerance_px)
            supplied = any(gt.get(img, {}).get(fam, []) for img in ("img1", "img2", "img3") for fam in ("first", "second"))
            if supplied:
                report["accuracy_status"] = "PARTIAL_GT_POLYLINE_MATCH_ESTIMATE"
        report_path = output_root / "test_report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        lines = [
            f"V4 冻结测试：{status}",
            f"模式：{args.mode}，重复 {args.repeat} 次，原始 SHA256：{report['frozen_source_sha256']}",
            "同输入重复结果：" + ("未测试（只有1次）" if args.repeat == 1 else ("一致" if not repeat_diffs else "有差异")),
        ]
        if args.mode == "regression":
            lines.append("冻结计数/间距基线：" + ("一致" if not reference_diffs else "有差异"))
        lines.extend("问题：" + x for x in (repeat_diffs + reference_diffs))
        lines.extend("备注：" + x for x in notes)
        lines.append(f"报告：{report_path}")
        (output_root / "test_report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("\n".join(lines), flush=True)
        return 0 if status in ("PASS", "INCOMPLETE_ONE_RUN") else 2
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
