#!/usr/bin/env python3
"""Safely import six ORIGINAL JPGs and six UNMARKED 2x enlargements.

Run on the *local* repository after downloading the clean ZIP.
No algorithm-generated yarn annotations are imported or produced.
Register only the 2x UNMARKED CROPS as annotation images in datasets/manifest.csv.
The original photo stays in images/ for provenance. The crop is not a
second independent physical fabric, nor a source of physical-yarn GT.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "datasets/user_contributed/2026-10-13-six-fabric-images"
PREFIX = "2026-10-13-six-fabric-images/"
MANIFEST = ROOT / "datasets/manifest.csv"
GT = ROOT / "datasets/ground_truth.csv"

EXPECTED_SHA = {
    "U20261013_01": "e273162299531d0eea5ff5d79b7c5937ba09d67b1101d8e54db3a313d28d0c91",
    "U20261013_02": "630cd4ea2245d7420307fae7704e34fb608a4c1f61379564321f03912a5312ca",
    "U20261013_03": "cc6d2c9507d086a6658f8939576bab84550e8cf532c6f8dc238542ae3e6a488f",
    "U20261013_04": "ce81fda0384c64381049869759fae7f3b51181c3914412640a3b8d4aa8d24a69",
    "U20261013_05": "4530b46cb4fa4236e4f15dcb0a62d97e41c3b34b3a4af6b3ffeeb3d1aa321250",
    "U20261013_06": "544b0e252daa44e4c1e01ac3d4680a870eb0fd01ae9549d3b9f4fe690ed56488",
}
MANIFEST_FIELDS = [
    "fabric_id", "position_id", "face", "split", "capture_mode",
    "image_path", "result_json_path", "calibration_type", "frame_confirmed", "notes",
]
GT_FIELDS = [
    "fabric_id", "position_id", "face", "review_status", "gt_source",
    "warp_axis_deg", "weft_axis_deg", "warp_density_per_cm", "weft_density_per_cm",
    "weave_type", "notes",
]


def sha(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def image_path(sid: str) -> Path:
    return DATA / "images" / (sid + ".jpg")


def zoom_path(sid: str) -> Path:
    return DATA / "zoom_unmarked" / (sid + "_center_2x.jpg")


def validate_local(*, require_images: bool) -> int:
    missing = []
    for sid, expected in EXPECTED_SHA.items():
        p = image_path(sid)
        if not p.is_file():
            missing.append(str(p.relative_to(ROOT)))
            continue
        if sha(p.read_bytes()) != expected:
            raise ValueError(f"{sid}: original JPEG SHA-256 mismatch; do not alter original bytes")
        z = zoom_path(sid)
        if not z.is_file():
            missing.append(str(z.relative_to(ROOT)))
    meta = DATA / "image_provenance.json"
    if meta.is_file():
        details = json.loads(meta.read_text(encoding="utf-8"))
        valid_status = {"UNANNOTATED",
                        "FIVE_OPERATOR_REVIEWED_PHYSICAL_YARN_TRAJECTORIES_ONE_NOT_ANNOTATED"}
        if details.get("annotation_status") not in valid_status:
            raise ValueError("unknown local human annotation status in image provenance")
        # The original/zoom JPG files must still be unmarked; the status says
        # whether SEPARATE human JSON trajectories have been reviewed.
        if details.get("annotation_status") != "UNANNOTATED":
            if details.get("annotation_target") != "PHYSICAL_YARN_TRAJECTORY":
                raise ValueError("reviewed paths must be real physical-yarn trajectories")
        for item in details["images"]:
            sid = item["sample_id"]
            if sid not in EXPECTED_SHA:
                raise ValueError(f"unknown file id {sid}")
            if item["original_sha256"] != EXPECTED_SHA[sid]:
                raise ValueError(f"{sid}: incorrect provenance source hash")
            z = zoom_path(sid)
            if z.exists() and sha(z.read_bytes()) != item["zoom_sha256"]:
                raise ValueError(f"{sid}: unmarked zoom JPEG SHA-256 mismatch")
    elif require_images:
        missing.append(str(meta.relative_to(ROOT)))
    for x in missing:
        print("MISSING:", x)
    print(f"Verified {6-sum(not image_path(s).exists() for s in EXPECTED_SHA)}/6 original JPGs; "
          f"missing original/zoom/provenance entries: {len(missing)}")
    return 2 if require_images and missing else 0


def _read_csv(path: Path, headers: list[str]) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        if r.fieldnames != headers:
            raise ValueError(f"unexpected CSV schema in {path}")
        return list(r)


def _write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    # Write only when changed; use atomic rename to protect the user's table.
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=headers, lineterminator="\n")
        wr.writeheader()
        wr.writerows(rows)
    temp.replace(path)


def register() -> None:
    if validate_local(require_images=True):
        raise ValueError("originals or unmarked zooms absent; register aborted")
    current = _read_csv(MANIFEST, MANIFEST_FIELDS)
    truth = _read_csv(GT, GT_FIELDS)
    by_id = {x["position_id"]: x for x in current}
    existing_gt = {x["position_id"] for x in truth}
    for sid in EXPECTED_SHA:
        target = f"datasets/user_contributed/2026-10-13-six-fabric-images/zoom_unmarked/{sid}_center_2x.jpg"
        original = f"datasets/user_contributed/2026-10-13-six-fabric-images/images/{sid}.jpg"
        note = ("user phone photo; label 2x unmarked center crop pixel coordinates; "
                "original archived in images; crop map in image_provenance.json; "
                "not an independent image sample; no pixelwise visible-yarn GT")
        if sid not in by_id:
            current.append({
                "fabric_id": "USER-" + sid, "position_id": sid,
                "face": "UNKNOWN", "split": "DEV",
                "capture_mode": "PHONE_UNKNOWN_LIGHTING",
                "image_path": target,
                "result_json_path": "", "calibration_type": "NONE",
                "frame_confirmed": "NO", "notes": note,
            })
        else:
            row = by_id[sid]
            if row["image_path"] not in (target, original):
                raise ValueError(f"{sid}: unexpected registered photo path; refusing overwrite")
            if row["image_path"] != target:
                annotation = ROOT / "datasets/annotations/drafts" / (sid + ".json")
                if annotation.is_file():
                    raise ValueError(f"{sid}: existing human annotation bound to ORIGINAL; "
                                     "reconcile before switching to zoom coordinates")
                row["image_path"] = target
            row["notes"] = note
        if sid not in existing_gt:
            truth.append({
                "fabric_id": "USER-" + sid, "position_id": sid,
                "face": "UNKNOWN", "review_status": "NOT_EVALUATED",
                "gt_source": "", "warp_axis_deg": "", "weft_axis_deg": "",
                "warp_density_per_cm": "", "weft_density_per_cm": "",
                "weave_type": "", "notes": "no operator-confirmed physical truth",
            })
    _write_csv(MANIFEST, MANIFEST_FIELDS, current)
    _write_csv(GT, GT_FIELDS, truth)
    print("Six 2x UNMARKED cropped JPGs registered as annotation inputs (idempotent).")
    print("Archival originals remain unchanged; no duplicate physical samples.")


def import_zip(zip_path: Path) -> None:
    if not zip_path.is_file():
        raise FileNotFoundError(f"ZIP missing: {zip_path}")
    with zipfile.ZipFile(zip_path) as archive:
        provenance_path = PREFIX + "image_provenance.json"
        details = json.loads(archive.read(provenance_path).decode("utf-8"))
        if details.get("annotation_status") != "UNANNOTATED":
            raise ValueError("refusing non-clean annotation bundle")
        if {x["sample_id"] for x in details["images"]} != set(EXPECTED_SHA):
            raise ValueError("ZIP does not contain exactly six expected samples")
        # Validate the ENTIRE bundle before writing any file.
        # The repository's provenance policy now binds human points to the 2x crop.
        # Do not replace the tracked, current policy with the older ZIP's policy.
        if not (DATA / "image_provenance.json").is_file():
            raise ValueError("image_provenance.json missing in checkout; please git pull main first")
        planned = []
        for rec in details["images"]:
            sid = rec["sample_id"]
            src = PREFIX + f"images/{sid}.jpg"
            zsrc = PREFIX + f"zoom_unmarked/{sid}_center_2x.jpg"
            if sha(archive.read(src)) != EXPECTED_SHA[sid]:
                raise ValueError(f"{sid}: altered source image")
            if sha(archive.read(zsrc)) != rec["zoom_sha256"]:
                raise ValueError(f"{sid}: altered enlargement")
            planned += [(src, image_path(sid)), (zsrc, zoom_path(sid))]
        for src, destination in planned:
            blob = archive.read(src)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists() and destination.read_bytes() == blob:
                continue
            if destination.exists():
                raise ValueError(f"refusing to overwrite different file: {destination}")
            destination.write_bytes(blob)
    print("Imported original JPGs + 2x unmarked centre crops; no assistant marks.")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--zip", type=Path, help="clean ZIP downloaded from ChatGPT")
    p.add_argument("--verify-only", action="store_true")
    args = p.parse_args()
    if args.zip:
        import_zip(args.zip)
    if args.verify_only:
        return validate_local(require_images=True)
    register()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
