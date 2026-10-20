from __future__ import annotations

import argparse
import csv
from pathlib import Path

import cv2

from engine.pipeline import run_measurement


def percentile_values(direction: dict | None) -> tuple[object, object, object, object]:
    if not direction:
        return None, None, None, None
    return (
        direction.get("valid_sample_count"),
        direction.get("p10_px"),
        direction.get("p50_px"),
        direction.get("p90_px"),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run FabricNET single-image width PoC validation.")
    parser.add_argument("--images", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mm-per-px-x", type=float, required=True)
    parser.add_argument("--mm-per-px-y", type=float, required=True)
    parser.add_argument("--warp-axis-hint", choices=("vertical", "horizontal"), default="vertical")
    parser.add_argument("--start", type=int, default=1, help="One-based position in sorted images.")
    parser.add_argument("--end", type=int, help="Inclusive position in sorted images.")
    parser.add_argument("--append", action="store_true", help="Append rows to an existing CSV.")
    args = parser.parse_args()

    images = sorted(args.images.glob("W*.jpg"))
    if not images:
        raise SystemExit("NO_W_JPG_IMAGES_FOUND")
    end = args.end or len(images)
    if args.start < 1 or end < args.start or end > len(images):
        raise SystemExit("INVALID_IMAGE_RANGE")
    selected_images = images[args.start - 1:end]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "image", "input_mode", "warp_axis_hint", "mm_per_px_x", "mm_per_px_y",
        "density_status", "warp_density_per_cm", "weft_density_per_cm", "width_status",
        "warp_valid_samples", "warp_p10_px", "warp_p50_px", "warp_p90_px",
        "weft_valid_samples", "weft_p10_px", "weft_p50_px", "weft_p90_px",
        "width_reasons",
    ]
    mode = "a" if args.append else "w"
    with args.output.open(mode, newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=columns)
        if not args.append:
            writer.writeheader()
        for index, image_path in enumerate(selected_images, start=args.start):
            image = cv2.imread(str(image_path))
            ok, encoded = cv2.imencode(".jpg", image)
            if not ok:
                raise ValueError(f"IMAGE_ENCODE_FAILED:{image_path.name}")
            result = run_measurement(
                encoded.tobytes(), encoded.tobytes(),
                mm_per_px_x=args.mm_per_px_x,
                mm_per_px_y=args.mm_per_px_y,
                warp_axis_hint=args.warp_axis_hint,
            )
            width = result.get("apparent_width", {})
            warp_n, warp_p10, warp_p50, warp_p90 = percentile_values(width.get("warp"))
            weft_n, weft_p10, weft_p50, weft_p90 = percentile_values(width.get("weft"))
            writer.writerow({
                "image": image_path.name,
                "input_mode": "SINGLE_IMAGE_DUPLICATED_PSEUDO_REFLECTION_TRANSMISSION_POC",
                "warp_axis_hint": args.warp_axis_hint,
                "mm_per_px_x": args.mm_per_px_x,
                "mm_per_px_y": args.mm_per_px_y,
                "density_status": result.get("status"),
                "warp_density_per_cm": result.get("warp_density_per_cm"),
                "weft_density_per_cm": result.get("weft_density_per_cm"),
                "width_status": width.get("status"),
                "warp_valid_samples": warp_n,
                "warp_p10_px": warp_p10,
                "warp_p50_px": warp_p50,
                "warp_p90_px": warp_p90,
                "weft_valid_samples": weft_n,
                "weft_p10_px": weft_p10,
                "weft_p50_px": weft_p50,
                "weft_p90_px": weft_p90,
                "width_reasons": "|".join(width.get("reasons", [])),
            })
            print(f"[{index}/{len(images)}] {image_path.name}: {width.get('status', 'FAIL')}", flush=True)


if __name__ == "__main__":
    main()
