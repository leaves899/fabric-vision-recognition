from __future__ import annotations
"""Blind native-8k R/T individual yarn tracking vs frozen seven-slice engine.

Original frozen 7-slice baseline is run earlier in SAME GitHub workflow.
This experiment does NOT read baseline JSON or synthetic labels until ALL
independently measured image-only physical entities have been frozen.
"""
import argparse
import json
import resource
import time
from pathlib import Path
import cv2
import numpy as np
from engine.multiwindow_pitch import (
    PitchSettings,detect_calibration_frame,frame_windows,analyze_pitch_window)
from engine.local_axis_rectification import (
    estimate_fabric_axis_from_frame,adjusted_window_homography)
from engine.individual_yarn_tracelets import trace_individual_entities
from evaluate_yarn_track_identity import projected_truth_curves,evaluate_local_tracks
from run_8k_yarn_identity import _draw_grid,_colorized_overlay,ROOT


def run(case):
    start=time.perf_counter()
    images=ROOT/"stress"/case
    out=ROOT/"individual-tracklets"/case
    out.mkdir(parents=True,exist_ok=True)
    r=cv2.imread(str(images/"reflection_8000x6000.jpg"))
    t=cv2.imread(str(images/"transmission_8000x6000.jpg"))
    if r is None or t is None or r.shape!=(6000,8000,3) or t.shape!=r.shape:
        raise RuntimeError("ORIGINAL_8K_RT_PAIR_REQUIRED")
    frame=detect_calibration_frame(r)
    if frame["status"]!="PASS":
        raise RuntimeError("NO_CALIBRATED_CAMERA_FRAME")
    settings=PitchSettings()
    pose=estimate_fabric_axis_from_frame(r,t,frame,settings)
    if pose["status"]=="UNDETERMINED":
        raise RuntimeError("FABRIC_DIRECTION_UNDETERMINED")
    rows=[];preview={}
    for i,j,M in frame_windows(frame,settings.grid,settings.window_size_px):
        H=adjusted_window_homography(M,pose["image_rotation_deg"],640,520)
        rp=cv2.warpPerspective(r,H,(520,520))
        tp=cv2.warpPerspective(t,H,(520,520))
        p=analyze_pitch_window(rp,tp,settings)
        if (i,j)==(1,1):preview={"R":rp,"T":tp}
        for fam in ("warp","weft"):
            hypothesis=p[fam]["candidates"]
            seed= hypothesis[0]["pitch_px"] if hypothesis else None
            candidate=trace_individual_entities(rp,tp,fam,seed)
            rows.append({"grid":[i,j],"family":fam,"H":H.tolist(),
                         "initial_pitch_px":seed,"individual":candidate})
    infer_time=time.perf_counter()-start
    # Only now open the original baseline metrics and synthetic truth labels.
    frozen=json.loads((ROOT/"identity-tracking"/case/"report.json").read_text(encoding="utf-8"))
    gt=json.loads((images/"truth.json").read_text(encoding="utf-8"))
    if gt["sha256"]!=frozen["same_input_sha256"]:
        raise RuntimeError("BASELINE_INPUT_HASH_CHANGED")
    for item in rows:
        family=item["family"]
        H=np.asarray(item["H"],np.float64)
        n=7
        slices=np.linspace(520/(2*n),520-520/(2*n),n)
        true=projected_truth_curves(gt,family,H,520,slices)
        current=item["individual"]
        q=current["tracks"] if current["status"]=="PASS" else []
        item["truth_identity_assessment_only"]=evaluate_local_tracks(
            q,true,family,gt["true_pitch_px_canonical"][family])
        if item["grid"]==[1,1]:
            preview.setdefault("individual",{})[family]=q
            preview.setdefault("GT",{})[family]=[{
                 "track_id":x["id"],"points":x["sampled_points_in_tile"]}
                 for x in true]
            baseline=next(row for row in frozen["windows"]
                          if row["grid"]==[1,1] and row["family"]==family)
            preview.setdefault("seven",{})[family]=(
                 baseline["seven"]["tracks"] if baseline["seven"]["status"]=="PASS" else [])
            from evaluate_yarn_track_identity import straight_candidate_tracks
            preview.setdefault("float",{})[family]=straight_candidate_tracks(
                 baseline["float"],family,slices)
    summary={}
    for family in ("warp","weft"):
        entries=[x for x in rows if x["family"]==family]
        metrics=[x["truth_identity_assessment_only"] for x in entries]
        individual={
          "mean_id_trajectory_f1":round(float(np.mean([x["f1"] for x in metrics])),4),
          "total_matches":sum(x["matched_tracks"] for x in metrics),
          "total_proposed_tracks":sum(x["predicted_tracks"] for x in metrics),
          "potential_gt_id_switches":sum(x["nearest_gt_id_switches_unmatched_inclusive"] for x in metrics),
          "passing_windows":sum(x["individual"]["status"]=="PASS" for x in entries),
          "total_optical_rejections":sum(x["individual"].get("rejections",{}).get("optical",0) for x in entries),
          "total_order_rejections":sum(x["individual"].get("rejections",{}).get("order",0) for x in entries)}
        summary[family]={"frozen_integer":frozen["summary"][family]["old"],
                         "frozen_float":frozen["summary"][family]["float"],
                         "frozen_common_phase_seven":frozen["summary"][family]["seven"],
                         "independent_per_yarn":individual}
    b=preview["T"]
    images_out=[preview["R"],b]
    for name in ("GT","float","seven","individual"):
        images_out.append(_colorized_overlay(
           b,preview.get(name,{}),(230,65,225),(45,225,255)))
    _draw_grid(images_out,["Native R","Native T","Physical ID truth",
               "Frozen float straight","Frozen shared phase","Independent per yarn"],
               out/"independent_entity_visual_comparison.jpg")
    report={"case":case,"native_shape":[6000,8000],
       "same_native_input_sha256":gt["sha256"],"pose_from_images":pose["image_rotation_deg"],
       "truth_weave_EVALUATION_ONLY":gt["true_weave"],
       "truth_wave_fraction_EVALUATION_ONLY":gt["source_scene"]["wave_fraction"],
       "capture_p10_certified_from_synthetic_truth":gt["passes_capture_p10_gate"],
       "summary":summary,"windows":rows,
       "algorithm_only_runtime_seconds":round(infer_time,2),
       "process_peak_rss_mib":round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024.,1),
       "scope":["TILE_LOCAL_PHYSICAL_ID_ONLY",
                "NO_FULL_IMAGE_CROSS_OCCLUSION_TRACKING",
                "BLIND_GT_READ_ONLY_AFTER_INFERENCE",
                "SYNTHETIC_NOT_REAL_CAPTURE"]}
    (out/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("INDEPENDENT_YARN_ENTITY_AB "+json.dumps({
       "case":case,"summary":summary,"runtime":report["algorithm_only_runtime_seconds"],
       "memory_mib":report["process_peak_rss_mib"]},ensure_ascii=False),flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--case",required=True)
    args=p.parse_args()
    run(args.case)
