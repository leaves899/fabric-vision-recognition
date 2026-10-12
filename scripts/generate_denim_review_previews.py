#!/usr/bin/env python3
"""Generate compact visual-review thumbnails for denim candidate images.

Visual review assets do not replace or modify original source photos.
"""
from __future__ import annotations

import json
from pathlib import Path
from PIL import Image, ImageOps, ImageDraw

BASE = Path(__file__).resolve().parents[1] / "datasets" / "public_samples"
TARGETS = ["T001", "T004", "T005", "T006", "T007"] + [f"D{i:03d}" for i in range(1, 22)]
OUT = BASE / "review_previews"
OUT.mkdir(parents=True, exist_ok=True)
items = json.loads((BASE / "sources.json").read_text(encoding="utf-8"))["items"]
lookup = {item["id"]: item for item in items}

for sample_id in TARGETS:
    sample = lookup[sample_id]
    source = BASE / "images" / sample["path"]
    with Image.open(source) as original:
        image = ImageOps.exif_transpose(original).convert("RGB")
        image.thumbnail((590, 460))
        sheet = Image.new("RGB", (610, 500), "#ffffff")
        sheet.paste(image, ((610-image.width)//2, (460-image.height)//2))
        draw = ImageDraw.Draw(sheet)
        draw.text((14, 472), f"{sample_id} - {sample['commons_file'][:65]}", fill="black")
        target = OUT / (sample_id + ".jpg")
        for quality in (55, 43, 33, 23, 14):
            sheet.save(target, "JPEG", quality=quality, optimize=True)
            if target.stat().st_size < 69000:
                break
        if target.stat().st_size >= 69000:
            raise ValueError(f"preview too large for connector: {target}")
        print(f"{target.name}: {target.stat().st_size} bytes")
