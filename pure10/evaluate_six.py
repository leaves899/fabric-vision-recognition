"""Six-fabric, leave-one-fabric-out-compatible EVALUATION (never inference).

User two-point marks are full physical-yarn reference trajectories, not fragments.
reference/check_same/holdout_same are DISTINCT physical yarns in ONE family.
check_cross/check_cross_second are two DISTINCT yarns in the other family.
Marker separation may span multiple yarns; divide by *_family_intervals.
This script NEVER passes marks, counts, or angles to pure10.engine.analyze.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import cv2
import numpy as np

from pure10.engine import analyze, _axis_error
from pure10.spectral_direction import estimate_axes

ROOT = Path(__file__).resolve().parents[1]
GLOB = "U20261013_*.json"


def _line_angle(ends):
    (x1, y1), (x2, y2) = ends
    return float(math.degrees(math.atan2(y2-y1, x2-x1)) % 180)


def _mean_axis(angles):
    theta = np.radians(np.array(angles)*2)
    return float((math.degrees(math.atan2(np.sin(theta).mean(),
                   np.cos(theta).mean()))/2) % 180)


def _spacing(line_a, line_b, intervals):
    if not isinstance(intervals, int) or intervals < 1:
        return None
    la = np.asarray(line_a, float)
    lb = np.asarray(line_b, float)
    u = la[1]-la[0]
    u /= max(np.linalg.norm(u),1e-9)
    normal = np.array([-u[1], u[0]])
    # Distance normal to the source physical yarn, not Euclidean endpoints.
    return float(abs((lb.mean(axis=0)-la.mean(axis=0)) @ normal)/intervals)


def _validate_annotation(ann, actual):
    if ann.get("image_path") != actual.as_posix().removeprefix(ROOT.as_posix()+"/"):
        raise AssertionError("annotation points do not refer to input image")
    digest = hashlib.sha256(actual.read_bytes()).hexdigest()
    if digest != ann["image_sha256"]:
        raise AssertionError("image SHA mismatch; never score stale zoom coordinates")
    im = cv2.imread(str(actual))
    if im is None:
        raise AssertionError("unreadable latest image")
    if [im.shape[1], im.shape[0]] != [ann["image_width"], ann["image_height"]]:
        raise AssertionError("native annotation coordinate system mismatch")


def _compare(out, ann, dims):
    seg = ann["segments"]
    fa = [seg.get(k) for k in ("reference","check_same","holdout_same")]
    fb = [seg.get(k) for k in ("check_cross","check_cross_second")]
    if fa[0] is None or fa[1] is None:
        return {"score_state":"MISSING_REFERENCE"}
    angle_a = _mean_axis([_line_angle(v) for v in fa if v])
    angle_b = (_mean_axis([_line_angle(v) for v in fb if v])
               if all(fb) else None)
    obs = out["axis_families"]
    permutations = (("a", "b"), ("b","a"))
    assignments = []
    for candidate_a, candidate_b in permutations:
        error_a = _axis_error(obs[candidate_a]["angle_image_deg"], angle_a)
        error_b = (_axis_error(obs[candidate_b]["angle_image_deg"], angle_b)
                   if angle_b is not None else 0.)
        assignments.append((error_a + error_b, (candidate_a, candidate_b)))
    error, chosen = min(assignments, key=lambda item: item[0])
    x, y = chosen
    # Algorithm's period measured on downsampled input, annotations on native
    # zoom pixels. Do not accidentally treat 2x enlargement as new resolution.
    sample_scale = min(1., 840/max(dims))
    def pred(f):
        p = obs[f]["period_px"]
        return None if p is None else float(p)/sample_scale
    def discrepancy(got, wanted):
        if got is None or wanted is None or wanted <= 0:
            return None
        return round(abs(got-wanted)/wanted*100,2)
    gt_a = _spacing(fa[0],fa[1],ann.get("same_family_intervals")) \
        if ann.get("same_family_intervals_confirmed") else None
    gt_b = _spacing(fb[0],fb[1],ann.get("cross_family_intervals")) \
        if all(fb) and ann.get("cross_family_intervals_confirmed") else None
    has_holdout = bool(len(fa) > 2 and fa[2])
    return {
        "score_state":"EVALUATED",
        "annotation_interpretation":"each line = distinct full physical yarn",
        "same_family_intervals":ann.get("same_family_intervals"),
        "cross_family_intervals":ann.get("cross_family_intervals"),
        "matching_family_a_to_prediction":x,
        "reference_angle_deg":round(angle_a,3),
        "cross_angle_deg":round(angle_b,3) if angle_b is not None else None,
        "pred_reference_angle_deg":obs[x]["angle_image_deg"],
        "pred_cross_angle_deg":obs[y]["angle_image_deg"],
        "reference_angle_error_deg":round(_axis_error(
             obs[x]["angle_image_deg"],angle_a),3),
        "cross_angle_error_deg":round(_axis_error(
             obs[y]["angle_image_deg"],angle_b),3) if angle_b is not None else None,
        "angle_pair_total_error_deg":round(error,3),
        "true_same_yarn_pitch_native_px":round(gt_a,3) if gt_a is not None else None,
        "pred_same_yarn_pitch_native_px":round(pred(x),3) if pred(x) else None,
        "same_yarn_pitch_relative_error_pct":discrepancy(pred(x),gt_a),
        "true_cross_yarn_pitch_native_px":round(gt_b,3) if gt_b is not None else None,
        "pred_cross_yarn_pitch_native_px":round(pred(y),3) if pred(y) else None,
        "cross_yarn_pitch_relative_error_pct":discrepancy(pred(y),gt_b),
        "holdout_distinct_yarn_not_interpolated":has_holdout,
        "period_has_physical_single_yarn_proof":False,
        "source_operator_reviewed":bool(ann.get("reference_confirmed")),
    }


def evaluate(root=ROOT, output=None, overlays=None):
    root = Path(root)
    base = root/"datasets/annotations/drafts"
    annotated = sorted(base.glob(GLOB))
    images = sorted((root/"datasets/user_contributed/2026-10-13-six-fabric-images/zoom_unmarked").glob("U20261013_*.jpg"))
    if not images:
        raise FileNotFoundError("Latest six GitHub zoom JPGs absent; checkout may be incomplete")
    ann_map = {f.stem:f for f in annotated}
    rows = []
    for image in images:
        sample_id = image.stem.replace("_center_2x", "")
        ann_file = ann_map.get(sample_id)
        rel = image.relative_to(root)
        overlay = Path(overlays)/f"{sample_id}_candidate.png" if overlays else None
        result = analyze(image, evidence_path=overlay)
        src_image = cv2.imread(str(image))
        baseline_theta = result["cross_scale_spectral_direction"]["theta_mod_90_deg"]
        theta90 = estimate_axes(cv2.rotate(src_image, cv2.ROTATE_90_CLOCKWISE))["theta_mod_90_deg"]
        theta180 = estimate_axes(cv2.rotate(src_image, cv2.ROTATE_180))["theta_mod_90_deg"]
        def modulo90_error(a, b):
            return min(abs(a-b),90-abs(a-b))
        rotational = {"axis_90_error_deg": modulo90_error(baseline_theta,theta90),
                      "axis_180_error_deg": modulo90_error(baseline_theta,theta180)}
        if ann_file:
            ann = json.loads(ann_file.read_text(encoding="utf-8"))
            _validate_annotation(ann, image)
            checks = _compare(result, ann, (ann["image_height"],ann["image_width"]))
        else:
            checks = {"score_state":"NO_ANNOTATION_ON_MAIN"}
        row = {"sample_id":sample_id, "image":str(rel),
               "fabric_id":sample_id, # original + zoom are not separate fabrics
               "algorithm": result, "evaluation":checks,
               "rotation_equivariance": rotational}
        rows.append(row)
    tested = [x["evaluation"] for x in rows
              if x["evaluation"]["score_state"] == "EVALUATED"]
    angle_errors = [x["reference_angle_error_deg"] for x in tested]
    cross_errors = [x["cross_angle_error_deg"] for x in tested
                    if x["cross_angle_error_deg"] is not None]
    pitch_errors = [x["same_yarn_pitch_relative_error_pct"] for x in tested
                    if x["same_yarn_pitch_relative_error_pct"] is not None]
    result = {
        "evaluation_kind":"ANNOTATION_BLIND_INFERENCE_DEVELOPMENT_SET_NOT_HELD_OUT",
        "number_of_independent_fabrics":len(rows),
        "number_of_fabrics_with_reviewed_annotations":len(tested),
        "number_missing_latest_annotation":len(rows)-len(tested),
        "important_limitations":[
           "Operator annotations are line-axis references, not dense segmentation truth",
           "2x zoom is interpolated: no extra physical information",
           "Without inner 5cm calibration markers physical density is UNAVAILABLE",
           "No weave classes have 0/1 verified over-under crossing ground truth",
           "This is the DEVELOPMENT SET; cross-scale FFT bands were selected after reviewing these examples",
           "No independent held-out physical yarn accuracy has yet been measured",
        ],
        "reference_angle_median_absolute_error_deg":
            float(np.median(angle_errors)) if angle_errors else None,
        "cross_angle_median_absolute_error_deg":
            float(np.median(cross_errors)) if cross_errors else None,
        "same_pitch_median_relative_error_pct":
            float(np.median(pitch_errors)) if pitch_errors else None,
        "rotation_90_max_modulo90_error_deg":
            max(x["rotation_equivariance"]["axis_90_error_deg"] for x in rows),
        "rotation_180_max_modulo90_error_deg":
            max(x["rotation_equivariance"]["axis_180_error_deg"] for x in rows),
        "per_fabric": rows,
        "acceptance_gates": {
          "ten_parameters_pass": False,
          "independent_holdout_available": False,
          "sample_count_meets_six_annotated": len(tested) == 6,
          "development_reference_axis_median_under_3deg":
             bool(angle_errors and np.median(angle_errors) < 3),
          "development_reference_axis_all_under_5deg":
             bool(angle_errors and len(angle_errors) == len(tested) and max(angle_errors) < 5),
          "development_physical_pitch_median_under_10pct":
             bool(pitch_errors and np.median(pitch_errors) < 10),
          "development_physical_pitch_all_under_20pct":
             bool(pitch_errors and len(pitch_errors) == len(tested) and max(pitch_errors) < 20),
          "weave_over_under_physical_ground_truth_available": False,
          "five_cm_physical_scale_available": False,
          "per_yarn_width_reference_available": False,
          "comment":"Unit tests and CI may pass while acceptance necessarily FAILS; never confuse these.",
        },
    }
    if output:
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",
                          encoding="utf-8")
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=ROOT)
    p.add_argument("--output",type=Path,default=Path("pure10-out/report.json"))
    p.add_argument("--overlays",type=Path,default=Path("pure10-out/overlays"))
    args=p.parse_args()
    res=evaluate(args.root,args.output,args.overlays)
    summary={k:v for k,v in res.items() if k != "per_fabric"}
    print(json.dumps(summary,indent=2,ensure_ascii=False))
    for r in res["per_fabric"]:
        ev=r["evaluation"]
        print(r["sample_id"],"state=",ev["score_state"],
              "angle error=",ev.get("reference_angle_error_deg"),
              "pitch error %=",ev.get("same_yarn_pitch_relative_error_pct"))


if __name__=="__main__":
    main()
