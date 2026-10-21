from __future__ import annotations
"""Physical RT v2 frozen-image A/B; adapted scorer, detectors unchanged.

Input: photo-guided flat 8000x6000 R/T images (not thumbnails).
Five arms: frozen V0.6.3 full-image output, original local integer phase,
floating phase, seven-strip shared phase, per-yarn optical tracklets.
All yarn centre F1s use EXACTLY the SAME 9 ROI-local 520px windows,
the SAME physical ground truth and corrected *gated cardinality* matcher.

The optimized arms assume station-flat warp/weft axes (a user-confirmed
capture constraint). V0.6.3 attempts automatic orientation. Accordingly,
direction-angle accuracy is separately labelled as non-comparable.

Physical truth is opened ONLY after all image-only inference is frozen.
"""
import argparse
import json
import math
import resource
import time
from pathlib import Path
import cv2
import numpy as np

from engine import pipeline
from engine.width import map_centerlines_to_reflection
from engine.multiwindow_pitch import (
    PitchSettings,detect_calibration_frame,frame_windows,analyze_pitch_window)
from engine.local_axis_rectification import adjusted_window_homography
from engine.physical_center_validation import validate_physical_centers
from engine.subpixel_physical_phase import validate_centers_fractional
from engine.local_yarn_tracks import trace_local_yarns
from engine.individual_yarn_tracelets import trace_individual_entities
from evaluate_center_matching import cardinality_gated_yarn_match
from evaluate_yarn_track_identity import projected_truth_curves
from synthetic_capture_8k import hash_file

FAMILIES=("warp","weft")
ARMS=("V063_FULL","INTEGER_LOCAL","FLOAT_LOCAL","SHARED_SEVEN","INDIVIDUAL_SEVEN")
ROOT=Path("experiments/shibie-8k-capture-multiwindow")


def _center_from_polyline(points,family,mid=260.,size=520):
    pts=np.asarray(points,np.float64)
    if pts.ndim!=2 or pts.shape[1]!=2 or len(pts)<2 or not np.isfinite(pts).all():
        return None
    along_axis=1 if family=="warp" else 0
    normal_axis=1-along_axis
    u=pts[:,along_axis]
    v=pts[:,normal_axis]
    order=np.argsort(u)
    u=u[order];v=v[order]
    ok=np.r_[True,np.diff(u)>1.e-5]
    u=u[ok];v=v[ok]
    if len(u)<2 or not u[0]<=mid<=u[-1]:
        return None
    val=float(np.interp(mid,u,v))
    return val if 0<=val<size else None


def _sample_lines(raw_lines,H,family):
    predicted=[]
    for line in raw_lines:
        pts=np.asarray(line,np.float32)
        if len(pts)<2:continue
        mapped=cv2.perspectiveTransform(pts[None],H)[0]
        c=_center_from_polyline(mapped,family)
        if c is not None:predicted.append(c)
    return sorted(predicted)


def _sample_tracks(tracks,family):
    return sorted(y for tr in tracks
                  if (y:=_center_from_polyline(tr["points"],family)) is not None)


