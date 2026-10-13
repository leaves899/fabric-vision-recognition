"""Geometric diagnostics for manually inferred yarn paths and V4 candidates.

For U20261013 the clicked lines are trajectories of true physical yarns through
possible occlusion, NOT continuously visible strand pixels nor precise physical
centerline pixel ground truth. Distances are approximate geometry only.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

from benchmark.manual_annotation import samples, validate_annotation

FROZEN_SHA = "dde5d84193a3f3d02bb55ad72a8c2b9f2a640034563ed936736ad46808b8dad1"


def closest_track_distances(points, tracks):
    """Return closest Euclidean px distance for each query point to candidate polyline A."""
    segments = []
    for track in tracks:
        poly = np.asarray(track, dtype=np.float64)
        if poly.ndim != 2 or poly.shape[1] != 2 or len(poly) < 2:
            continue
        a, b = poly[:-1], poly[1:]
        valid = np.sum((b-a)**2, axis=1) > 1e-10
        if np.any(valid):
            segments.append(np.column_stack((a[valid], b[valid])))
    if not segments:
        return [None] * len(points)
    seg = np.vstack(segments)
    a = seg[:, :2]
    b = seg[:, 2:]
    delta = b-a
    denominator = np.sum(delta*delta, axis=1)
    out = []
    for p in np.asarray(points, dtype=np.float64):
        t = np.clip(np.sum((p-a)*delta, axis=1)/denominator, 0, 1)
        foot = a+t[:, None]*delta
        out.append(float(np.sqrt(np.min(np.sum((foot-p)**2, axis=1)))))
    return out


def _cross2(a,b):
    return float(a[0]*b[1]-a[1]*b[0])


def nearby_candidate_pitch(tracks, sample_axis, midpoint, radius=240):
    """Intersection spacing on a local normal transect, not ground truth pitch."""
    v = np.asarray(sample_axis[1],float)-np.asarray(sample_axis[0],float)
    length = float(np.linalg.norm(v))
    if length < 1:
        return None, 0
    n = np.array([-v[1],v[0]])/length
    center = np.asarray(midpoint,float)
    start = center-radius*n
    direction = 2*radius*n
    offsets = []
    for track in tracks:
        poly=np.asarray(track,float)
        if poly.ndim != 2 or poly.shape[1] != 2 or len(poly) < 2:continue
        hits=[]
        for a,b in zip(poly[:-1],poly[1:]):
            d=b-a
            det=_cross2(direction,d)
            if abs(det)<1e-7:continue
            w=a-start
            t=_cross2(w,d)/det
            s=_cross2(w,direction)/det
            if 0<=t<=1 and 0<=s<=1:
                hits.append(float((t-.5)*2*radius))
        if hits:
            offsets.append(float(np.median(hits)))
    if len(offsets)<3:
        return None,len(offsets)
    offsets.sort()
    diffs=np.diff(offsets)
    diffs=diffs[diffs>2]
    return (round(float(np.median(diffs)),4) if len(diffs)>=2 else None),len(offsets)


def evaluate_tracks(annotation, tracks, origin=(0,0)):
    """Distances are computed at 15 points on reference and *different* check line."""
    ox,oy=origin
    out={}
    ref=annotation["segments"]["reference"]
    original_ref=np.asarray(ref,float)-[ox,oy]
    for role in ("reference","check_same"):
        segment=annotation["segments"].get(role)
        if not segment:
            out[role]={"status":"NO_OPERATOR_SEGMENT"}
            continue
        points=np.asarray(segment,float)-[ox,oy]
        sampled=np.linspace(points[0],points[1],15)
        distances=closest_track_distances(sampled,tracks)
        available=[x for x in distances if x is not None]
        pitch, crossings=nearby_candidate_pitch(tracks,original_ref,sampled[7])
        median=round(float(np.median(available)),3) if available else None
        normalized=round(median/pitch,3) if median is not None and pitch is not None and pitch>0 else None
        out[role]={
            "status":"GEOMETRIC_AUDIT_ONLY",
            "median_min_distance_px":median,
            "p90_min_distance_px":round(float(np.percentile(available,90)),3) if available else None,
            "local_candidate_pitch_px":pitch,
            "local_candidate_crossing_count":crossings,
            "distance_as_fraction_of_candidate_pitch":normalized,
            "possible_gap_phase": bool(normalized is not None and .30<=normalized<=.70),
            "spatial_misalignment_review": bool(normalized is not None and normalized >= .25),
            "limitation":"Candidate-track distance to operator-marked segment. Does NOT prove physical yarn center; excludes photometric yarn/gap evidence.",
        }
    return out



def render_position_overlay(image, tracks, annotation, origin, output_path):
    """Visual evidence only: red candidate A, yellow input yarn, cyan DIFFERENT check yarn."""
    import cv2
    long_side = max(image.shape[:2])
    factor = min(1.0, 1300.0/long_side)
    preview = cv2.resize(image, (round(image.shape[1]*factor), round(image.shape[0]*factor)),
                         interpolation=cv2.INTER_AREA) if factor < 1 else image.copy()
    def projection(points):
        a = np.asarray(points, dtype=float)
        a[:,0] = (a[:,0] - origin[0])*factor
        a[:,1] = (a[:,1] - origin[1])*factor
        return np.rint(a).astype(np.int32)
    for track in tracks:
        if len(track) >= 2:
            pts = np.rint(np.asarray(track,float)*factor).astype(np.int32)
            cv2.polylines(preview, [pts], False, (40,60,235), 1, cv2.LINE_AA)
    for role, color in (("reference",(0,220,255)),("check_same",(255,255,0)),("holdout_same",(255,0,255))):
        segment = annotation["segments"].get(role)
        if segment:
            pts = projection(segment)
            cv2.line(preview, tuple(pts[0]),tuple(pts[1]),color,3,cv2.LINE_AA)
            for xy in pts:
                cv2.circle(preview,tuple(xy),4,color,-1,cv2.LINE_AA)
    header = np.zeros((35,preview.shape[1],3),dtype=np.uint8)
    cv2.putText(header,"RED: V4 A / YELLOW: A1 / CYAN: A2 / MAGENTA: A3 HOLDOUT",
                (8,24),cv2.FONT_HERSHEY_SIMPLEX,.45,(255,255,255),1,cv2.LINE_AA)
    image_out = np.vstack([header,preview])
    if not cv2.imwrite(str(output_path),image_out):
        raise RuntimeError("failed to save position evidence JPEG")


def main(argv=None):
    cli=argparse.ArgumentParser(description="Audit candidate-track position against operator-marked yarn segments")
    cli.add_argument("--id",required=True)
    cli.add_argument("--result-dir",type=Path,required=True,help="folder containing V5 JSON")
    cli.add_argument("--out",type=Path,default=None)
    args=cli.parse_args(argv)
    root=Path(__file__).resolve().parents[1]
    sample=samples(root).get(args.id)
    if not sample:
        raise SystemExit("Not registered: "+args.id)
    annotation_path=root/"datasets/annotations/drafts"/(args.id+".json")
    annotation=validate_annotation(root,json.loads(annotation_path.read_text(encoding="utf-8")))
    if annotation["review_state"]!="OPERATOR_REVIEWED" or not annotation["reference_confirmed"]:
        raise SystemExit("NOT_EVALUATED: reference still unreviewed")
    result_dir=args.result_dir if args.result_dir.is_absolute() else root/args.result_dir
    record=json.loads((result_dir/"v5_result.json").read_text(encoding="utf-8"))
    result=record["result"]
    if result["v4"]["frozen_sha256"]!=FROZEN_SHA:
        raise SystemExit("Unexpected frozen V4 hash")
    provenance=record.get("original_image_provenance")
    offset=(0,0)
    source=(root/sample["image_path"]).read_bytes()
    import cv2
    image=cv2.imdecode(np.frombuffer(source,dtype=np.uint8),cv2.IMREAD_COLOR)
    if image is None:
        raise SystemExit("Cannot decode original image")
    if (image.shape[1],image.shape[0])!=(annotation["image_width"],annotation["image_height"]):
        raise SystemExit("EXIF/display orientation mismatch")
    if provenance:
        import hashlib
        if hashlib.sha256(source).hexdigest()!=provenance["original_image_sha256"]:
            raise SystemExit("Stale photo bytes")
        x0,y0,x1,y1=provenance["crop_xyxy_original_px"]
        image=image[y0:y1,x0:x1].copy()
        offset=(x0,y0)
        if [image.shape[1],image.shape[0]]!=provenance["cropped_pixel_size_px"]:
            raise SystemExit("Crop geometry mismatch")
    else:
        import hashlib
        if hashlib.sha256(source).hexdigest()!=result["image_sha256"]:
            raise SystemExit("Original image has changed")
    sys.path.insert(0,str(root/"demo/v5"))
    from v4_adapter import run_v4
    v4=run_v4(image,float(result["direction_evidence"]["v4_adapter_rotation_deg"]))
    analysis=evaluate_tracks(annotation,v4["first"],offset)
    inferred_physical_path = annotation.get("annotation_target")=="PHYSICAL_YARN_TRAJECTORY"
    report={
        "sample_id":args.id,"status":(
            "INFERRED_REAL_YARN_PATH_GEOMETRY_ONLY" if inferred_physical_path
            else "POSITION_DIAGNOSTIC_ONLY"),
        "input_type":"ROI" if provenance else "FULL_IMAGE",
        "origin_xy_px":offset, "candidate_A_lines":len(v4["first"]),
        "reference":analysis["reference"],
        "independent_check_same":analysis["check_same"],
        "annotation_target":annotation.get("annotation_target","UNSPECIFIED"),
        "trajectory_can_cross_occlusion":inferred_physical_path,
        "reported_distance_is_pixelwise_visible_yarn_accuracy":False,
        "report_caution":"U20261013 marked paths are inferred physical-yarn trajectories, not visible pixel GT. Agreement only supports approximate geometry. Do not certify yarn centers or adjust grid phase uncritically.",
        "user_report":"T001/T004/T005 tracks reported as lying in inter-yarn gaps",
    }
    output=args.out if args.out is not None else result_dir/"phase_diagnostic.json"
    output=output if output.is_absolute() else root/output
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    render_position_overlay(image, v4["first"], annotation, offset, output.parent/"position_overlay.jpg")
    # V6 experiment: derive phase only from the INPUT real-yarn reference.
    # The distinct second segment is held out and reported, never used to fit.
    from benchmark.yarn_phase_anchor import adjust_first_family
    first_anchor=(np.asarray(annotation["segments"]["reference"],float)-np.asarray(offset,float)).tolist()
    second_anchor=(np.asarray(annotation["segments"]["check_same"],float)-np.asarray(offset,float)).tolist() if annotation["segments"]["check_same"] else None
    candidate_a, anchor_report=adjust_first_family(v4["first"],first_anchor,second_anchor)
    report["v6_candidate_a_anchor"]=anchor_report
    if second_anchor:
        from benchmark.yarn_pitch_calibration import two_anchor_correct
        dual_corrected, dual_report = two_anchor_correct(v4["first"],first_anchor,second_anchor)
        report["v6_dual_physical_yarn_calibration"]=dual_report
        # The third marked A-yarn is NEVER used to estimate phase or pitch.
        holdout=annotation["segments"].get("holdout_same")
        if holdout:
            holdout_roi=(np.asarray(holdout,float)-np.asarray(offset,float)).tolist()
            from benchmark.yarn_phase_anchor import median_distance
            dual_report["independent_holdout_before_px"]=median_distance(holdout_roi,v4["first"])
            dual_report["independent_holdout_after_px"]=median_distance(holdout_roi,dual_corrected) if dual_report["status"]=="TWO_ANCHOR_CANDIDATE_GRID" else None
            dual_report["independent_holdout_test"]="MEASURED_NOT_USED_TO_CALIBRATE"
        else:
            dual_report["independent_holdout_test"]="NOT_EVALUATED_NO_THIRD_YARN"
        if dual_report["status"]=="TWO_ANCHOR_CANDIDATE_GRID":
            render_position_overlay(image,dual_corrected,annotation,offset,
                                    output.parent/"phase_and_pitch_anchored_candidate.jpg")
    report["v6_family_b"]="NOT_CORRECTED_NO_CONFIRMED_CROSS_ANCHOR"
    if anchor_report["status"] in ("ANCHORED_CANDIDATE_A","ALREADY_ALIGNED_A"):
        render_position_overlay(image,candidate_a,annotation,offset,output.parent/"phase_anchored_candidate.jpg")
    # Optional B-family physical reference is a SEPARATE operator input;
    # it cannot be invented from visual twill periodicity.
    if annotation["segments"].get("check_cross") and annotation["segments"].get("check_cross_second"):
        cross=(np.asarray(annotation["segments"]["check_cross"],float)-np.asarray(offset,float)).tolist()
        cross_second=(np.asarray(annotation["segments"]["check_cross_second"],float)-np.asarray(offset,float)).tolist()
        from benchmark.yarn_pitch_calibration import two_anchor_correct
        candidate_b,b_report=two_anchor_correct(v4["second"],cross,cross_second)
        report["v6_candidate_b_dual_calibration"]=b_report
        report["v6_family_b"]="TWO_CROSS_ANCHOR_CANDIDATE" if b_report["status"]=="TWO_ANCHOR_CANDIDATE_GRID" else "ABSTAINED"
    elif annotation["segments"].get("check_cross"):
        report["v6_family_b"]="NOT_CALIBRATED_ONLY_ONE_CROSS_YARN"

    # V6 usable output is a separately versioned candidate-track JSON, not a
    # silent replacement of frozen V5 results. Family B keeps its own status.
    ready_a=report.get("v6_dual_physical_yarn_calibration",{}).get("status")=="TWO_ANCHOR_CANDIDATE_GRID"
    corrected_a=dual_corrected if ready_a else v4["first"]
    ready_b=report.get("v6_family_b")=="TWO_CROSS_ANCHOR_CANDIDATE"
    corrected_b=candidate_b if ready_b else v4["second"]
    # V6.1: two physical endpoints without the NUMBER of real yarn
    # intervals can turn a single coarse yarn into two candidate tracks.
    # Only confirmed physical interval counts may activate de-duplication.
    verified_alias_a=False
    verified_alias_b=False
    from benchmark.yarn_duplicate_guard import suppress_double_tracks
    if second_anchor:
        holdout=annotation["segments"].get("holdout_same")
        holdout_roi=(np.asarray(holdout,float)-np.asarray(offset,float)).tolist() if holdout else None
        guarded,guard_info=suppress_double_tracks(
            v4["first"],first_anchor,second_anchor,
            physical_intervals=annotation.get("same_family_intervals"),
            confirmed=annotation.get("same_family_intervals_confirmed") is True,
            holdout=holdout_roi)
        report["v61_family_a_duplicate_guard"]=guard_info
        verified_alias_a=guard_info["status"]=="DOUBLE_CANDIDATES_SUPPRESSED_UNVERIFIED_FIELD"
        if verified_alias_a:
            corrected_a=guarded
            ready_a=True
            render_position_overlay(image,corrected_a,annotation,offset,
                output.parent/"v61_duplicate_suppressed_candidate.jpg")
    else:
        report["v61_family_a_duplicate_guard"]={"status":"ABSTAINED","reason":"SECOND_REAL_YARN_ANCHOR_MISSING"}
    if ready_b and annotation.get("cross_family_intervals_confirmed") is True:
        cross=(np.asarray(annotation["segments"]["check_cross"],float)-np.asarray(offset,float)).tolist()
        cross2=(np.asarray(annotation["segments"]["check_cross_second"],float)-np.asarray(offset,float)).tolist()
        guarded_b,report_b=suppress_double_tracks(v4["second"],cross,cross2,
            physical_intervals=annotation.get("cross_family_intervals"),confirmed=True)
        report["v61_family_b_duplicate_guard"]=report_b
        verified_alias_b=report_b["status"]=="DOUBLE_CANDIDATES_SUPPRESSED_UNVERIFIED_FIELD"
        if verified_alias_b:
            corrected_b=guarded_b

    payload={
        "schema_version":"v6-anchor-candidate-0.1",
        "status":"PHYSICAL_INTERVALS_VERIFIED_ALIAS_REDUCED_CANDIDATES" if verified_alias_a else "POSITION_ONLY_DUPLICATE_RISK_UNVERIFIED",
        "input_image_sha256":annotation["image_sha256"],
        "frozen_v4_sha256":FROZEN_SHA,
        "calibrated_native_roi_offset_px":list(offset),
        "family_A":{"status":"VERIFIED_INTERVAL_ALIAS_REDUCED" if verified_alias_a else "POSITION_ALIGNED_COUNT_UNVERIFIED",
                    "tracks_px":corrected_a,
                    "physical_yarn_identity":"UNKNOWN_UNLESS_MANUALLY_ASSIGNED"},
        "family_B":{"status":"VERIFIED_INTERVAL_ALIAS_REDUCED" if verified_alias_b else "UNVERIFIED_COUNT",
                    "tracks_px":corrected_b,
                    "physical_yarn_identity":"UNKNOWN_UNLESS_MANUALLY_ASSIGNED"},
        "candidate_alias_guard_verified_A":verified_alias_a,
        "candidate_alias_guard_verified_B":verified_alias_b,
        "physical_yarn_count_usable":False,
        "independent_holdout_status":report.get("v6_dual_physical_yarn_calibration",{}).get("independent_holdout_test","NOT_EVALUATED"),
        "safety_note":"Candidate grid only. Do not publish yarn counts, density or per-yarn accuracy without independent evidence.",
    }
    (output.parent/"v6_candidate_tracks.json").write_text(json.dumps(payload,ensure_ascii=False)+"\n",encoding="utf-8")
    if ready_a:
        from benchmark.yarn_v6_visuals import save_compare
        save_compare(image,v4["first"],v4["second"],corrected_a,corrected_b,
                     annotation,offset,output.parent,b_calibrated=ready_b)
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
