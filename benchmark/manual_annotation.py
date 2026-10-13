"""Local-only operator annotation service.

U20261013 PHYSICAL_YARN_REFERENCE labels denote REAL PHYSICAL YARNS,
possibly across occlusion: they are NOT necessarily visible yarn segments and
are NOT verified per-pixel centerline ground truth. Two clicked points provide
a direction and an approximate inferred path. User-reviewed yarn identity
within a family must not be conflated with WARP/WEFT identification.
The service never invents yarn lines, class identity, weave or density.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import threading
import time
import webbrowser
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from benchmark.dataset import MANIFEST_FIELDS, load_csv, resolve_local

DEFAULT_FOLDER = Path("datasets/annotations/drafts")
MODES = {"DRAFT", "OPERATOR_REVIEWED"}
ELIGIBILITY = {"UNREVIEWED", "DENIM_CANDIDATE", "NEGATIVE_NON_DENIM", "UNCERTAIN"}
FAMILIES = {"UNKNOWN", "WARP", "WEFT"}
SEGMENTS = ("reference", "check_same", "holdout_same", "check_cross", "check_cross_second")
# A physical-yarn trajectory is a connected strand inferred through possible
# occlusions; the full two-point line need not correspond to visible pixels.
ANNOTATION_TARGETS = {"PHYSICAL_YARN_REFERENCE", "VISIBLE_YARN_SEGMENT",
                      "DIRECTION_ONLY", "UNSPECIFIED"}
SIX_FABRIC_PREFIX = "U20261013_"


def annotation_target_for(sid: str, requested=None) -> str:
    # Read old JSON labels without forcing the user to re-annotate.
    if requested == "PHYSICAL_YARN_TRAJECTORY":
        requested = "PHYSICAL_YARN_REFERENCE"
    if requested is None:
        # Retain compatibility with old annotation files, but make the
        # new interpretation explicit in validate_annotation() return values.
        requested = ("PHYSICAL_YARN_REFERENCE"
                     if str(sid).startswith(SIX_FABRIC_PREFIX) else "UNSPECIFIED")
    if requested not in ANNOTATION_TARGETS:
        raise ValueError("unsupported annotation_target")
    if str(sid).startswith(SIX_FABRIC_PREFIX) and requested != "PHYSICAL_YARN_REFERENCE":
        raise ValueError("six-fabric reviewed annotations mean PHYSICAL_YARN_REFERENCE")
    return requested



def samples(root: Path) -> dict[str, dict]:
    items = load_csv(root / "datasets/manifest.csv", MANIFEST_FIELDS)
    return {item["position_id"]: item for item in items if item["capture_mode"] in {"PUBLIC_UNKNOWN", "PHONE_UNKNOWN_LIGHTING"}}


def image_stats(root: Path, row: dict) -> tuple[str, tuple[int, int]]:
    """Pillow uses display-oriented EXIF dimensions; image bytes remain unchanged."""
    from PIL import Image, ImageOps
    image = resolve_local(root, row["image_path"])
    checksum = hashlib.sha256(image.read_bytes()).hexdigest()
    with Image.open(image) as data:
        size = ImageOps.exif_transpose(data).size
    return checksum, size


def _zoom_review_provenance(root: Path, row: dict, image_sha256: str,
                            image_size: tuple[int, int]) -> dict:
    """Bind six zoom-native manual annotations to the immutable source crop.

    Legacy/public photos continue to use their registered image directly.
    """
    sid = row["position_id"]
    if not sid.startswith("U20261013_"):
        return {}
    if sid not in {f"U20261013_{index:02d}" for index in range(1, 7)}:
        return {}
    prefix = Path("datasets/user_contributed/2026-10-13-six-fabric-images")
    provenance_file = root / prefix / "image_provenance.json"
    provenance = json.loads(provenance_file.read_text(encoding="utf-8"))
    image = next((item for item in provenance["images"]
                  if item["sample_id"] == sid), None)
    if image is None:
        raise ValueError("missing zoom photo provenance")
    expected = (prefix / image["zoom"]).as_posix()
    if row["image_path"] != expected:
        raise ValueError("manual reference must be on registered unmarked 2x zoom photo")
    if image_sha256 != image["zoom_sha256"]:
        raise ValueError("zoom photo hash changed; manual annotations would be stale")
    original_path = prefix / image["original"]
    if hashlib.sha256((root / original_path).read_bytes()).hexdigest() != image["original_sha256"]:
        raise ValueError("original photo hash changed")
    x0, y0, x1, y1 = image["crop_original_xyxy"]
    scale = image["enlargement_scale"]
    if not isinstance(scale, int) or scale != 2:
        raise ValueError("unsupported enlargement scale")
    if image_size != ((x1 - x0) * scale, (y1 - y0) * scale):
        raise ValueError("zoom dimensions inconsistent with original crop")
    return {
        "annotation_image_kind": "UNMARKED_2X_CENTER_CROP",
        "coordinate_space": "ZOOM_2X_NATIVE_PIXELS",
        "original_image_path": original_path.as_posix(),
        "original_image_sha256": image["original_sha256"],
        "crop_original_xyxy": [x0, y0, x1, y1],
        "enlargement_scale": scale,
    }


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
    review_provenance = _zoom_review_provenance(root, row, checksum, (width, height))
    supplied = data.get("image_sha256")
    if supplied not in (None, "", checksum):
        raise ValueError("image hash changed since annotation; review coordinates")
    eligibility = data.get("eligibility", "UNREVIEWED")
    review_state = data.get("review_state", "DRAFT")
    family = data.get("reference_family", "UNKNOWN")
    annotation_target = annotation_target_for(sid, data.get("annotation_target"))
    supplied_semantics = data.get("annotation_semantics")
    if supplied_semantics not in (None, "", annotation_target, "PHYSICAL_YARN_TRAJECTORY"):
        raise ValueError("annotation_semantics conflicts with annotation_target")
    if supplied_semantics == "PHYSICAL_YARN_TRAJECTORY" and annotation_target != "PHYSICAL_YARN_REFERENCE":
        raise ValueError("invalid legacy physical yarn reference")
    if data.get("visible_pixel_gt_confirmed") is True and annotation_target != "VISIBLE_YARN_SEGMENT":
        raise ValueError("inferred physical yarn trajectory is not visible pixel ground truth")
    if data.get("centerline_pixel_gt_confirmed") is True and annotation_target == "PHYSICAL_YARN_REFERENCE":
        raise ValueError("inferred physical yarn path is not precise pixel centerline ground truth")

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
    # Distinct roles are distinct REAL physical yarns, not portions of one yarn.
    # Reject both identical and reverse-endpoint duplicate clicks.
    roles = (("reference","check_same","holdout_same"),
             ("check_cross","check_cross_second"))
    for family_roles in roles:
        for i, first in enumerate(family_roles):
            for second in family_roles[i+1:]:
                x, y = normalized[first], normalized[second]
                if x is not None and y is not None and (x == y or x == y[::-1]):
                    raise ValueError(f"{second} must denote a DIFFERENT physical yarn than {first}")
    if review_state == "OPERATOR_REVIEWED" and not confirmed:
        raise ValueError("reviewed reference needs explicit operator confirmation")
    if normalized["check_same"] == normalized["reference"] and normalized["reference"] is not None:
        raise ValueError("check_same must be a DIFFERENT segment, not the V5 input reference")
    if normalized["check_cross"] == normalized["reference"] and normalized["reference"] is not None:
        raise ValueError("check_cross must be a DIFFERENT segment")
    # Holdout yarn MUST NOT duplicate either input/calibration segment.
    if normalized["holdout_same"] is not None:
        for used in ("reference", "check_same"):
            if normalized["holdout_same"] == normalized[used]:
                raise ValueError("holdout_same must differ from all calibration segments")
    if normalized["check_cross_second"] is not None and normalized["check_cross_second"] == normalized["check_cross"]:
        raise ValueError("check_cross_second must differ from check_cross")
    if family != "UNKNOWN" and not data.get("identity_confirmed") is True:
        raise ValueError("warp/weft physical identity requires an explicit confirmation")
    if eligibility == "NEGATIVE_NON_DENIM" and review_state == "OPERATOR_REVIEWED":
        raise ValueError("non-denim negatives must remain outside the primary denim benchmark")
    # Exact physical yarn-to-yarn interval counts are optional, but must be
    # explicitly human-verified before candidate lines may be deduplicated.
    counts={}
    for key, required in (("same_family",("reference","check_same")),
                          ("cross_family",("check_cross","check_cross_second"))):
        value=data.get(key+"_intervals")
        consent=data.get(key+"_intervals_confirmed",False)
        if value in ("",None):
            value=None
        if value is not None and (isinstance(value,bool) or not isinstance(value,int) or not 1<=value<=200):
            raise ValueError(key+" yarn intervals must be integer 1..200")
        if consent is not True and value is not None:
            raise ValueError(key+" yarn intervals require operator confirmation")
        if consent is True and value is None:
            raise ValueError(key+" confirmed intervals must have a count")
        if value is not None and any(normalized[x] is None for x in required):
            raise ValueError(key+" confirmed intervals require both real yarn segments")
        counts[key+"_intervals"]=value
        counts[key+"_intervals_confirmed"]=(consent is True)
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
        "segments": normalized, **counts, "notes": notes.strip(),
        "annotation_target": annotation_target,
        "annotation_semantics": annotation_target,
        "physical_yarn_role_groups": {"A":["reference","check_same","holdout_same"],
                                      "B":["check_cross","check_cross_second"]}
            if annotation_target == "PHYSICAL_YARN_REFERENCE" else {},
        "path_may_cross_occlusion": annotation_target == "PHYSICAL_YARN_REFERENCE",
        "visible_pixel_gt_confirmed": False if annotation_target != "VISIBLE_YARN_SEGMENT"
            else data.get("visible_pixel_gt_confirmed") is True,
        "centerline_pixel_gt_confirmed": False if annotation_target == "PHYSICAL_YARN_REFERENCE"
            else data.get("centerline_pixel_gt_confirmed") is True,
        **review_provenance,
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
        "warning": "PHYSICAL_YARN_REFERENCE denotes a distinct real yarn per path through possible occlusions; NOT a visible pixel mask. A1/A2 calibrate, A3 is held out; warp/weft identity and cm density unconfirmed.",
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
        if path.path == "/api/local-review-capabilities":
            from benchmark.local_image_review import (
                LOCAL_REVIEW_PROTOCOL_VERSION, SUPPORTED_LINE_KINDS, SOURCE)
            return self._json({
                "protocol_version": LOCAL_REVIEW_PROTOCOL_VERSION,
                "supported_line_kinds": list(SUPPORTED_LINE_KINDS),
                "annotation_source": SOURCE,
                "save_endpoint": "/api/local-review",
                "restart_required_after_python_update": True,
            })
        if path.path == "/api/local-review":
            from benchmark.local_image_review import load_local_review
            sid = parse_qs(path.query).get("id", [""])[0]
            try:
                return self._json(load_local_review(root, sid))
            except (ValueError, OSError, KeyError, json.JSONDecodeError) as exc:
                return self._json({"error": str(exc)}, 404)
        if path.path == "/api/local-review-audit":
            from benchmark.local_image_review import audit_local_reviews
            return self._json(audit_local_reviews(root))
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
        endpoint = urlsplit(self.path).path
        if endpoint not in ("/api/annotation", "/api/local-review"):
            return self._json({"error": "unsupported endpoint"}, 404)
        origin = self.headers.get("Origin")
        host = self.headers.get("Host", "")
        if not host or host.split(":")[0] not in ("127.0.0.1", "localhost") or (origin and origin not in ("http://" + host,)):
            return self._json({"error": "local same-origin requests only"}, 403)
        try:
            n = int(self.headers.get("Content-Length", "0"))
            limit = 1_000_000 if endpoint == "/api/local-review" else 80_000
            if n <= 0 or n > limit:
                raise ValueError("invalid annotation payload size")
            data = json.loads(self.rfile.read(n).decode("utf-8"))
            if endpoint == "/api/local-review":
                from benchmark.local_image_review import store_local_review, FOLDER
                result = store_local_review(self.server.repo_root, data)
                return self._json({
                    "saved": True, "sample_id": result["sample_id"],
                    "status": result["review_state"], "image_sha256": result["image_sha256"],
                    "path": str(FOLDER / (result["sample_id"] + ".json")).replace("\\", "/"),
                    "regions": len(result["regions"]), "relations": len(result["relations"]),
                    "independent_physical_gt": False})
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
    serve.add_argument("--open", action="store_true", help="open the local browser after server starts")
    sub.add_parser("audit", help="list verified, draft, missing or stale references")
    args = p.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    if args.command == "audit":
        from benchmark.local_image_review import audit_local_reviews
        report = audit(root)
        # Keep legacy top-level audit keys for existing callers.
        report["phone_image_local_reviews"] = audit_local_reviews(root)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    server = ThreadingHTTPServer(("127.0.0.1", args.port), lambda *a, **kw:
                                 AnnotationHandler(*a, directory=str(root), **kw))
    server.repo_root = root
    url = f"http://127.0.0.1:{server.server_address[1]}/tools/yarn_annotator/"
    print(f"Open {url} (local only)")
    if args.open:
        # Start serving before asking the default browser to load the UI.
        def _open_local_browser():
            time.sleep(0.6)
            webbrowser.open(url)
        threading.Thread(target=_open_local_browser, daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
