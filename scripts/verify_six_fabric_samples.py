#!/usr/bin/env python3
"""Validate six user-contributed visual annotations and optional image files.

No physical-yarn truth is inferred. Missing images are a warning by default,
or a failure with --require-images.
"""
import argparse
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/"datasets/user_contributed/2026-10-13-six-fabric-images"

def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--require-images",action="store_true")
    args=parser.parse_args()
    data=json.loads((BASE/"visual_drafts.json").read_text(encoding="utf-8"))
    assert len(data["samples"])==6
    missing=[]
    for sample in data["samples"]:
        sid=sample["sample_id"]
        w,h=sample["resolution_px"]
        x1,y1,x2,y2=sample["roi_xyxy"]
        assert 0 <= x1 < x2 <= w and 0 <= y1 < y2 <= h,sid
        assert sample["confirmed_yarn_axis_deg"] is None if "confirmed_yarn_axis_deg" in sample else True
        assert sample["warp_density_per_cm"] is None and sample["weft_density_per_cm"] is None
        assert sample["status"] == "VISUAL_REVIEW_ONLY_NOT_GROUND_TRUTH"
        for flo in sample["visible_local_float_candidates"]:
            a,b,c,d=flo["bbox_xyxy"]
            assert 0 <= a < c <= w and 0 <= b < d <= h
            assert flo["physical_yarn_id"] is None
        file=BASE/sample["expected_original_path"]
        if not file.is_file():
            missing.append(sid)
            print(f"PENDING_BINARY_IMPORT: {sid} -> {file}")
            continue
        sha=hashlib.sha256(file.read_bytes()).hexdigest()
        if sha!=sample["original_sha256"]:
            raise ValueError(f"{sid}: source JPG SHA-256 mismatch")
        print(f"VERIFIED: {sid} source bytes match")
    print(f"Metadata: {len(data['samples'])}/6; original JPGs present: {6-len(missing)}/6")
    if args.require_images and missing:
        print("ERROR: GitHub cannot be claimed to contain the complete original images.")
        return 2
    return 0

if __name__=="__main__":
    raise SystemExit(main())
