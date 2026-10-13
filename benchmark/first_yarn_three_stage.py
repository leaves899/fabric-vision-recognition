"""Three-stage first-physical-yarn research on operator-inferred yarn trajectories.

A: operator identifies TRUE physical yarn connection direction (possibly occluded).
B: independently detect image ridges at multiple longitudinal windows; do not
   train photometric templates or pixel phase on the operator's drawn path.
C: check candidate geometry against other inferred real-yarn trajectories,
   count aliasing and rot90 consistency. NO true fiber center/pixel GT exists.
The output is never automatically certified as a single real fiber.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import cv2
import numpy as np

from benchmark.manual_annotation import validate_annotation, segment_axis_deg
from benchmark.direction_only_first_yarn import score_profile, render

ROOT=Path(__file__).resolve().parents[1]
PREFIX="U20261013_"


def axial_error(a,b):
    return round(float(abs((a-b+90)%180-90)),3)


def centerline_coordinate(trajectory,m,offset):
    pts=np.asarray(trajectory,dtype=np.float64)-np.asarray(offset,dtype=np.float64)
    pts=cv2.transform(pts.reshape(1,2,2),m)[0]
    return float(np.mean(pts[:,1]))


def evaluate_centers(ann,visual,proposal):
    """Check approximate operator trajectory GEOMETRY only after image-only fit."""
    if visual is None:
        return dict(status="ABSTAIN_NO_IMAGE_STRUCTURE",
                    true_yarn_pixel_accuracy_evaluable=False)
    _,peaks,m,offset=visual
    coords=np.asarray(peaks,float)
    if len(coords)<4:
        return dict(status="ABSTAIN_TOO_FEW_CANDIDATES",
                    true_yarn_pixel_accuracy_evaluable=False)
    ref=ann["segments"]["reference"]
    reference_y=centerline_coordinate(ref,m,offset)
    entries={}
    for role in ("reference","check_same","holdout_same"):
        path=ann["segments"].get(role)
        if not path:
            continue
        center=centerline_coordinate(path,m,offset)
        nearest=int(np.argmin(np.abs(coords-center)))
        entries[role]={
            "operator_inferred_path_y_rotated_px":round(center,3),
            "nearest_image_ridge_index":nearest,
            "nearest_image_ridge_y_px":int(coords[nearest]),
            "geometric_offset_to_approximate_path_px":round(float(abs(coords[nearest]-center)),3),
            "within_image_roi":bool(0<=center<visual[0].shape[0]),
            "meaning":"geometric agreement with INFERRED PHYSICAL YARN path, NOT visible-pixel fiber GT"
        }
    diffs=np.diff(coords)
    spacing=float(np.median(diffs)) if len(diffs) else None
    human_intervals=ann.get("same_family_intervals")
    result=dict(status="IMAGE_RIDGES_UNVERIFIED",candidate_count=int(len(coords)),
                median_image_ridge_spacing_px=round(spacing,3) if spacing else None,
                physical_center_pixel_gt=False,
                operator_annotations="APPROXIMATE_TRUE_YARN_TRAJECTORIES_MAY_CROSS_OCCLUSION",
                approximate_path_geometry=entries,
                counts_are_hypotheses_not_real_yarn_count=True)
    if spacing is None or spacing<=0:
        return result
    for row in entries.values():
        row["distance_in_image_period_units"]=round(
            row["geometric_offset_to_approximate_path_px"]/spacing,3)
    if "reference" in entries and "check_same" in entries and human_intervals:
        r=entries["reference"]["nearest_image_ridge_index"]
        c=entries["check_same"]["nearest_image_ridge_index"]
        detected_intervals=abs(c-r)
        image_pitch=spacing
        approx_pitch=abs(entries["reference"]["operator_inferred_path_y_rotated_px"]-
                         entries["check_same"]["operator_inferred_path_y_rotated_px"])/human_intervals
        result["manual_physical_interval_count_EVALUATION_ONLY"]=human_intervals
        result["image_candidate_peak_intervals_between_inferred_tracks"]=detected_intervals
        result["candidate_interval_count_error"]=abs(detected_intervals-human_intervals)
        result["approximate_operator_pitch_px_NOT_PIXEL_GT"]=round(approx_pitch,3)
        result["candidate_pitch_relative_disagreement"]=round(
            abs(image_pitch/approx_pitch-1),3) if approx_pitch>0 else None
        result["alias_ratio_candidate_to_operator"]=round(
            image_pitch/approx_pitch,3) if approx_pitch>0 else None
    # Explicit fail-closed: a high ridge count is NOT evidence of true-yarn count.
    # Approximate paths can be shifted in image by user inference / occlusion.
    return result


def bilateral_boundary_evidence(visual,detector):
    """Verify candidate image lines have two contrasting flanks along the axis.

    This is an optical consistency diagnostic. Two-sided contrast is shared by
    some twill bands, so NO result can certify an individual physical yarn.
    """
    if visual is None or "selected_channel" not in detector:
        return {"status":"NOT_EVALUATED_NO_RIDGES","candidate_bilateral_support":[]}
    rotated,peaks,_,_=visual
    lab=cv2.cvtColor(rotated,cv2.COLOR_BGR2LAB).astype(np.float32)
    channel=lab[:,:,0] if detector["selected_channel"]=="L" else lab[:,:,2]
    layer=cv2.GaussianBlur(channel,(0,0),sigmaX=2.5,sigmaY=1.0)
    h,w=layer.shape
    xs=np.linspace(.14*w,.86*w,120,dtype=np.int32)
    side=int(max(2,min(18,round(detector["selected_cross_scale_px"]*1.0))))
    sign=1 if detector["selected_polarity"]=="light" else -1
    noise=float(np.percentile(np.abs(layer-np.median(layer)),60))
    threshold=max(.65,.10*noise)
    records=[]
    for y in peaks:
        if y-side<1 or y+side>=h-1:
            continue
        center=layer[y,xs]
        flank_a=layer[y-side,xs]
        flank_b=layer[y+side,xs]
        both=sign*(center-flank_a)
        other=sign*(center-flank_b)
        support=np.minimum(both,other)>threshold
        quarters=[float(np.mean(block)) for block in np.array_split(support,4)]
        records.append({
            "y_px":int(y),
            "two_sided_boundary_support_ratio":round(float(np.mean(support)),3),
            "supported_longitudinal_quarters":int(sum(q>.30 for q in quarters)),
            "median_two_sided_contrast":round(float(np.median(np.minimum(both,other))),3),
        })
    stable=sum(row["supported_longitudinal_quarters"]>=3
               and row["two_sided_boundary_support_ratio"]>=.36
               for row in records)
    return {
        "status":"IMAGE_BILATERAL_BOUNDARY_DIAGNOSTIC_ONLY",
        "candidate_bilateral_support":records,
        "candidate_lines_with_repeatable_paired_flanks":stable,
        "analyzed_candidate_lines":len(records),
        "physical_yarn_identity_certified":False,
        "warning":"Twill texture bands can have two-sided edges too; requires independently localized visible strand evidence.",
    }


def two_physical_yarn_anchor_hypothesis(ann,visual):
    """Optional A1+A2 physical-yarn geometry calibration, A3 strict holdout.

    Two operator-marked true-yarn trajectories and their operator-verified number
    of intervals may constrain an approximate physical pitch/phase. This is NOT
    independent recognition: all grid sites are unverified until image evidence
    finds true visible fibers; uncertain sites remain UNKNOWN.
    """
    status={"status":"ABSTAIN_NO_OPERATOR_PHYSICAL_ANCHOR_PAIR",
            "calibration_roles":["reference","check_same","same_family_intervals"],
            "holdout_role":"holdout_same",
            "physical_yarn_grid_is_not_pixel_gt":True,
            "automatic_real_yarn_count_certified":False}
    if visual is None or ann.get("same_family_intervals_confirmed") is not True:
        return status
    segments=ann["segments"]
    if not (segments.get("reference") and segments.get("check_same")
            and ann.get("same_family_intervals")):
        return status
    _,image_peaks,m,offset=visual
    a=centerline_coordinate(segments["reference"],m,offset)
    b=centerline_coordinate(segments["check_same"],m,offset)
    n=int(ann["same_family_intervals"])
    signed_pitch=(b-a)/n
    pitch=abs(signed_pitch)
    if not 6<=pitch<=130:
        status["status"]="ABSTAIN_IMPLAUSIBLE_APPROXIMATE_PHYSICAL_PITCH"
        return status
    if len(image_peaks)<4:
        status["status"]="ABSTAIN_TOO_FEW_PHOTO_CANDIDATES"
        return status
    h=visual[0].shape[0]
    kmin=int(np.ceil((3-a)/signed_pitch)) if signed_pitch>0 else int(np.ceil((h-3-a)/signed_pitch))
    kmax=int(np.floor((h-3-a)/signed_pitch)) if signed_pitch>0 else int(np.floor((3-a)/signed_pitch))
    if kmax<kmin:
        status["status"]="ABSTAIN_EMPTY_CANDIDATE_GRID"
        return status
    k=np.arange(kmin,kmax+1,dtype=int)
    targets=a+k*signed_pitch
    peaks=np.asarray(image_peaks,float)
    # Nearest ridge may be missing because the physical yarn is occluded.
    # A single ridge cannot be counted twice for neighboring target sites.
    support_tolerance=min(7.,.24*pitch)
    assignments=[]
    used=set()
    for num,target in zip(k,targets):
        nearest=int(np.argmin(abs(peaks-target)))
        err=abs(float(peaks[nearest]-target))
        supported=err<=support_tolerance and nearest not in used
        if supported:used.add(nearest)
        assignments.append({
            "physical_grid_step_index":int(num),
            "approximate_predicted_y_px":round(float(target),3),
            "closest_image_ridge_y_px":int(peaks[nearest]),
            "image_geometric_support":bool(supported),
            "ridge_alignment_residual_px":round(err,3),
            "actual_visible_yarn_confirmed":False,
        })
    result=dict(status="TWO_TRUE_YARN_ANCHOR_GRID_HYPOTHESES_NOT_VERIFIED",
                calibration_roles=["reference","check_same","same_family_intervals"],
                physical_yarn_interval_count_manual=n,
                inferred_nominal_physical_pitch_px=round(pitch,3),
                photo_candidate_pitch_not_used_for_calibration=True,
                photo_candidate_count=len(peaks),
                grid_site_count=len(assignments),
                grid_sites_near_an_image_ridge=sum(x["image_geometric_support"] for x in assignments),
                approximate_candidate_targets=assignments,
                calibration_uses_operator_inferred_trajectories_not_visible_pixel_gt=True,
                automatic_real_yarn_count_certified=False)
    holdout=segments.get("holdout_same")
    if holdout:
        y=centerline_coordinate(holdout,m,offset)
        index=int(round((y-a)/signed_pitch))
        expected=a+index*signed_pitch
        result["third_real_yarn_heldout"]={
            "operator_inferred_path_y_px":round(y,3),
            "nearest_nominal_grid_index":index,
            "nearest_nominal_grid_y_px":round(expected,3),
            "approximate_geometry_residual_px":round(abs(y-expected),3),
            "residual_as_fraction_of_nominal_pitch":round(abs(y-expected)/pitch,3),
            "was_used_to_calibrate":False,
            "warning":"Good holdout geometry does not prove photo pixels of each grid site are a visible yarn."
        }
    return result


def analyze_sample(ann,img):
    assert ann["annotation_target"]=="PHYSICAL_YARN_REFERENCE"
    ref=ann["segments"]["reference"]
    a=segment_axis_deg(ref)
    center=np.asarray(ref,float).mean(axis=0).tolist()
    detector,visual=score_profile(img,a,approximate_roi_center=center)
    boundaries=bilateral_boundary_evidence(visual,detector)
    report={
        "sample_id":ann["sample_id"],
        "annotation_target":ann["annotation_target"],
        "annotation_not_visible_segment":True,
        "annotation_path_may_cross_occlusion":True,
        "path_coordinates_are_not_precise_pixel_GT":True,
        "image_source_sha256":ann["image_sha256"],
        "step_A":{
            "operator_inferred_true_yarn_axis_deg":round(a,3),
            "direction_source":"OPERATOR_CONFIRMED_TRUE_YARN_TRAJECTORY",
            "independent_same_family_axis_error_deg":{
                role:axial_error(a,segment_axis_deg(ann["segments"][role]))
                for role in ("check_same","holdout_same")
                if ann["segments"].get(role)
            },
        },
        "step_B":{
            "status":detector["status"],
            "image_only_ridge_candidates":detector.get("image_only_candidate_ridge_count",0),
            "appearance_tuned_to_operator_pixel_line":False,
            "photo_ridge_filter_channel":detector.get("selected_channel"),
            "photo_ridge_filter_scale_px":detector.get("selected_cross_scale_px"),
            "image_support_score":detector.get("image_support_score"),
            "hypothesis_not_yarn_identity":True,
            "boundary_evidence":boundaries,
        },
        "step_C":evaluate_centers(ann,visual,detector),
        "step_C2_physical_yarn_anchor_calibration":two_physical_yarn_anchor_hypothesis(ann,visual),
        "validated_physical_yarn_center_count":None,
        "physical_yarn_recognition_accuracy":None,
        "density_per_cm":None,
        "decision":"ABSTAIN_NOT_ENOUGH_VISIBLE_YARN_PIXEL_GT",
    }
    return report,visual,detector


def write_overlay(img,ann,result,visual,out):
    # Image-only candidate projection is visually rendered alongside source image.
    render(img,ann["segments"]["reference"],result,visual,out)


def run(root:Path,out:Path):
    out.mkdir(parents=True,exist_ok=True)
    rows=[]
    for path in sorted((root/"datasets/annotations/drafts").glob(PREFIX+"*.json")):
        ann=validate_annotation(root,json.loads(path.read_text(encoding="utf-8")))
        if ann["review_state"]!="OPERATOR_REVIEWED":
            continue
        raw=(root/ann["image_path"]).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=ann["image_sha256"]:
            raise RuntimeError("annotation image checksum mismatch")
        image=cv2.imdecode(np.frombuffer(raw,np.uint8),cv2.IMREAD_COLOR)
        if image is None or list(image.shape[1::-1])!=[ann["image_width"],ann["image_height"]]:
            raise RuntimeError("zoom native pixel coordinates not matched")
        report,visual,detector=analyze_sample(ann,image)
        rows.append(report)
        write_overlay(image,ann,detector,visual,out/(ann["sample_id"]+".jpg"))
        e=report["step_C"]
        print(f'{ann["sample_id"]} status={report["decision"]} '
              f'candidate_ridges={report["step_B"]["image_only_ridge_candidates"]} '
              f'geometry_interval_error={e.get("candidate_interval_count_error")} '
              f'paired_flank_candidates={report["step_B"]["boundary_evidence"].get("candidate_lines_with_repeatable_paired_flanks")} '
              f'calibrated_photo_sites={report["step_C2_physical_yarn_anchor_calibration"].get("grid_sites_near_an_image_ridge")} '
              f'operator_pitch={e.get("approximate_operator_pitch_px_NOT_PIXEL_GT")}',flush=True)
    summary={
        "baseline_main":"e1b219384224e1d77c79aa108bef3fb51a39ea56",
        "annotation_target":"PHYSICAL_YARN_REFERENCE",
        "steps":["A: human physical-yarn orientation","B: independent photo ridges",
                 "C: approximate yarn-path geometric agreement and alias risk"],
        "number_reviewed":len(rows),
        "physical_yarn_per_pixel_accuracy_evaluable":False,
        "real_yarn_count_evaluable":False,
        "results":rows,
        "qualification":"Human path is inferred across occlusion. This evaluation cannot certify every candidate stripe as a physical yarn."
    }
    (out/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    if len(rows)!=5:
        raise RuntimeError(f"Expected five reviewed physical-yarn trajectory samples, got {len(rows)}")
    return summary


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=ROOT)
    p.add_argument("--out",type=Path,default=Path("experiments/first-yarn-3stage"))
    args=p.parse_args()
    root=args.root.resolve()
    folder=args.out if args.out.is_absolute() else root/args.out
    run(root,folder)


if __name__=="__main__":
    main()
