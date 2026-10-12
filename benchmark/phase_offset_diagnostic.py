"""Geometric localization audit: distance from annotated *visible yarn* to V4 A tracks.

The input direction is supplied by a person. This tool deliberately does NOT
count small angular error as localization success or create an auto-correction.
These are proximal-point diagnostics, not a true pixelwise yarn mask IoU.
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
    for role, color in (("reference",(0,220,255)),("check_same",(255,255,0))):
        segment = annotation["segments"].get(role)
        if segment:
            pts = projection(segment)
            cv2.line(preview, tuple(pts[0]),tuple(pts[1]),color,3,cv2.LINE_AA)
            for xy in pts:
                cv2.circle(preview,tuple(xy),4,color,-1,cv2.LINE_AA)
    header = np.zeros((35,preview.shape[1],3),dtype=np.uint8)
    cv2.putText(header,"RED: V4 A candidate / YELLOW: input real yarn / CYAN: separate check",
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
    report={
        "sample_id":args.id,"status":"POSITION_DIAGNOSTIC_ONLY",
        "input_type":"ROI" if provenance else "FULL_IMAGE",
        "origin_xy_px":offset, "candidate_A_lines":len(v4["first"]),
        "reference":analysis["reference"],
        "independent_check_same":analysis["check_same"],
        "report_caution":"Low angular error cannot validate correct yarn centers. Do not auto-correct grid phase from these metrics alone.",
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
    payload={
        "schema_version":"v6-anchor-candidate-0.1",
        "status":"POSITION_CALIBRATED_CANDIDATES" if ready_a else "UNAVAILABLE",
        "input_image_sha256":annotation["image_sha256"],
        "frozen_v4_sha256":FROZEN_SHA,
        "calibrated_native_roi_offset_px":list(offset),
        "family_A":{"status":"TWO_YARN_INPUT_CALIBRATED" if ready_a else "UNVERIFIED_OR_ABSTAINED",
                    "tracks_px":corrected_a,
                    "physical_yarn_identity":"UNKNOWN_UNLESS_MANUALLY_ASSIGNED"},
        "family_B":{"status":"TWO_YARN_INPUT_CALIBRATED" if ready_b else "UNVERIFIED_UNCHANGED_V4",
                    "tracks_px":corrected_b,
                    "physical_yarn_identity":"UNKNOWN_UNLESS_MANUALLY_ASSIGNED"},
        "independent_holdout_status":report.get("v6_dual_physical_yarn_calibration",{}).get("independent_holdout_test","NOT_EVALUATED"),
        "safety_note":"Candidate grid only. Do not publish yarn counts, density or per-yarn accuracy without independent evidence.",
    }
    (output.parent/"v6_candidate_tracks.json").write_text(json.dumps(payload,ensure_ascii=False)+"\n",encoding="utf-8")
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
