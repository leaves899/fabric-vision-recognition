"""Local-only, operator-driven yarn-direction annotation service.

Human reference points are V5 *inputs*, not independent algorithm ground truth.
The service never guesses points, warp/weft identity, weave class or density.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from benchmark.dataset import MANIFEST_FIELDS, load_csv, resolve_local

DEFAULT_FOLDER = Path("datasets/annotations/drafts")
MODES = {"DRAFT", "OPERATOR_REVIEWED"}
ELIGIBILITY = {"UNREVIEWED", "DENIM_CANDIDATE", "NEGATIVE_NON_DENIM", "UNCERTAIN"}
FAMILIES = {"UNKNOWN", "WARP", "WEFT"}
SEGMENTS = ("reference", "check_same", "check_cross")


def samples(root: Path) -> dict[str, dict]:
    items = load_csv(root / "datasets/manifest.csv", MANIFEST_FIELDS)
    return {item["position_id"]: item for item in items if item["capture_mode"] == "PUBLIC_UNKNOWN"}


def image_stats(root: Path, row: dict) -> tuple[str, tuple[int, int]]:
    """Pillow uses display-oriented EXIF dimensions; image bytes remain unchanged."""
    from PIL import Image, ImageOps
    image = resolve_local(root, row["image_path"])
    checksum = hashlib.sha256(image.read_bytes()).hexdigest()
    with Image.open(image) as data:
        size = ImageOps.exif_transpose(data).size
    return checksum, size


def _segment(points, width: int, height: int, name: str, *, required: bool):
    if points is None or points == []:
        if required:
            raise ValueError(f"{name}: two real-yarn points are required")
        return None
    if not isinstance(points, list) or len(points) != 2:
        raise ValueError(f"{name}: expected two points")
    checked = []
    for p in points:
        if (not isinstance(p, list) or len(p) != 2 or
            any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in p)):
            raise ValueError(f"{name}: coordinates must be finite numeric pairs")
        x, y = p
        if not (0 <= x < width and 0 <= y < height):
            raise ValueError(f"{name}: a point lies outside the original image")
        checked.append([round(float(x), 3), round(float(y), 3)])
    if math.dist(*checked) < 20:
        raise ValueError(f"{name}: reference segment shorter than 20 original pixels")
    return checked


def segment_axis_deg(points: list[list[float]]) -> float:
    return math.degrees(math.atan2(points[1][1] - points[0][1],
                                   points[1][0] - points[0][0])) % 180


def validate_annotation(root: Path, data: dict) -> dict:
    if not isinstance(data, dict) or data.get("schema_version") != "1.0":
        raise ValueError("unsupported annotation schema")
    sid = data.get("sample_id")
    row = samples(root).get(sid)
    if row is None:
        raise ValueError("unknown registered public sample_id")
    if data.get("image_path") != row["image_path"]:
        raise ValueError("image path does not match the registered manifest")
    checksum, (width, height) = image_stats(root, row)
    supplied = data.get("image_sha256")
    if supplied not in (None, "", checksum):
        raise ValueError("image hash changed since annotation; review coordinates")
    eligibility = data.get("eligibility", "UNREVIEWED")
    review_state = data.get("review_state", "DRAFT")
    family = data.get("reference_family", "UNKNOWN")
    if eligibility not in ELIGIBILITY or review_state not in MODES or family not in FAMILIES:
        raise ValueError("invalid review state, eligibility, or reference identity")
    confirmed = data.get("reference_confirmed") is True
    points = data.get("segments", {})
    if not isinstance(points, dict):
        raise ValueError("segments must be a JSON object")
    normalized = {
        name: _segment(points.get(name), width, height, name,
                       required=(name == "reference" and (confirmed or review_state == "OPERATOR_REVIEWED")))
        for name in SEGMENTS
    }
    if review_state == "OPERATOR_REVIEWED" and not confirmed:
        raise ValueError("reviewed reference needs explicit operator confirmation")
    if normalized["check_same"] == normalized["reference"] and normalized["reference"] is not None:
        raise ValueError("check_same must be a DIFFERENT segment, not the V5 input reference")
    if normalized["check_cross"] == normalized["reference"] and normalized["reference"] is not None:
        raise ValueError("check_cross must be a DIFFERENT segment")
    if family != "UNKNOWN" and not data.get("identity_confirmed") is True:
        raise ValueError("warp/weft physical identity requires an explicit confirmation")
    if eligibility == "NEGATIVE_NON_DENIM" and review_state == "OPERATOR_REVIEWED":
        raise ValueError("non-denim negatives must remain outside the primary denim benchmark")
    notes = data.get("notes", "")
    if not isinstance(notes, str) or len(notes) > 4000:
        raise ValueError("notes must be text of at most 4000 characters")
    return {
        "schema_version": "1.0", "sample_id": sid, "fabric_id": row["fabric_id"],
        "image_path": row["image_path"], "image_sha256": checksum,
        "image_width": width, "image_height": height,
        "eligibility": eligibility, "review_state": review_state,
        "reference_confirmed": confirmed, "reference_family": family,
        "identity_confirmed": family != "UNKNOWN",
        "segments": normalized, "notes": notes.strip(),
        "annotation_origin": "OPERATOR_CLICKED_NOT_ALGORITHM_GT",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _annotation_path(root: Path, sid: str) -> Path:
    if sid not in samples(root):
        raise ValueError("unknown sample")
    return root / DEFAULT_FOLDER / (sid + ".json")


def store_annotation(root: Path, data: dict) -> dict:
    result = validate_annotation(root, data)
    target = _annotation_path(root, result["sample_id"])
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(".json.tmp")
    temp.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, target)
    return result


def audit(root: Path) -> dict:
    images = samples(root)
    ready, draft, stale, non_denim, unknown = [], [], [], [], []
    for sid, row in images.items():
        path = root / DEFAULT_FOLDER / (sid + ".json")
        if not path.exists():
            unknown.append(sid)
            continue
        try:
            data = validate_annotation(root, json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            stale.append(sid)
            continue
        if data["eligibility"] == "NEGATIVE_NON_DENIM":
            non_denim.append(sid)
        elif data["review_state"] == "OPERATOR_REVIEWED" and data["reference_confirmed"]:
            ready.append(sid)
        else:
            draft.append(sid)
    return {
        "status": "READY_FOR_V5" if ready else "NO_REVIEWED_YARN_REFERENCES",
        "registered_public": len(images), "ready_for_v5": ready,
        "draft": draft, "negative_non_denim": non_denim,
        "stale_or_invalid": stale, "not_started": len(unknown),
        "warning": "Operator input is not independent GT. V5 candidates must be compared to different physically verified segments.",
    }


class AnnotationHandler(SimpleHTTPRequestHandler):
    server_version = "YarnAnnotationLocal/1.0"

    def __init__(self, *args, directory=None, **kwargs):
        super().__init__(*args, directory=directory, **kwargs)

    def _json(self, payload, code=200):
        blob = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(blob)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(blob)

    def do_GET(self):
        path = urlsplit(self.path)
        root = self.server.repo_root
        if path.path == "/api/items":
            items = [
                {"sample_id": x["position_id"], "image_path": x["image_path"],
                 "fabric_id": x["fabric_id"], "notes": x["notes"],
                 "annotated": (root / DEFAULT_FOLDER / (x["position_id"] + ".json")).is_file()}
                for x in samples(root).values()
            ]
            return self._json({"items": items})
        if path.path == "/api/annotation":
            sid = parse_qs(path.query).get("id", [""])[0]
            try:
                target = _annotation_path(root, sid)
                if target.is_file():
                    return self._json(json.loads(target.read_text(encoding="utf-8")))
                return self._json({"schema_version": "1.0", "sample_id": sid,
                                   "image_path": samples(root)[sid]["image_path"]})
            except (KeyError, ValueError, OSError, json.JSONDecodeError):
                return self._json({"error": "sample not found or corrupt saved annotation"}, 404)
        return super().do_GET()

    def do_POST(self):
        if urlsplit(self.path).path != "/api/annotation":
            return self._json({"error": "unsupported endpoint"}, 404)
        origin = self.headers.get("Origin")
        host = self.headers.get("Host", "")
        if not host or host.split(":")[0] not in ("127.0.0.1", "localhost") or (origin and origin not in ("http://" + host,)):
            return self._json({"error": "local same-origin requests only"}, 403)
        try:
            n = int(self.headers.get("Content-Length", "0"))
            if n <= 0 or n > 80_000:
                raise ValueError("invalid annotation payload size")
            data = json.loads(self.rfile.read(n).decode("utf-8"))
            result = store_annotation(self.server.repo_root, data)
            return self._json({"saved": True, "sample_id": result["sample_id"],
                               "status": result["review_state"], "image_sha256": result["image_sha256"]})
        except (ValueError, OSError, KeyError, json.JSONDecodeError) as exc:
            return self._json({"error": str(exc)}, 422)


def main(argv=None):
    p = argparse.ArgumentParser(description="Local manual yarn reference annotation")
    sub = p.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="serve local review interface")
    serve.add_argument("--port", type=int, default=8765)
    sub.add_parser("audit", help="list verified, draft, missing or stale references")
    args = p.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    if args.command == "audit":
        print(json.dumps(audit(root), ensure_ascii=False, indent=2))
        return 0
    server = ThreadingHTTPServer(("127.0.0.1", args.port), lambda *a, **kw:
                                 AnnotationHandler(*a, directory=str(root), **kw))
    server.repo_root = root
    print(f"Open http://127.0.0.1:{args.port}/tools/yarn_annotator/ (local only)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
