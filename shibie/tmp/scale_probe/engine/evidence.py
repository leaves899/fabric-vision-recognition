from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np


def _image_copy(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    return image.copy()


def _draw_width_evidence(image: np.ndarray, width: dict) -> np.ndarray:
    canvas = _image_copy(image)
    colors = {"warp": (0, 200, 255), "weft": (255, 160, 0)}
    for item in width.get("evidence", [])[:160]:
        direction = item.get("direction")
        color = colors.get(direction, (0, 255, 0))
        center = tuple(int(round(v)) for v in item.get("center", (0, 0)))
        left = tuple(int(round(v)) for v in item.get("edge_left", center))
        right = tuple(int(round(v)) for v in item.get("edge_right", center))
        cv2.line(canvas, left, right, color, 2, cv2.LINE_AA)
        cv2.circle(canvas, center, 2, (255, 255, 255), -1, cv2.LINE_AA)
    return canvas


def _draw_twill_evidence(image: np.ndarray, twill: dict) -> np.ndarray:
    canvas = _image_copy(image)
    for item in twill.get("evidence", [])[:100]:
        line = item.get("line")
        if not line or len(line) != 4:
            continue
        points = tuple(int(round(v)) for v in line)
        cv2.line(canvas, points[:2], points[2:], (0, 0, 255), 2, cv2.LINE_AA)
    label = f"direction={twill.get('direction')} angle={twill.get('angle_deg')}"
    cv2.putText(canvas, label, (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 2, cv2.LINE_AA)
    return canvas


def _draw_direction_field(image: np.ndarray, orientation: dict) -> np.ndarray:
    canvas = _image_copy(image)
    samples = orientation.get("direction_field_samples", [])
    shape = orientation.get("field_shape") or [image.shape[1], image.shape[0]]
    sx = image.shape[1] / max(float(shape[0]), 1.0)
    sy = image.shape[0] / max(float(shape[1]), 1.0)
    for item in samples:
        angle = np.deg2rad(float(item.get("angle_deg", 0.0)))
        length = 8.0 + 10.0 * float(np.clip(item.get("coherence", 0.0), 0.0, 1.0))
        x, y = float(item.get("x", 0.0)) * sx, float(item.get("y", 0.0)) * sy
        dx, dy = np.cos(angle) * length, np.sin(angle) * length
        cv2.line(canvas, (int(x - dx), int(y - dy)), (int(x + dx), int(y + dy)), (0, 255, 0), 1, cv2.LINE_AA)
    return canvas


def _draw_centerlines(image: np.ndarray, centerlines: dict) -> np.ndarray:
    canvas = _image_copy(image)
    for key, color in (("warp", (0, 200, 255)), ("weft", (255, 160, 0))):
        for line in centerlines.get(key, [])[:80]:
            points = np.asarray(line, dtype=np.float32)
            if len(points) < 2:
                continue
            cv2.polylines(canvas, [np.round(points).astype(np.int32)], False, color, 1, cv2.LINE_AA)
    return canvas


def _draw_weave_matrix(matrix: list[list[int]] | None, path: Path) -> bool:
    if not matrix:
        return False
    values = np.asarray(matrix, dtype=np.int8)
    height, width = values.shape[:2]
    cell = 42
    canvas = np.full((height * cell, width * cell, 3), 255, dtype=np.uint8)
    for row in range(height):
        for column in range(width):
            value = int(values[row, column])
            color = (60, 170, 60) if value > 0 else ((60, 60, 210) if value < 0 else (180, 180, 180))
            top_left = (column * cell, row * cell)
            bottom_right = ((column + 1) * cell - 1, (row + 1) * cell - 1)
            cv2.rectangle(canvas, top_left, bottom_right, color, -1)
            cv2.putText(canvas, "+" if value > 0 else ("-" if value < 0 else "?"), (top_left[0] + 13, top_left[1] + 29), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 255), 2, cv2.LINE_AA)
    cv2.imwrite(str(path), canvas)
    return True


def generate_evidence(
    front: np.ndarray,
    measurement: dict,
    output_dir: str | Path,
    sample_id: str = "sample",
) -> dict:
    """Render report evidence from existing Measurement JSON without re-analysis."""
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    twill = measurement.get("twill") or {}
    width = measurement.get("apparent_width") or {}
    files: dict[str, str] = {}

    width_path = root / f"{sample_id}_width.png"
    cv2.imwrite(str(width_path), _draw_width_evidence(front, width))
    files["width"] = str(width_path)

    twill_path = root / f"{sample_id}_twill.png"
    cv2.imwrite(str(twill_path), _draw_twill_evidence(front, twill))
    files["twill"] = str(twill_path)

    direction_path = root / f"{sample_id}_direction_field.png"
    cv2.imwrite(str(direction_path), _draw_direction_field(front, measurement.get("orientation") or {}))
    files["direction_field"] = str(direction_path)

    centerline_path = root / f"{sample_id}_centerlines.png"
    cv2.imwrite(str(centerline_path), _draw_centerlines(front, measurement.get("centerline_evidence") or {}))
    files["centerlines"] = str(centerline_path)

    weave = twill.get("interlacing_topology") or {}
    matrix = (weave.get("weave_evidence") or {}).get("float_matrix")
    if matrix:
        matrix_path = root / f"{sample_id}_weave_matrix.png"
        if _draw_weave_matrix(matrix, matrix_path):
            files["weave_matrix"] = str(matrix_path)

    index = {
        "sample_id": sample_id,
        "status": "PASS" if files else "FAIL",
        "files": files,
        "statuses": {
            "width": width.get("status"),
            "direction": twill.get("direction_status"),
            "angle": twill.get("angle_status"),
            "weave": twill.get("weave_status"),
        },
        "measurement_reference": {
            "engine_version": measurement.get("engine_version"),
            "algorithm_profile": measurement.get("algorithm_profile"),
        },
        "not_rendered": ["fft_or_autocorrelation_plot"],
    }
    index_path = root / f"{sample_id}_evidence.json"
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    files["index"] = str(index_path)
    return index
