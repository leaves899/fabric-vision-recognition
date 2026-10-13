"""Local Git-trackable PHONE-ONLY evidence annotations.

Separate from both operator PHYSICAL_YARN_REFERENCE path anchors and the
independently physically verified local_patches.json GT ledger.

Coordinates are native pixels in the registered photograph (U20261013 are 2x
enlarged center crops). Neither boxes nor short strokes certify actual yarn
identity or pixelwise segmentation truth. The same external image audit used
by legacy annotations applies here.
"""
from __future__ import annotations

import json
import math
import os
import tempfile
from pathlib import Path
from datetime import datetime, timezone

from benchmark.manual_annotation import image_stats, samples, _zoom_review_provenance

FOLDER = Path("datasets/physical_evidence_labels/manual_image_reviews")
SCHEMA = "1.0"
SOURCE = "PHONE_IMAGE_OPERATOR_REVIEW"
KINDS = {
    "APPARENT_VISIBLE_YARN", "GAP", "TWILL_PATTERN",
    "COLOR_STRIPE", "SHADOW", "OCCLUSION", "UNCERTAIN",
}
RELATIONS = {"SAME_PHYSICAL_YARN", "DIFFERENT_PHYSICAL_YARN", "UNKNOWN"}
MAX_REGIONS = 400
MAX_RELATIONS = 400


def _point(p, width, height):
    if (not isinstance(p, list) or len(p) != 2 or
        any(isinstance(v, bool) or not isinstance(v, (int, float)) or
            not math.isfinite(v) for v in p)):
        raise ValueError("point must be two finite pixel coordinates")
    x, y = p
    if not (0 <= x < width and 0 <= y < height):
        raise ValueError("point outside registered image")
    return [round(float(x), 3), round(float(y), 3)]


def _geometry(geometry, width, height):
    if not isinstance(geometry, dict):
        raise ValueError("region geometry must be an object")
    typ = geometry.get("type")
    if typ == "RECT":
        rect = geometry.get("bbox")
        if not isinstance(rect, list) or len(rect) != 4:
            raise ValueError("rectangle needs bbox [x0,y0,x1,y1]")
        lo = _point(rect[:2], width, height)
        hi = _point(rect[2:], width, height)
        if hi[0] - lo[0] < 4 or hi[1] - lo[1] < 4:
            raise ValueError("rectangle should be at least 4 by 4 pixels")
        return {"type": "RECT", "bbox": lo + hi}
    if typ == "LINE":
        points = geometry.get("points")
        if not isinstance(points, list) or len(points) != 2:
            raise ValueError("short line needs two endpoints")
        p, q = [_point(x, width, height) for x in points]
        if math.dist(p, q) < 4:
            raise ValueError("short line should span at least 4 pixels")
        return {"type": "LINE", "points": [p, q]}
    raise ValueError("unsupported geometry; use RECT or LINE")


