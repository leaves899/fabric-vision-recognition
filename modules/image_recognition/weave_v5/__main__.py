"""Run as: python -m modules.image_recognition.weave_v5 --image ... --out ..."""
import argparse
import json
from pathlib import Path
from .run_photo_weave_v5 import run

def main():
    parser=argparse.ArgumentParser(description="Fabric weave V5 candidate detector")
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--rois", type=int, choices=[1,3], default=3)
    opts=parser.parse_args()
    result=run(opts.image, opts.out, opts.rois)
    print(json.dumps(result["summary"],ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()
