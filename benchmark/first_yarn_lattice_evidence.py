"""First-yarn A1+A2 pitch lattice with MULTI-WINDOW PHOTO EVIDENCE.

Labels are PHYSICAL_YARN_REFERENCE: one two-point mark = one REAL physical yarn
whose extrapolated path can cross interlacing occlusion, NOT a visible pixel mask.
A1 chooses image orientation/ROI; A2 + operator-confirmed *number of intervals*
sets nominal pitch/phase. A3 and B are NOT read by infer_lattice, ever.
Each nominal site remains an unverified physical-yarn HYPOTHESIS even when image
texture supports it: twill bands can produce the same optical signals.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np

from benchmark.direction_only_first_yarn import oriented_ridge, score_profile
from benchmark.manual_annotation import segment_axis_deg, validate_annotation

ROOT = Path(__file__).resolve().parents[1]


def project_y(segment, affine, crop_origin):
    raw=np.asarray(segment,float)-np.asarray(crop_origin,float)
    return float(np.mean(cv2.transform(raw.reshape(1,2,2),affine)[0,:,1]))


def image_band(rotated, detector):
    lab=cv2.cvtColor(rotated,cv2.COLOR_BGR2LAB).astype(np.float32)
    ch=lab[:,:,0 if detector["selected_channel"]=="L" else 2]
    scale=float(detector["selected_cross_scale_px"])
    polarity=1 if detector["selected_polarity"]=="light" else -1
    response=oriented_ridge(ch,scale)*polarity
    norm=float(np.percentile(abs(response-np.median(response)),75))
    return response/max(.6,norm),scale


def infer_lattice(image, ann, *, prepared=None):
    """Only A1 + A2 + operator-confirmed A1/A2 intervals enter inference.

    prepared=(image-only detector, rotation result) is for synthetic testing.
    An image ridge can support a SITE, not certify a physical yarn identity.
    """
    base={"status":"ABSTAIN", "annotation_target":"PHYSICAL_YARN_REFERENCE",
          "calibration_roles":["reference","check_same","same_family_intervals"],
          "excluded_test_role":"holdout_same",
          "verified_real_yarn_count":None, "verified_real_yarn_trajectories":None,
          "warp_weft_identity":"UNKNOWN","density_per_cm":None,
          "pixel_centerline_ground_truth":False}
    if ann.get("annotation_target")!="PHYSICAL_YARN_REFERENCE":
        return {**base,"status":"ABSTAIN_INCORRECT_LABEL_SEMANTICS"},None
    s=ann["segments"]
    intervals=ann.get("same_family_intervals")
    if (not s.get("reference") or not s.get("check_same")
            or ann.get("same_family_intervals_confirmed") is not True
            or type(intervals) is not int or not 1<=intervals<=200):
        return {**base,"status":"ABSTAIN_UNCONFIRMED_DISTINCT_PHYSICAL_ANCHORS"},None
    axis=segment_axis_deg(s["reference"])
    if prepared is None:
        detector,visual=score_profile(
            image,axis,approximate_roi_center=np.asarray(s["reference"],float).mean(axis=0).tolist())
    else:
        detector,visual=prepared
    if visual is None or detector["status"]!="IMAGE_TEXTURE_RIDGE_CANDIDATES_REQUIRE_YARN_CONFIRMATION":
        return {**base,"status":"ABSTAIN_NO_IMAGE_RIDGES"},visual
    rotated,_,affine,origin=visual
    y1=project_y(s["reference"],affine,origin)
    y2=project_y(s["check_same"],affine,origin)
    signed=(y2-y1)/intervals
    pitch=abs(signed)
    # 2x interpolated photo => real camera sampling pitch is half this number.
    if not 10<=pitch<=130:
        return {**base,"status":"ABSTAIN_INSUFFICIENT_NATIVE_PITCH_RESOLUTION",
                "pitch_2x_px":round(pitch,3),"pitch_original_px":round(pitch/2,3)},visual
    response,scale=image_band(rotated,detector)
    h,w=response.shape
    # The legacy rectifier fills rotated corners by reflected pixels. Those
    # replicas are NOT actual field of view: forbid counting them as evidence.
    side_len=min(1100,image.shape[0],image.shape[1])
    ox,oy=np.rint(np.asarray(origin,float)).astype(int)
    original_roi=image[oy:oy+side_len,ox:ox+side_len]
    if original_roi.shape[:2]!=(side_len,side_len):
        raise ValueError("native source crop and affine provenance mismatch")
    mask=cv2.warpAffine(np.ones(original_roi.shape[:2],np.uint8),affine,(w,h),
                        flags=cv2.INTER_NEAREST,borderMode=cv2.BORDER_CONSTANT,
                        borderValue=0).astype(bool)
    sites=[]
    for k in range(-200,201):
        y=y1+k*signed
        if 20<=y<h-20:
            sites.append((k,float(y)))
    if not sites or len(sites)>130:
        return {**base,"status":"ABSTAIN_INVALID_LATTICE_EXTENT"},visual
    # Nine independent longitudinal windows; fixed settings across all fabrics.
    cx=np.linspace(.25*w,.75*w,9)
    xidx=np.rint(cx).astype(int)
    sites=[(k,y) for k,y in sites if
           sum(bool(mask[int(round(y)),x]) for x in xidx)>=6]
    if len(sites)<4:
        return {**base,"status":"ABSTAIN_INSUFFICIENT_UNREFLECTED_PHOTO_COVERAGE"},visual
    half=max(8,int(.03*w))
    profiles=[]
    for x in cx:
        lo=max(0,int(x)-half);hi=min(w,int(x)+half)
        profiles.append(np.median(response[:,lo:hi],axis=1))
    profiles=np.asarray(profiles)
    radius=int(np.clip(round(pitch*.23),2,11))
    side=int(np.clip(round(scale),2,max(3,pitch*.35)))

    # Search a SMALL global offset for approximate A1/A2 hand-drawn paths.
    # Objective is unsupervised PHOTO contrast, never the withheld A3 position.
    # A twill pattern could also maximize this; ambiguity must be explicit.
    shifts=np.linspace(-.20*pitch,.20*pitch,11)
    def photo_phase_objective(shift):
        values=[]
        for _,base_y in sites:
            center=int(round(base_y+shift))
            if center-side-2<0 or center+side+2>=h:
                continue
            for prof in profiles:
                yc=int(np.clip(center,2,h-3))
                loc=prof[yc-2:yc+3]
                if not len(loc):
                    continue
                peak_y=yc-2+int(np.argmax(loc))
                peak_val=float(prof[peak_y])
                paired=min(peak_val-float(prof[peak_y-side]),
                           peak_val-float(prof[peak_y+side]))
                values.append(min(1.,max(0.,peak_val-.30)) *
                              min(1.,max(0.,paired-.16)))
        return float(np.mean(values)) if values else 0.
    phase_scores=[photo_phase_objective(float(shift)) for shift in shifts]
    winner=int(np.argmax(phase_scores))
    best_delta=float(shifts[winner])
    best_quality=phase_scores[winner]
    baseline_quality=phase_scores[len(shifts)//2]
    competitors=[score for i,score in enumerate(phase_scores)
                 if abs(shifts[i]-best_delta)>=.12*pitch]
    competing=max(competitors) if competitors else 0.
    distinguishable=(best_quality>0.015 and
                     best_quality-competing>=max(.005,best_quality*.09))
    gain=best_quality-baseline_quality
    applied_shift=(best_delta if distinguishable and gain>=.007
                   and abs(best_delta)<=.2*pitch else 0.)
    # All grid indices remain anchored to A1/A2, with a bounded image-only
    # phase correction. Neither A3 nor B labels enter this selection.
    sites=[(k,y+applied_shift) for k,y in sites]
    records=[]
    for k,target in sites:
        measurements=[]
        for x,profile in zip(cx,profiles):
            ix=int(round(x))
            if not mask[int(np.clip(round(target),0,h-1)),ix]:
                continue
            low=max(2,round(target)-radius);high=min(h-3,round(target)+radius)
            if high<low:continue
            ii=np.arange(low,high+1)
            py=int(ii[np.argmax(profile[ii])])
            val=float(profile[py])
            flank=float(min(val-profile[py-side],val-profile[py+side]))
            measurements.append({"x":round(float(x),1),"y":py,
                                 "ridge_score":round(val,3),
                                 "paired_flank_score":round(flank,3),
                                 "supported":bool(val>.3 and flank>.16)})
        observed=[m for m in measurements if m["supported"]]
        # Local yarn tracks may lean a few degrees after reference rotation:
        # distinguish smooth linear drift from discontinuous texture jumping.
        slope_deg=None
        spread=None
        if len(observed)>=4:
            xs=np.asarray([m["x"] for m in observed],float)
            ys=np.asarray([m["y"] for m in observed],float)
            gradient,intercept=np.polyfit(xs,ys,1)
            slope_deg=float(np.degrees(np.arctan(gradient)))
            spread=float(np.std(ys-(gradient*xs+intercept)))
        quartiles=len({min(3,int(i*4/max(1,len(measurements))))
                       for i,m in enumerate(measurements) if m["supported"]})
        supported=bool(len(observed)>=6 and quartiles>=3 and
                       spread is not None and spread<=max(2.5,pitch*.12)
                       and slope_deg is not None and abs(slope_deg)<=8)
        records.append({
            "nominal_physical_yarn_index":int(k),
            "nominal_y_2x_px":round(target,3),
            "longitudinal_windows_supported":len(observed),
            "independent_image_quarters_supported":quartiles,
            "linear_drift_corrected_center_jitter_2x_px":round(spread,3) if spread is not None else None,
            "local_image_track_tilt_deg":round(slope_deg,3) if slope_deg is not None else None,
            "image_evidence_supported":supported,
            "confirmed_actual_physical_yarn":False,
            "local_observations":measurements})
    supported=sum(r["image_evidence_supported"] for r in records)
    # The image may refine the A1 angle ONLY when many independent strips agree.
    # This candidate is not an autonomous yarn-angle ground truth.
    angles=[r["local_image_track_tilt_deg"] for r in records
            if r["image_evidence_supported"] and r["local_image_track_tilt_deg"] is not None]
    if len(angles)>=8:
        angle_delta=float(np.median(angles))
        angle_mad=float(np.median(np.abs(np.asarray(angles)-angle_delta)))
        angle_candidate=(round((axis+angle_delta)%180,3)
                         if angle_mad<=1.25 and abs(angle_delta)<=6 else None)
    else:
        angle_delta=None
        angle_mad=None
        angle_candidate=None
    coverage=supported/len(records)
    status=("IMAGE_SUPPORTED_PHYSICAL_LATTICE_HYPOTHESIS_NOT_IDENTIFIED_YARNS"
            if coverage>=.6 and supported>=8
            else "ABSTAIN_UNSTABLE_IMAGE_SUPPORT")
    result={**base,"status":status,"operator_direction_axis_deg":round(float(axis),3),
            "image_assisted_axis_candidate_deg_UNVERIFIED":angle_candidate,
            "image_track_tilt_consensus_deg":round(angle_delta,3) if angle_delta is not None else None,
            "image_track_tilt_mad_deg":round(angle_mad,3) if angle_mad is not None else None,
            "image_assisted_angle_is_confirmed_real_yarn":False,
            "nominal_physical_pitch_2x_px":round(pitch,3),
            "nominal_physical_pitch_camera_original_px":round(pitch/2,3),
            "photo_only_phase_refinement_applied_2x_px":round(applied_shift,3),
            "photo_only_phase_refinement_disambiguated":bool(distinguishable),
            "photo_phase_best_support_score":round(best_quality,5),
            "photo_phase_baseline_support_score":round(baseline_quality,5),
            "photo_phase_runner_up_score":round(competing,5),
            "photo_phase_candidates_tested":len(shifts),
            "manual_A3_used_for_phase_search":False,
            "rotated_reflected_border_excluded":True,
            "calibration_y1_y2_2x_px":[round(y1,3),round(y2,3)],
            "confirmed_A1_A2_intervals_used_for_calibration":intervals,
            "real_yarn_count_between_A1_A2_FROM_HUMAN_INTERVALS_ONLY":intervals+1,
            "manual_span_count_is_not_automated_full_roi_yarn_count":True,
            "nominal_lattice_site_count_NOT_actual_yarn_count":len(records),
            "longitudinal_image_supported_site_count_NOT_actual_yarn_count":supported,
            "supported_site_fraction":round(coverage,4),
            "photo_channel":detector["selected_channel"],
            "photo_filter_scale_2x_px":detector["selected_cross_scale_px"],
            "photo_polarity":detector["selected_polarity"],
            "sites":records,
            "limitations":["Dark/light weave texture can mimic the physical lattice.",
                           "A1/A2 are approximate physical trajectories, not pixel centers.",
                           "Photo enlargement adds no native camera resolution.",
                           "No verified real-yarn roots or roots/cm from this experiment."]}
    return result,visual


def check_a3_holdout(ann,inferred,visual):
    """Read A3 ONLY after inference completes; no model, pitch or phase updates."""
    if not ann["segments"].get("holdout_same") or not inferred.get("sites") or visual is None:
        return {"status":"NOT_EVALUATED","used_for_calibration":False}
    _,_,affine,origin=visual
    y=project_y(ann["segments"]["holdout_same"],affine,origin)
    choice=min(inferred["sites"],key=lambda site:abs(site["nominal_y_2x_px"]-y))
    pitch=float(inferred["nominal_physical_pitch_2x_px"])
    residual=abs(choice["nominal_y_2x_px"]-y)
    return {"status":"APPROXIMATE_GEOMETRY_MATCH" if residual<=.25*pitch
                     else "APPROXIMATE_GEOMETRY_MISMATCH",
            "evaluation_role":"A3_SEPARATE_REAL_PHYSICAL_YARN",
            "used_for_calibration":False,"evaluation_is_pixel_GT":False,
            "nearest_lattice_index":choice["nominal_physical_yarn_index"],
            "holdout_residual_2x_px":round(residual,3),
            "holdout_residual_fraction_pitch":round(residual/pitch,3),
            "image_support_at_nearest_site":choice["image_evidence_supported"],
            "real_physical_yarn_image_identity_verified":False}


def experiment(root,out):
    out.mkdir(parents=True,exist_ok=True)
    results=[]
    for file in sorted((root/"datasets/annotations/drafts").glob("U20261013_*.json")):
        ann=validate_annotation(root,json.loads(file.read_text(encoding="utf-8")))
        if ann["review_state"]!="OPERATOR_REVIEWED":continue
        source=(root/ann["image_path"]).read_bytes()
        if hashlib.sha256(source).hexdigest()!=ann["image_sha256"]:
            raise RuntimeError("source photo hash mismatch")
        photo=cv2.imdecode(np.frombuffer(source,np.uint8),cv2.IMREAD_COLOR)
        if photo is None or (photo.shape[1],photo.shape[0])!=(ann["image_width"],ann["image_height"]):
            raise RuntimeError("native 2x photo coordinates mismatch")
        inferred,visual=infer_lattice(photo,ann)
        a3=check_a3_holdout(ann,inferred,visual)
        results.append({"sample_id":ann["sample_id"],"stage_D":inferred,
                        "independent_A3_heldout":a3,
                        "certified_yarn_count":None,"density_per_cm":None})
        if visual is not None:
            image=visual[0].copy()
            for r in inferred.get("sites",[]):
                y=round(r["nominal_y_2x_px"])
                color=(0,210,35) if r["image_evidence_supported"] else (0,95,245)
                cv2.line(image,(0,y),(image.shape[1]-1,y),color,1,cv2.LINE_AA)
            factor=min(1.0,1150/image.shape[1])
            if factor<1:image=cv2.resize(image,None,fx=factor,fy=factor,interpolation=cv2.INTER_AREA)
            cv2.imwrite(str(out/(ann["sample_id"]+"_nominal_yarn_lattice.jpg")),image)
        print(f'{ann["sample_id"]} lattice={inferred["status"]} '
              f'supported={inferred.get("longitudinal_image_supported_site_count_NOT_actual_yarn_count")}/'
              f'{inferred.get("nominal_lattice_site_count_NOT_actual_yarn_count")} '
              f'A3={a3.get("holdout_residual_fraction_pitch")} '
              f'photo_phase_shift={inferred.get("photo_only_phase_refinement_applied_2x_px")} '
              f'image_angle={inferred.get("image_assisted_axis_candidate_deg_UNVERIFIED")}',flush=True)
    meta={"annotation_semantics":"PHYSICAL_YARN_REFERENCE","samples_evaluated":len(results),
          "image_evidence_is_not_yarn_identity_proof":True,
          "physical_yarn_count_accuracy_evaluable":False,"results":results}
    (out/"summary.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    if len(results)<5:raise RuntimeError("Missing operator-reviewed samples")
    return meta


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--root",type=Path,default=ROOT)
    parser.add_argument("--out",type=Path,default=Path("experiments/first-yarn-lattice"))
    args=parser.parse_args()
    root=args.root.resolve()
    out=args.out if args.out.is_absolute() else root/args.out
    experiment(root,out)


if __name__=="__main__":
    main()
