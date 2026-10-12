"""Incrementally register *downloaded* Commons photos; never invent textile GT.

Source catalog may contain prospective files not yet downloaded. Only existing
image bytes are eligible for manifest rows. An existing manifest/GT is preserved.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path, PurePosixPath

from benchmark.dataset import (
    MANIFEST_FIELDS, GROUND_TRUTH_FIELDS, KEY, load_csv, resolve_local, validate,
)


def prepare(root: Path, source_json: Path, manifest_path: Path, gt_path: Path):
    catalog = json.loads(source_json.read_text(encoding="utf-8"))
    items = catalog.get("items")
    if not isinstance(items, list):
        raise ValueError("sources.json items must be a list")
    manifest = load_csv(manifest_path, MANIFEST_FIELDS)
    gt = load_csv(gt_path, GROUND_TRUTH_FIELDS)
    known_manifest = {tuple(row[k] for k in KEY) for row in manifest}
    known_gt = {tuple(row[k] for k in KEY) for row in gt}
    previous_image_paths = {row["image_path"] for row in manifest}
    ids_seen: set[str] = set()
    paths_seen: set[str] = set()
    added: list[str] = []
    pending: list[str] = []
    existing: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("sources.json contains a non-object")
        sample_id = item.get("id")
        path_name = item.get("path")
        if not isinstance(sample_id, str) or not sample_id or not sample_id.replace("-", "").isalnum():
            raise ValueError(f"invalid source ID: {sample_id!r}")
        if sample_id in ids_seen:
            raise ValueError(f"duplicate source ID: {sample_id}")
        ids_seen.add(sample_id)
        if not isinstance(path_name, str) or not path_name or any(x in (".", "..") for x in PurePosixPath(path_name).parts) or PurePosixPath(path_name).is_absolute() or "\\" in path_name or ":" in path_name or PurePosixPath(path_name).suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
            raise ValueError(f"invalid image path for {sample_id}")
        path = f"datasets/public_samples/images/{path_name}"
        if path in paths_seen:
            raise ValueError(f"duplicate image source path: {path}")
        paths_seen.add(path)
        local_file = resolve_local(root, path)
        if not local_file.is_file() or local_file.stat().st_size == 0:
            pending.append(sample_id)
            continue
        if not item.get("source_page") or not item.get("license"):
            raise ValueError(f"missing licensing/source metadata: {sample_id}")
        fabric_id = f"PUBLIC-{sample_id}"
        key = (fabric_id, sample_id, "UNKNOWN")
        if path in previous_image_paths or key in known_manifest:
            existing.append(sample_id)
            continue
        # Identity/face/illumination/GT are unknown, even when a source title names a weave.
        manifest.append(dict(zip(MANIFEST_FIELDS, (
            fabric_id, sample_id, "UNKNOWN", "DEV", "PUBLIC_UNKNOWN", path, "", "NONE", "NO",
            f"source_id={sample_id}; weak_weave={item.get('weave_candidate', 'unknown')}; NOT_GROUND_TRUTH",
        ))))
        known_manifest.add(key)
        previous_image_paths.add(path)
        if key not in known_gt:
            gt.append(dict(zip(GROUND_TRUTH_FIELDS, (
                fabric_id, sample_id, "UNKNOWN", "NOT_EVALUATED", "", "", "", "", "", "",
                "Source weave metadata is weak label only; human physical GT absent",
            ))))
            known_gt.add(key)
        added.append(sample_id)
    validation = validate(manifest, gt, root, check_images=True)
    return manifest, gt, {
        "status": "FAIL" if validation["errors"] else "INCOMPLETE",
        "source_entries": len(items),
        "present_images": len(added) + len(existing),
        "added": added,
        "already_registered": existing,
        "pending_image_download": pending,
        "ground_truth_confirmed": sum(r["review_status"] == "CONFIRMED" for r in gt),
        "validation": validation,
    }


def write_csv(path: Path, fields: tuple[str, ...], rows: list[dict]):
    # Existing columns and existing manual labels survive unchanged.
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Register downloaded public image assets without manufacturing GT")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--source-json", type=Path, default=Path("datasets/public_samples/sources.json"))
    parser.add_argument("--manifest", type=Path, default=Path("datasets/manifest.csv"))
    parser.add_argument("--ground-truth", type=Path, default=Path("datasets/ground_truth.csv"))
    parser.add_argument("--write", action="store_true", help="persist new rows; default is dry-run")
    args = parser.parse_args(argv)
    try:
        manifest, gt, report = prepare(args.root, args.source_json, args.manifest, args.ground_truth)
        if args.write and not report["validation"]["errors"]:
            write_csv(args.manifest, MANIFEST_FIELDS, manifest)
            write_csv(args.ground_truth, GROUND_TRUTH_FIELDS, gt)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2 if report["validation"]["errors"] else 0
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "FAIL", "errors": [str(exc)]}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