def validate_local_review(root: Path, payload: dict) -> dict:
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA:
        raise ValueError("unsupported local evidence review schema")
    sid = payload.get("sample_id")
    row = samples(root).get(sid)
    if row is None:
        raise ValueError("unknown registered sample_id")
    if payload.get("image_path") != row["image_path"]:
        raise ValueError("image_path does not match registered image")
    checksum, (width, height) = image_stats(root, row)
    _zoom_review_provenance(root, row, checksum, (width, height))
    if payload.get("image_sha256") not in (None, "", checksum):
        raise ValueError("source image SHA-256 differs from review")
    if payload.get("annotation_source", SOURCE) != SOURCE:
        raise ValueError("phone-only review cannot claim independent physical ground truth")
    if payload.get("independent_physical_gt") not in (None, False):
        raise ValueError("phone-only review is never independent physical ground truth")
    status = payload.get("review_state", "DRAFT")
    if status not in ("DRAFT", "OPERATOR_REVIEWED"):
        raise ValueError("invalid local review state")
    note = payload.get("notes", "")
    if not isinstance(note, str) or len(note) > 2000:
        raise ValueError("notes must be text of at most 2000 characters")
    regions = payload.get("regions", [])
    links = payload.get("relations", [])
    if not isinstance(regions, list) or len(regions) > MAX_REGIONS:
        raise ValueError("invalid or oversized regions array")
    if not isinstance(links, list) or len(links) > MAX_RELATIONS:
        raise ValueError("invalid or oversized relations array")
    ids = set()
    checked = []
    for item in regions:
        if not isinstance(item, dict):
            raise ValueError("region must be an object")
        rid = item.get("id")
        if not isinstance(rid, str) or not 1 <= len(rid) <= 40 or not rid.isascii() or not all(
                c.isalnum() or c in "_-" for c in rid):
            raise ValueError("region id must be short ASCII letters/digits")
        if rid in ids:
            raise ValueError("duplicate region id")
        ids.add(rid)
        kind = item.get("kind")
        if kind not in KINDS:
            raise ValueError("unknown local evidence category")
        geom = _geometry(item.get("geometry"), width, height)
        if geom["type"] == "LINE" and kind not in ("APPARENT_VISIBLE_YARN", "UNCERTAIN"):
            raise ValueError("short line is only for apparent yarn or unknown")
        remark = item.get("note", "")
        if not isinstance(remark, str) or len(remark) > 500:
            raise ValueError("invalid region note")
        checked.append({"id": rid, "kind": kind, "geometry": geom, "note": remark.strip(),
                        "physical_identity_confirmed": False,
                        "pixelwise_yarn_mask_gt": False})
    rel = []
    used = set()
    for item in links:
        if not isinstance(item, dict):
            raise ValueError("relation must be object")
        a, b, label = item.get("a"), item.get("b"), item.get("relation")
        if a not in ids or b not in ids or a == b:
            raise ValueError("relation requires two different saved region ids")
        if label not in RELATIONS:
            raise ValueError("unknown relationship")
        pair = tuple(sorted((a,b)))
        if pair in used:
            raise ValueError("duplicate pairwise relation")
        used.add(pair)
        rel.append({"a": a, "b": b, "relation": label,
                    "evidence_source": SOURCE,
                    "independent_physical_gt": False})
    return {
        "schema_version": SCHEMA, "sample_id": sid, "fabric_id": row["fabric_id"],
        "image_path": row["image_path"], "image_sha256": checksum,
        "image_width": width, "image_height": height,
        "annotation_target": "LOCAL_IMAGE_EVIDENCE_REVIEW",
        "annotation_source": SOURCE, "independent_physical_gt": False,
        "review_state": status, "notes": note.strip(),
        "regions": checked, "relations": rel,
        "coordinate_space": ("ZOOM_2X_NATIVE_PIXELS" if sid.startswith("U20261013_")
                             else "IMAGE_NATIVE_PIXELS"),
        "physical_yarn_reference_unchanged": True,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def review_path(root: Path, sid: str):
    if sid not in samples(root):
        raise ValueError("unknown registered sample")
    return root / FOLDER / (sid + ".json")


def load_local_review(root: Path, sid: str):
    path = review_path(root, sid)
    if path.is_file():
        return validate_local_review(root, json.loads(path.read_text(encoding="utf-8")))
    row = samples(root)[sid]
    checksum, (width, height) = image_stats(root, row)
    return {
        "schema_version": SCHEMA, "sample_id": sid, "fabric_id": row["fabric_id"],
        "image_path": row["image_path"], "image_sha256": checksum,
        "image_width": width, "image_height": height,
        "annotation_target": "LOCAL_IMAGE_EVIDENCE_REVIEW",
        "annotation_source": SOURCE, "independent_physical_gt": False,
        "review_state": "DRAFT", "notes": "", "regions": [], "relations": [],
    }


def store_local_review(root: Path, payload: dict):
    result = validate_local_review(root, payload)
    path = review_path(root, result["sample_id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    # Different temporary files avoid races with the legacy annotation writer.
    fd, name = tempfile.mkstemp(prefix=path.stem+".",suffix=".tmp",dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(result, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    return result


def audit_local_reviews(root: Path):
    report = {"annotation_source": SOURCE, "independent_physical_gt": False,
              "reviewed_samples": 0, "saved_samples": 0,
              "region_counts": {}, "relations": 0, "invalid_samples": []}
    for sid in samples(root):
        path = review_path(root, sid)
        if not path.is_file():
            continue
        try:
            item = validate_local_review(root, json.loads(path.read_text(encoding="utf-8")))
        except (ValueError, OSError, KeyError, json.JSONDecodeError):
            report["invalid_samples"].append(sid)
            continue
        report["saved_samples"] += 1
        report["reviewed_samples"] += (item["review_state"] == "OPERATOR_REVIEWED")
        report["relations"] += len(item["relations"])
        for region in item["regions"]:
            kind = region["kind"]
            report["region_counts"][kind] = report["region_counts"].get(kind,0)+1
    return report