def _original_v063(rbytes,tbytes):
    """Use the unmodified production function; spy on selected width seeds."""
    captured={}
    original=pipeline._run_direction
    def wrapper(img,deg,mx,my):
        ans=original(img,deg,mx,my)
        captured[round(float(deg)%180,4)]=ans
        return ans
    start=time.perf_counter()
    pipeline._run_direction=wrapper
    try:
        try:
            result=pipeline.run_measurement(
                rbytes,tbytes,mm_per_px_x=.0125,mm_per_px_y=.0125,
                sample_id="flat_AB_V063_unchanged")
            error=None
        except Exception as exc:
            result={"status":"EXCEPTION","failure_reasons":[type(exc).__name__+":"+str(exc)]}
            error=type(exc).__name__+":"+str(exc)
    finally:
        pipeline._run_direction=original
    lines={fam:[] for fam in FAMILIES}
    orientation=result.get("orientation",{})
    norm=result.get("normalization",{})
    if norm and orientation:
        for fam in FAMILIES:
            angle=orientation.get(fam+"_direction_deg")
            q=captured.get(round(float(angle)%180,4)) if angle is not None else None
            if q and "_width_seed" in q:
                lines[fam]=map_centerlines_to_reflection(
                    q["_width_seed"],norm,np.eye(2,3,dtype=np.float32))
    out={"version":result.get("engine_version","0.6.3"),
         "profile":result.get("algorithm_profile"),
         "status":result.get("status"),
         "reasons":result.get("failure_reasons"),
         "warp_density_cm":result.get("warp_density_per_cm"),
         "weft_density_cm":result.get("weft_density_per_cm"),
         "orientation":orientation,
         "twill":result.get("twill"),
         "angle_is_automatic":True,
         "exception":error,"runtime_seconds":round(time.perf_counter()-start,3),
         "raw_line_counts":{fam:len(lines[fam]) for fam in FAMILIES}}
    return out,lines


def _draw(tile,projected,family,thickness=1):
    output=tile.copy()
    color=(0,70,255) if family=="warp" else (30,220,255)
    for v in projected:
        z=int(round(v))
        if family=="warp":
            cv2.line(output,(z,0),(z,519),color,thickness,cv2.LINE_AA)
        else:
            cv2.line(output,(0,z),(519,z),color,thickness,cv2.LINE_AA)
    return output


def _side_by_side(tile, gt, predictions, out):
    # 2x4 grid: transmission, GT and each of the five actual detector variants.
    keylist=["NATIVE_TRANSMISSION","TRUE_YARN_CENTRES"]+list(ARMS)
    img=np.full((2*520,4*520,3),237,np.uint8)
    for index,label in enumerate(keylist):
        patch=tile.copy() if label=="NATIVE_TRANSMISSION" else (
            _draw(tile,gt["warp"],"warp") if label=="TRUE_YARN_CENTRES"
            else tile.copy())
        if label=="TRUE_YARN_CENTRES":
            patch=_draw(patch,gt["weft"],"weft")
        if label in ARMS:
            patch=_draw(patch,predictions[label]["warp"],"warp")
            patch=_draw(patch,predictions[label]["weft"],"weft")
        row,col=divmod(index,4)
        img[row*520:(row+1)*520,col*520:(col+1)*520]=patch
        cv2.rectangle(img,(col*520,row*520),
                      (col*520+518,row*520+31),(255,255,255),-1)
        cv2.putText(img,label,(col*520+8,row*520+24),
                    cv2.FONT_HERSHEY_SIMPLEX,.59,(10,10,10),2,cv2.LINE_AA)
    if not cv2.imwrite(str(out),img,[cv2.IMWRITE_JPEG_QUALITY,89]):
        raise RuntimeError("AB_VISUAL_WRITE_FAILED")


