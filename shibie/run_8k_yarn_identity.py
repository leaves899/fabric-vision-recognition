from __future__ import annotations
"""Native 8k R/T experiment: fixed centres vs image-only 7-slice local tracks.

Inference runs to completion WITHOUT touching truth.json.
Afterwards, physical GT IDs are projected through each image-only homography
for a different and more demanding repeated-cross-section evaluation.
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
from engine.local_yarn_tracks import trace_local_yarns, TrackSettings
from evaluate_yarn_track_identity import (
    projected_truth_curves,straight_candidate_tracks,evaluate_local_tracks)


ROOT=Path("experiments/shibie-8k-capture-multiwindow")
SLICES=7


def _colorized_overlay(tile,tracks,warp_color,weft_color):
    im=tile.copy()
    for fam in ("warp","weft"):
        rgb=warp_color if fam=="warp" else weft_color
        for tr in tracks.get(fam,[]):
            pts=np.asarray(tr["points"],np.float32)
            if len(pts)<2:continue
            pts=np.round(pts).astype(np.int32)
            cv2.polylines(im,[pts.reshape(-1,1,2)],False,rgb,2,cv2.LINE_AA)
    return im


def _draw_grid(panels, captions, path):
    side=520
    canvas=np.full((side*2,side*3,3),235,np.uint8)
    for index,(panel,caption) in enumerate(zip(panels,captions)):
        r,c=divmod(index,3)
        canvas[r*side:(r+1)*side,c*side:(c+1)*side]=panel
        cv2.rectangle(canvas,(c*side,r*side),(c*side+365,r*side+33),(255,255,255),-1)
        cv2.putText(canvas,caption,(c*side+9,r*side+24),
                    cv2.FONT_HERSHEY_SIMPLEX,.7,(0,0,0),2,cv2.LINE_AA)
    if not cv2.imwrite(str(path),canvas,[cv2.IMWRITE_JPEG_QUALITY,82]):
        raise RuntimeError("VISUAL_COMPARISON_WRITE_FAILED")


def benchmark(case):
    start=time.perf_counter()
    images=ROOT/"stress"/case
    out=ROOT/"identity-tracking"/case
    out.mkdir(parents=True,exist_ok=True)
    r=cv2.imread(str(images/"reflection_8000x6000.jpg"))
    t=cv2.imread(str(images/"transmission_8000x6000.jpg"))
    if r is None or t is None or r.shape!=(6000,8000,3) or t.shape!=r.shape:
        raise RuntimeError("NATIVE_8K_RT_REQUIRED")
    frame=detect_calibration_frame(r)
    if frame.get("status")!="PASS":
        raise RuntimeError("FRAME_NOT_FOUND: "+json.dumps(frame))
    settings=PitchSettings()
    pose=estimate_fabric_axis_from_frame(r,t,frame,settings)
    if pose["status"]=="UNDETERMINED":
        raise RuntimeError("FABRIC_AXIS_NOT_PROPOSED")
    records=[]
    previews={}
    for i,j,M in frame_windows(frame,3,settings.window_size_px):
        H=adjusted_window_homography(M,pose["image_rotation_deg"],640,520)
        rr=cv2.warpPerspective(r,H,(520,520))
        tt=cv2.warpPerspective(t,H,(520,520))
        estimates=analyze_pitch_window(rr,tt,settings)
        if (i,j)==(1,1):previews={"R":rr,"T":tt}
        for fam in ("warp","weft"):
            ranking=estimates[fam]["candidates"]
            pitch=ranking[0]["pitch_px"] if ranking else None
            old=validate_physical_centers(rr,tt,fam,pitch)
            floating=validate_centers_fractional(rr,tt,fam,pitch)
            seven=trace_local_yarns(rr,tt,fam,pitch)
            records.append({"grid":[i,j],"family":fam,"raw_to_tile":H.tolist(),
              "initial_pitch":pitch,"old":old,"float":floating,"seven":seven})
    inference_elapsed=time.perf_counter()-start
    # Absolutely no synthetic ground truth opened until all image-only
    # transform, pose, phase and local track proposals have been frozen above.
    truth=json.loads((images/"truth.json").read_text(encoding="utf-8"))
    evaluated=[]
    for item in records:
        fam=item["family"]
        H=np.asarray(item["raw_to_tile"],np.float64)
        slice_alongs=[x["along_px"] for x in item["seven"].get("slices",[])]
        if not slice_alongs:
            slice_alongs=[(j+.5)*520/SLICES for j in range(SLICES)]
        true=projected_truth_curves(truth,fam,H,520,slice_alongs)
        pitch_truth=truth["true_pitch_px_canonical"][fam]
        paths={
          "old":straight_candidate_tracks(item["old"],fam,slice_alongs),
          "float":straight_candidate_tracks(item["float"],fam,slice_alongs),
          "seven":item["seven"].get("tracks",[]) if item["seven"]["status"]=="PASS" else []
        }
        scores={name:evaluate_local_tracks(p,true,fam,pitch_truth) for name,p in paths.items()}
        evaluated.append({**item,
           "truth_identity_assessment_only":{
              "eligible_yarns":len(true),"metrics":scores,
              "truth_yarn_ids":[v["id"] for v in true]}})
        if item["grid"]==[1,1]:
            previews.setdefault("old",{})[fam]=paths["old"]
            previews.setdefault("float",{})[fam]=paths["float"]
            previews.setdefault("seven",{})[fam]=paths["seven"]
            previews.setdefault("GT",{})[fam]=[
               {"track_id":y["id"],"points":y["sampled_points_in_tile"]}
               for y in true]
    if previews:
        b=previews["T"]
        overlays=[previews["R"],b,
          _colorized_overlay(b,previews["GT"],(230,70,220),(250,220,35)),
          _colorized_overlay(b,previews["old"],(230,65,225),(45,225,255)),
          _colorized_overlay(b,previews["float"],(230,65,225),(45,225,255)),
          _colorized_overlay(b,previews["seven"],(230,65,225),(45,225,255))]
        labels=["Native R (tile)","Native T (tile)","Physical GT IDs",
                "Frozen integer","Float fixed tracks","7-slice image tracks"]
        _draw_grid(overlays,labels,out/"true_id_trajectory_comparison.jpg")
    summary={}
    for fam in ("warp","weft"):
        arr=[x for x in evaluated if x["family"]==fam]
        summary[fam]={}
        for method in ("old","float","seven"):
            summary[fam][method]={
              "mean_id_trajectory_f1":round(float(np.mean([
                 x["truth_identity_assessment_only"]["metrics"][method]["f1"] for x in arr])),4),
              "total_matches":sum(x["truth_identity_assessment_only"]["metrics"][method]["matched_tracks"] for x in arr),
              "total_proposed_tracks":sum(x["truth_identity_assessment_only"]["metrics"][method]["predicted_tracks"] for x in arr),
              "potential_gt_id_switches":sum(x["truth_identity_assessment_only"]["metrics"][method]["nearest_gt_id_switches_unmatched_inclusive"] for x in arr),
              "passing_windows":sum(x[method]["status"]=="PASS" for x in arr)}
    report={"case":case,"native_pair_shape":[6000,8000],
       "image_only_rotation":pose["image_rotation_deg"],"axis_status":pose["status"],
       "same_input_sha256":truth["sha256"],
       "truth_weave_FOR_AUDIT_ONLY":truth["true_weave"],
       "truth_rotation_FOR_AUDIT_ONLY":truth["source_scene"].get("fabric_rotation_deg"),
       "physical_width_P10_passes_capture_gate":truth["passes_capture_p10_gate"],
       "summary":summary,"windows":evaluated,
       "image_only_inference_seconds":round(inference_elapsed,2),
       "total_eval_runtime_seconds":round(time.perf_counter()-start,2),
       "peak_process_rss_mib":round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024.,1),
       "scope":["LOCAL_TILE_ID_LINK_NOT_GLOBAL_50MM_ID",
                "CURVE_CONTINUITY_SCORING_NOT_OCCLUSION_PIXEL_VISIBILITY",
                "EXPERIMENTAL_SYNTHETIC_NOT_REAL_CAMERA_R_T"]}
    (out/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("7_SLICE_PHYSICAL_IDENTITY "+json.dumps({
       "case":case,"pose":pose["image_rotation_deg"],"results":summary,
       "inference_s":report["image_only_inference_seconds"],
       "rss_mib":report["peak_process_rss_mib"]},ensure_ascii=False),flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--case",required=True)
    a=p.parse_args()
    benchmark(a.case)
