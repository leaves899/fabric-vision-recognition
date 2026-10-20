from __future__ import annotations
"""Frozen-pair A/B comparison for integer vs fractional pitch on native 8k.

All image-only inference finishes before truth.json is opened. An F1 score
here is an independent mid-cross-section proxy, NOT full yarn ID continuity.
"""
import argparse
import json
import resource
import time
from pathlib import Path
import cv2
import numpy as np
from engine.multiwindow_pitch import PitchSettings, detect_calibration_frame, frame_windows, analyze_pitch_window
from engine.local_axis_rectification import estimate_fabric_axis_from_frame, adjusted_window_homography
from engine.physical_center_validation import validate_physical_centers
from engine.subpixel_physical_phase import validate_centers_fractional
from run_local_axis_experiment import raw_gt_projected, score_centers


def _overlay(patch, family, locations, rgb):
    dest = patch.copy()
    n = dest.shape[0]
    for x in locations:
        k = int(round(float(x)))
        if family == "warp":
            cv2.line(dest, (k, 0), (k, n-1), rgb, 1, cv2.LINE_AA)
        else:
            cv2.line(dest, (0, k), (n-1, k), rgb, 1, cv2.LINE_AA)
    return dest


def evaluate(case: str):
    start = time.perf_counter()
    out = Path("experiments/shibie-8k-capture-multiwindow/subpixel") / case
    out.mkdir(parents=True, exist_ok=True)
    image_path = Path("experiments/shibie-8k-capture-multiwindow/stress") / case
    r = cv2.imread(str(image_path / "reflection_8000x6000.jpg"))
    t = cv2.imread(str(image_path / "transmission_8000x6000.jpg"))
    if r is None or t is None or r.shape != (6000, 8000, 3) or t.shape != r.shape:
        raise RuntimeError("NATIVE_8K_PAIR_REQUIRED")
    frame = detect_calibration_frame(r)
    if frame.get("status") != "PASS":
        raise RuntimeError("FRAME_REQUIRED: " + json.dumps(frame))
    settings = PitchSettings()
    pose = estimate_fabric_axis_from_frame(r, t, frame, settings)
    if pose["status"] == "UNDETERMINED":
        raise RuntimeError("INDETERMINATE_AXIS: " + json.dumps(pose))
    rows = []
    center_patches = {}
    for i, j, H in frame_windows(frame, settings.grid, settings.window_size_px):
        transform = adjusted_window_homography(H, pose["image_rotation_deg"], 640, 520)
        rr = cv2.warpPerspective(r, transform, (520, 520))
        tt = cv2.warpPerspective(t, transform, (520, 520))
        pitch = analyze_pitch_window(rr, tt, settings)
        if (i, j) == (1, 1):
            center_patches = {"R": rr, "T": tt}
        for family in ("warp", "weft"):
            candidates = pitch[family]["candidates"]
            guess = candidates[0]["pitch_px"] if candidates else None
            before = validate_physical_centers(rr, tt, family, guess)
            after = validate_centers_fractional(rr, tt, family, guess)
            rows.append({"grid": [i, j], "family": family, "raw_to_tile": transform.tolist(),
                         "pitch_initial": guess, "old": before, "new": after})
    # The hidden synthetic physical labels are first read here, AFTER both paths.
    gt = json.loads((image_path / "truth.json").read_text(encoding="utf-8"))
    results = {}
    for family in ("warp", "weft"):
        cases = []
        for item in rows:
            if item["family"] != family:
                continue
            truth = raw_gt_projected(gt, family, np.asarray(item["raw_to_tile"], np.float64), 520)
            scores = {}
            for key in ("old", "new"):
                data = item[key]
                coords = data.get("center_positions_px", []) if data.get("status") == "PASS" else []
                scores[key] = score_centers(coords, truth, gt["true_pitch_px_canonical"][family])
            item["truth_assessment_only"] = scores
            cases.append(item)
        results[family] = {
            "old_f1_proxy": round(float(np.mean([q["truth_assessment_only"]["old"]["f1_proxy"] for q in cases])), 4),
            "new_f1_proxy": round(float(np.mean([q["truth_assessment_only"]["new"]["f1_proxy"] for q in cases])), 4),
            "old_pass_windows": sum(q["old"]["status"] == "PASS" for q in cases),
            "new_pass_windows": sum(q["new"]["status"] == "PASS" for q in cases),
            "new_period_mape": round(float(np.mean([
               abs(q["new"].get("pitch_px",0)-gt["true_pitch_px_canonical"][family])
               / gt["true_pitch_px_canonical"][family]
               for q in cases])), 4),
            "failure_reasons_new": [q["new"].get("reason") for q in cases if q["new"]["status"] != "PASS"]
        }
    # Program-derived overlays, never regenerated or substituted from truth.
    if center_patches:
        panels = [center_patches["R"], center_patches["T"]]
        M = next(q["raw_to_tile"] for q in rows if q["grid"] == [1, 1])
        M = np.asarray(M, dtype=np.float64)
        for family in ("warp", "weft"):
            item = next(q for q in rows if q["grid"] == [1, 1] and q["family"] == family)
            truth = raw_gt_projected(gt, family, M, 520)
            panels.append(_overlay(center_patches["T"], family, truth, (255, 50, 190)))
            for name in ("old", "new"):
                q = item[name]
                coords = q.get("center_positions_px", []) if q["status"] == "PASS" else []
                panels.append(_overlay(center_patches["T"], family, coords, (30, 50, 250)))
        labels = ["Reflection", "Transmission", "Truth warp", "Old warp", "New warp",
                  "Truth weft", "Old weft", "New weft"]
        canvas = np.full((1040, 2080, 3), 230, dtype=np.uint8)
        for index, (panel, label) in enumerate(zip(panels, labels)):
            y, x = divmod(index, 4)
            canvas[y*520:(y+1)*520, x*520:(x+1)*520] = panel
            cv2.rectangle(canvas, (x*520,y*520), (x*520+195,y*520+30), (255,255,255), -1)
            cv2.putText(canvas,label,(x*520+9,y*520+22),
                cv2.FONT_HERSHEY_SIMPLEX,.62,(0,0,0),2,cv2.LINE_AA)
        cv2.imwrite(str(out / "real_algorithm_visual_comparison.jpg"), canvas,
                    [cv2.IMWRITE_JPEG_QUALITY, 82])
    report = {"case": case, "capture_shape": [8000,6000],
              "pose_from_pixels_only": pose,
              "truth_pose_deg_EVALUATION_ONLY": gt["source_scene"].get("fabric_rotation_deg"),
              "input_sha256": gt["sha256"],
              "results": results, "windows": rows,
              "runtime_seconds": round(time.perf_counter()-start, 2),
              "peak_rss_mib": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024., 1),
              "limitations": ["SYNTHETIC_NOT_REAL_CAPTURE",
                              "LOCAL_MIDSECTION_PROXY_NOT_YARN_ID_F1",
                              "SAME_IMAGE_AND_GT_FOR_OLD_AND_NEW"]}
    (out / "comparison.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("SUBPIXEL_RESULT " + json.dumps({"case":case,"pose":pose["image_rotation_deg"],
          "results":results,"runtime_seconds":report["runtime_seconds"],
          "peak_rss_mib":report["peak_rss_mib"]},ensure_ascii=False), flush=True)
    return results


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--case", required=True)
    args = p.parse_args()
    evaluate(args.case)