def compare(case,image_dir,output_dir):
    source=Path(image_dir)
    out=Path(output_dir)
    out.mkdir(parents=True,exist_ok=True)
    rp=source/"reflection_8000x6000.jpg"
    tp=source/"transmission_8000x6000.jpg"
    gt_path=source/"truth.json"
    if not (rp.is_file() and tp.is_file() and gt_path.is_file()):
        raise RuntimeError("ORIGINAL_GENERATED_8K_PAIR_REQUIRED")
    rbytes=rp.read_bytes()
    tbytes=tp.read_bytes()
    R=cv2.imdecode(np.frombuffer(rbytes,np.uint8),cv2.IMREAD_COLOR)
    T=cv2.imdecode(np.frombuffer(tbytes,np.uint8),cv2.IMREAD_COLOR)
    if R is None or T is None or R.shape!=T.shape or R.shape!=(6000,8000,3):
        raise RuntimeError("NATIVE_8K_RAW_INPUT_SHAPE_ERROR")
    input_hashes={"reflection":hash_file(rp),"transmission":hash_file(tp)}
    old,raw_lines=_original_v063(rbytes,tbytes)
    old["internal_candidates_diagnostic_only_on_FAIL"]=True
    if old["status"] in ("FAIL","EXCEPTION"):
        raw_lines={fam:[] for fam in FAMILIES}
    start=time.perf_counter()
    frame=detect_calibration_frame(R)
    windows=[]
    settings=PitchSettings()
    if frame.get("status")=="PASS":
        # Fixed ZERO angle is the station condition, not a learned GT hint.
        for i,j,M in frame_windows(frame,settings.grid,settings.window_size_px):
            H=adjusted_window_homography(M,0.,settings.window_size_px,520)
            rr=cv2.warpPerspective(R,H,(520,520))
            tt=cv2.warpPerspective(T,H,(520,520))
            proposals=analyze_pitch_window(rr,tt,settings)
            predictions={"V063_FULL":{},"INTEGER_LOCAL":{},
                         "FLOAT_LOCAL":{},"SHARED_SEVEN":{},"INDIVIDUAL_SEVEN":{}}
            details={}
            for fam in FAMILIES:
                guesses=proposals[fam]["candidates"]
                pitch=guesses[0]["pitch_px"] if guesses else None
                integer=validate_physical_centers(rr,tt,fam,pitch)
                floating=validate_centers_fractional(rr,tt,fam,pitch)
                shared=trace_local_yarns(rr,tt,fam,pitch)
                individual=trace_individual_entities(rr,tt,fam,pitch)
                predictions["V063_FULL"][fam]=_sample_lines(raw_lines[fam],H,fam)
                predictions["INTEGER_LOCAL"][fam]=(
                    integer.get("center_positions_px",[]) if integer.get("status")=="PASS" else [])
                predictions["FLOAT_LOCAL"][fam]=(
                    floating.get("center_positions_px",[]) if floating.get("status")=="PASS" else [])
                predictions["SHARED_SEVEN"][fam]=(
                    _sample_tracks(shared["tracks"],fam) if shared.get("status")=="PASS" else [])
                predictions["INDIVIDUAL_SEVEN"][fam]=(
                    _sample_tracks(individual["tracks"],fam) if individual.get("status")=="PASS" else [])
                details[fam]={"raw_acf_pitch_candidates":guesses[:3],
                    "pitch_primary_from_pixels":pitch,
                    "INTEGER_LOCAL":{k:v for k,v in integer.items() if k not in ("center_positions_px","phase_candidates")},
                    "FLOAT_LOCAL":{k:v for k,v in floating.items() if k not in ("center_positions_px","phase_candidates","subpixel_period")},
                    "SHARED_SEVEN":{k:v for k,v in shared.items() if k not in ("tracks","slices")},
                    "INDIVIDUAL_SEVEN":{k:v for k,v in individual.items() if k!="tracks"},
                    "predictions_counts":{v:len(q.get(fam,[])) for v,q in predictions.items()}}
            windows.append({"grid":[i,j],"raw_to_tile":H.tolist(),
                "R":rr,
                "T":tt,
                "predictions":predictions,"details":details})
    optimized_time=time.perf_counter()-start
    (out/"frozen_predictions_before_GT.json").write_text(json.dumps({
        "input_sha256":input_hashes,"original":old,"windows":[
        {k:v for k,v in w.items() if k not in ('R','T')} for w in windows]},indent=2))
    # Labels may enter the process ONLY from this point forward.
    truth=json.loads(gt_path.read_text(encoding="utf-8"))
    if truth.get("sha256")!=input_hashes:
        raise RuntimeError("SYNTHETIC_TRUTH_INPUT_HASH_MISMATCH")
    scene=truth.get("source_scene",{})
    if (scene.get("rotation_deg")!=0 or scene.get("fabric_rotation_deg")!=0
        or scene.get("perspective")!=0):
        raise RuntimeError("NOT_ZERO_ROTATION_SCENE")
    if frame.get("status")!="PASS":
        report={"case":case,"status":"FRAME_NOT_FOUND",
                "frame":frame,"original":old,"source_hash":input_hashes}
        (out/"comparison.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        print("FLAT_PHOTO_AB "+json.dumps(report,ensure_ascii=False),flush=True)
        return report
    evaluated=[]
    for w in windows:
        scores={}
        truths={}
        for fam in FAMILIES:
            entities=projected_truth_curves(
                truth,fam,np.asarray(w["raw_to_tile"],np.float64),520,
                [260.],min_eligible_slices=1)
            true=sorted(v for entity in entities
                        if (v:=_center_from_polyline(entity["sampled_points_in_tile"],fam)) is not None)
            truths[fam]=true
            pitch=truth["true_pitch_px_canonical"][fam]
            scores[fam]={}
            for arm in ARMS:
                pred=w["predictions"][arm][fam]
                match=cardinality_gated_yarn_match(pred,true,pitch)
                gates={str(gate):cardinality_gated_yarn_match(pred,true,pitch,gate) for gate in (.20,.25,.32,.40)}
                scores[fam][arm]={"f1":round(match["f1"],4),
                    "gate_sensitivity":gates,"false_positive_count":len(pred)-match['matches'],
                    "missed_count":len(true)-match['matches'],
                    "precision":round(match["precision"],4),
                    "recall":round(match["recall"],4),
                    "matched":match["matches"],"predicted":len(pred),
                    "actual":len(true),
                    "matching_gate_fraction_of_true_pitch":.32}
        evaluated.append({"grid":w["grid"],"scores":scores,"details":w["details"],
            "true_centers":truths,"predicted_centers":w["predictions"]})
        _side_by_side(w["T"],truths,w["predictions"],out/("window_"+"_".join(map(str,w['grid']))+"_AB.jpg"))
        if w["grid"]==[1,1] and w["T"] is not None:
            _side_by_side(w["T"],truths,w["predictions"],
                          out/"actual_algorithm_same_region_AB.jpg")
            cv2.imwrite(str(out/"input_R_center_520px.jpg"),w["R"])
            cv2.imwrite(str(out/"input_T_center_520px.jpg"),w["T"])
    summaries={}
    for fam in FAMILIES:
        famrows=[x["scores"][fam] for x in evaluated]
        mids=[x for x in evaluated if x["grid"]==[1,1]]
        summaries[fam]={}
        for arm in ARMS:
            score=[x[arm] for x in famrows]
            median_pitch=[]
            for w in evaluated:
                p=w["details"][fam]["pitch_primary_from_pixels"]
                if p is not None:median_pitch.append(p)
            summaries[fam][arm]={
                 "mean_f1_9_windows":round(float(np.mean([q["f1"] for q in score])),4),
                 "micro_f1_9_windows":round(float(2*sum(q["matched"] for q in score)/
                                    max(sum(q["predicted"]+q["actual"] for q in score),1)),4),
                 "mean_precision_9_windows":round(float(np.mean([q["precision"] for q in score])),4),
                 "mean_recall_9_windows":round(float(np.mean([q["recall"] for q in score])),4),
                 "center_window_f1":mids[0]["scores"][fam][arm]["f1"],
                 "windows_with_candidates":sum(q["predicted"]>0 for q in score),
                 "window_refusal_fraction":sum(q["predicted"]==0 for q in score)/len(score),
                 "worst_window_f1":min(q['f1'] for q in score),
                 "predicted_total":sum(q['predicted'] for q in score),
                 "actual_total":sum(q['actual'] for q in score),
                 "missed_total":sum(q['missed_count'] for q in score),
                 "false_positive_total":sum(q['false_positive_count'] for q in score),
                 "gate_micro_f1":{str(g):2*sum(q['gate_sensitivity'][str(g)]['matches'] for q in score)/max(sum(q['predicted']+q['actual'] for q in score),1) for g in (.20,.25,.32,.40)}}
        pitch_values=[]
        for w in evaluated:
            opt=w["details"][fam]["FLOAT_LOCAL"].get("pitch_px")
            if opt is not None:pitch_values.append(opt)
        pitch_med=float(np.median(pitch_values)) if pitch_values else None
        summaries[fam]["photo_optimized_density_cm"]=(
            round(10/(pitch_med*.0125),3) if pitch_med is not None else None)
        summaries[fam]["real_density_per_cm_GT_ONLY"]=truth["true_density_per_cm"][fam]
    gt_density=truth["true_density_per_cm"]
    densities={
       "truth_per_cm":gt_density,
       "V063_FULL":{fam:old.get(fam+"_density_cm") for fam in FAMILIES},
       "FLOAT_LOCAL":{fam:summaries[fam]["photo_optimized_density_cm"] for fam in FAMILIES}}
    for arm in ("V063_FULL","FLOAT_LOCAL"):
        densities[arm+"_abs_pct_error"]={
          fam:round(100*abs(densities[arm][fam]-gt_density[fam])/gt_density[fam],3)
             if densities[arm][fam] is not None else None
          for fam in FAMILIES}
    for arm in ('V063_FULL','FLOAT_LOCAL'):
        densities[arm+'_absolute_error_per_cm']={fam:abs(densities[arm][fam]-gt_density[fam]) if densities[arm][fam] is not None else None for fam in FAMILIES}
    report={"case":case,"status":"MEASURED","input_source":"NATIVE_8000x6000_HEIGHTFIELD_RT_V2",
         "input_hash_sha256":input_hashes,"GT_only_weave":truth["true_weave"],
         "GT_only_calibration_mm_per_px":truth["camera_geometry"]["rectified_mm_per_px"],
         "GT_only_yarn_count":{fam:len(truth["physical_yarn_centerlines"][fam]) for fam in FAMILIES},
         "frame_from_photons":{k:v for k,v in frame.items() if k!="raw_to_frame"},
         "original":old,"optimized_using_known_flat_axis":True,
         "optimized_angle_accuracy_not_comparable_with_autoorient_V063":True,
         "density":densities,"summaries":summaries,"windows":evaluated,
         "optimized_window_inference_seconds":round(optimized_time,2),
         "whole_process_peak_rss_mib":round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024.,2),
         "limitations":["SYNTHETIC_HEIGHTFIELD_NOT_CALIBRATED_TO_REAL_RT",
                        "TRUE_T_SYNTHETIC_NOT_REAL_CAMERA",
                        "0_DEG_ALIGNMENT_IS_CAPTURE_CONSTRAINT_NOT_LEARNED",
                        "F1_IS_LOCAL_MID_CROSS_SECTION_PHYSICAL_CENTRE_NOT_FULL_TRACK_ID",
                        "WINDOWS_FROM_ONE_IMAGE_NOT_INDEPENDENT_SAMPLES",
                        "NO_WEAVE_ACCURACY_AS_OPTIMIZED_TRACKER_HAS_NO_WEAVE_CLASSIFIER"]}
    (out/"comparison.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    compact={"case":case,"original_status":old["status"],"summary":summaries,
              "density":densities,"runtime_s":{"original":old["runtime_seconds"],
                            "optimized_all_variants":round(optimized_time,2)}}
    print("PHOTO_GUIDED_SAME_REGION_AB "+json.dumps(compact,ensure_ascii=False),flush=True)
    return report


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--case",required=True)
    p.add_argument("--images",required=True,type=Path)
    p.add_argument("--out",required=True,type=Path)
    a=p.parse_args()
    compare(a.case,a.images,a.out)
