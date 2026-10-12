"""Audit real downloaded photos without fabricating yarn directions or physical density.

Only image-file integrity and coarse visual diagnostics are tested here.
These are triage flags, NOT Gate 2 camera certification or recognition accuracy.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from benchmark.dataset import GROUND_TRUTH_FIELDS, KEY, MANIFEST_FIELDS, load_csv, resolve_local

FIELDS = (
    "source_id", "fabric_id", "image_path", "weave_weak_label", "state",
    "native_width", "native_height", "megapixels", "byte_size", "container",
    "sha256", "mean_gray", "p05_gray", "p95_gray", "quality_flags",
    "has_v5_result", "confirmed_gt", "frame_5cm_confirmed", "source_url",
)
QUEUE_FIELDS = ("priority", "source_id", "image_path", "weave_weak_label", "reason", "next_action")
PRIORITY = {
    "P001": (1, "平纹可见段与双方向参考"),
    "T001": (2, "牛仔斜纹可能带偏实际纱线"),
    "T002": (3, "格纹颜色条与真实纱线方向的区别"),
    "T004": (4, "手机拍摄牛仔布"),
    "T005": (5, "破斜纹与周期混淆"),
    "H001": (6, "人字纹纹理方向干扰"),
    "S001": (7, "缎纹浮长造成可见纱段不连续"),
    "X002": (8, "灯芯绒绒条不是经纬单根纱线"),
    "U001": (9, "未知组织必须允许拒判"),
}


def quantile(histogram: list[int], fraction: float) -> int:
    total = sum(histogram)
    if not total:
        raise ValueError("empty histogram")
    target = total * fraction
    seen = 0
    for index, count in enumerate(histogram):
        seen += count
        if seen >= target:
            return index
    return 255


def inspect_image(path: Path) -> dict:
    """Inspect real bytes; thumbnail statistics are non-certified review hints."""
    sha = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            sha.update(chunk)
    with Image.open(path) as original:
        image_format = original.format or "UNKNOWN"
        native_w, native_h = original.size
        view = ImageOps.exif_transpose(original)
        grayscale = view.convert("L")
        grayscale.thumbnail((256, 256), Image.Resampling.BILINEAR)
        hist = grayscale.histogram()
        count = sum(hist)
        mean = sum(v * n for v, n in enumerate(hist)) / count
    low = quantile(hist, 0.05)
    high = quantile(hist, 0.95)
    flags = []
    if min(native_w, native_h) < 1000:
        flags.append("SMALL_NATIVE_DIMENSION_REVIEW")
    if high - low < 35:
        flags.append("LOW_TONAL_SPREAD_REVIEW")
    if mean < 40 or mean > 215:
        flags.append("EXTREME_MEAN_BRIGHTNESS_REVIEW")
    return {
        "native_width": native_w, "native_height": native_h,
        "megapixels": round(native_w * native_h / 1_000_000, 3),
        "byte_size": path.stat().st_size, "container": image_format,
        "sha256": sha.hexdigest(), "mean_gray": round(mean, 2),
        "p05_gray": low, "p95_gray": high, "quality_flags": "|".join(flags),
    }


def analyze(root: Path, manifest_path: Path, ground_truth_path: Path, sources_path: Path):
    manifest = load_csv(manifest_path, MANIFEST_FIELDS)
    gt = load_csv(ground_truth_path, GROUND_TRUTH_FIELDS)
    catalog = json.loads(sources_path.read_text(encoding="utf-8"))
    sources = {x["id"]: x for x in catalog["items"]}
    truth = {tuple(x[k] for k in KEY): x for x in gt}
    rows, queue = [], []
    hash_owner = {}
    present_ids = set()
    for sample in manifest:
        source_id = sample["position_id"]
        item = sources.get(source_id)
        if not item:
            continue  # non-public phone and V5 regression photos are out of this catalog
        present_ids.add(source_id)
        expected = "datasets/public_samples/images/" + item["path"]
        record = {k: "" for k in FIELDS}
        record.update(
            source_id=source_id, fabric_id=sample["fabric_id"],
            image_path=sample["image_path"], weave_weak_label=item.get("weave_candidate", ""),
            state="OK", has_v5_result="YES" if sample["result_json_path"] else "NO",
            confirmed_gt="YES" if truth.get(tuple(sample[k] for k in KEY), {}).get("review_status") == "CONFIRMED" else "NO",
            frame_5cm_confirmed=sample["frame_confirmed"], source_url=item.get("source_page", ""),
        )
        if expected != sample["image_path"]:
            record["state"] = "SOURCE_PATH_MISMATCH"
        else:
            try:
                path = resolve_local(root, sample["image_path"])
                if not path.is_file():
                    record["state"] = "MISSING_IMAGE"
                else:
                    stats = inspect_image(path)
                    record.update(stats)
                    if stats["sha256"] in hash_owner:
                        record["quality_flags"] += "|DUPLICATE_BYTES_WITH_" + hash_owner[stats["sha256"]]
                    hash_owner[stats["sha256"]] = source_id
            except (OSError, ValueError, UnidentifiedImageError) as exc:
                record["state"] = "IMAGE_READ_ERROR"
                record["quality_flags"] = type(exc).__name__
        rows.append(record)
        if record["state"] == "OK" and record["confirmed_gt"] == "NO":
            priority, reason = PRIORITY.get(source_id, (100, "候选弱标签，需要人工确认真实物理纱段"))
            queue.append({
                "priority": priority, "source_id": source_id,
                "image_path": record["image_path"], "weave_weak_label": record["weave_weak_label"],
                "reason": reason,
                "next_action": "同一根真实纱线上人工标两点；独立确认经纬身份；保存证据",
            })
    queue.sort(key=lambda x: (int(x["priority"]), x["source_id"]))
    problems = [x for x in rows if x["state"] != "OK"]
    missing = sorted(set(sources) - present_ids)
    flags = Counter(y for x in rows for y in x["quality_flags"].split("|") if y)
    summary = {
        "status": "FAIL" if problems else "INCOMPLETE_NO_INDEPENDENT_GT",
        "source_catalog_entries": len(sources), "registered_public_images": len(rows),
        "not_registered_sources": len(missing), "not_registered_ids": missing,
        "unreadable_or_missing_images": len(problems), "no_v5_result": sum(x["has_v5_result"] == "NO" for x in rows),
        "without_confirmed_gt": sum(x["confirmed_gt"] == "NO" for x in rows),
        "without_confirmed_5cm_frame": sum(x["frame_5cm_confirmed"] != "YES" for x in rows),
        "review_quality_flags": dict(flags),
        "note": "Metadata and brightness flags do not establish real yarn direction, image sharpness, a 5cm physical scale, or benchmark accuracy.",
    }
    return rows, queue, summary


def write_csv(path: Path, names: tuple[str, ...], records: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=names, lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Audit downloaded public textile photos and generate human annotation queue")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--manifest", type=Path, default=Path("datasets/manifest.csv"))
    parser.add_argument("--ground-truth", type=Path, default=Path("datasets/ground_truth.csv"))
    parser.add_argument("--sources", type=Path, default=Path("datasets/public_samples/sources.json"))
    parser.add_argument("--out", type=Path, default=Path("experiments/public-photo-audit"))
    args = parser.parse_args(argv)
    try:
        rows, queue, summary = analyze(args.root, args.manifest, args.ground_truth, args.sources)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "FAIL", "reason": str(exc)}, ensure_ascii=False))
        return 2
    args.out.mkdir(parents=True, exist_ok=True)
    write_csv(args.out / "image_inventory.csv", FIELDS, rows)
    write_csv(args.out / "annotation_queue.csv", QUEUE_FIELDS, queue)
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    readme = [
        "# Public textile photo audit",
        "",
        f"- Catalog entries: {summary['source_catalog_entries']}",
        f"- Registered images: {summary['registered_public_images']}",
        f"- Pending unregistered sources: {summary['not_registered_sources']}",
        f"- Missing/unreadable: {summary['unreadable_or_missing_images']}",
        f"- Missing human-confirmed GT: {summary['without_confirmed_gt']}",
        f"- Missing saved V5 JSON: {summary['no_v5_result']}",
        "",
        "Weak source labels are not ground truth. Basic image stats and review flags are not camera-quality certification.",
        "The annotation queue asks for genuinely human-confirmed yarn reference points; no points or physical counts were synthesized.",
    ]
    (args.out / "summary.md").write_text("\n".join(readme) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 2 if summary["status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
