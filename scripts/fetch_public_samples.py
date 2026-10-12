#!/usr/bin/env python3
"""Download the public fabric test photographs with tracked provenance.

Source: datasets/public_samples/sources.json
Destination: datasets/public_samples/images/
Only original JPEG/MPO (multi-picture JPEG) bytes from Wikimedia Commons are used.\nAn MPO is a JPEG-compatible container: its first picture is a JPEG image.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "datasets" / "public_samples"
MANIFEST = DATASET / "sources.json"
IMAGES = DATASET / "images"
MAX_BYTES = 26 * 1024 * 1024
USER_AGENT = (
    "FabricVisionRecognition/1.0 "
    "(https://github.com/leaves899/fabric-vision-recognition; "
    "open-license research photo archiving)"
)


def fetch_one(name: str, out: Path) -> None:
    url = "https://commons.wikimedia.org/wiki/Special:FilePath/" + quote(name, safe="")
    last_error = None
    for attempt in range(3):
        try:
            req = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(req, timeout=90) as response:
                host = urlparse(response.geturl()).hostname or ""
                if host not in {"commons.wikimedia.org", "upload.wikimedia.org"}:
                    raise ValueError(f"unexpected image host: {host}")
                if "image" not in response.headers.get("Content-Type", "").lower():
                    raise ValueError(f"not an image: {response.headers.get('Content-Type')}")
                tmp = out.with_name(out.name + ".partial")
                count = 0
                with tmp.open("wb") as file:
                    while chunk := response.read(262144):
                        count += len(chunk)
                        if count > MAX_BYTES:
                            raise ValueError("image larger than 26 MiB")
                        file.write(chunk)
            with Image.open(tmp) as image:
                # An MPO has a valid JPEG first image plus MPF metadata.
                # Keeping the original bytes preserves provenance.
                if image.format not in {"JPEG", "MPO"}:
                    raise ValueError(f"unexpected format: {image.format}")
                if min(image.size) < 400:
                    raise ValueError(f"image too small for testing: {image.size}")
                image.verify()
            tmp.replace(out)
            return
        except Exception as exc:
            last_error = exc
            out.with_name(out.name + ".partial").unlink(missing_ok=True)
            if attempt < 2:
                time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"cannot download {name}: {last_error}") from last_error


def main() -> None:
    entries = json.loads(MANIFEST.read_text(encoding="utf-8"))["items"]
    rows = []
    for entry in entries:
        if entry["has_5cm_calibration_frame"] or entry["density_ground_truth"]:
            raise ValueError("public samples must not be mislabeled as calibrated")
        relative = Path(entry["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"unsafe destination: {relative}")
        dest = IMAGES / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.is_file():
            fetch_one(entry["commons_file"], dest)
        with Image.open(dest) as image:
            if image.format not in {"JPEG", "MPO"}:
                raise ValueError(f"invalid image file: {dest}")
            width, height = image.size
            image.verify()
        checksum = hashlib.sha256(dest.read_bytes()).hexdigest()
        rows.append(f"{checksum}  images/{relative.as_posix()}\n")
        print(f"{entry['id']} {width}x{height} {dest.stat().st_size} bytes {dest}")
    (DATASET / "checksums.sha256").write_text("".join(rows), encoding="utf-8")
    print(f"Downloaded/verified {len(rows)} real photographs.")


if __name__ == "__main__":
    main()
