"""P0-E5: zero-tune exploratory CROSS-FABRIC optical crossing phase diagnostic.

A physical yarn crossing cannot be proven from RGB alone. We test whether B
orientation energy is systematically different at predicted A/B intersections
versus midperiod locations on the operator A1 *reference trajectory*. A1/B1/B2
are image-registered human geometry; A3 is excluded. No operator local labels
enter the feature calculation. All shifted controls have UNKNOWN physical class.

No training or cutoffs; no retuning using U06 (additional fabric/photo).
E5 was designed *after* the U06 labels became available, so U06 is NOT a
preregistered blind test or independent holdout.
Native original camera pixels only; zoom image is coordinate provenance.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import cv2
import numpy as np

from benchmark.local_image_review import load_local_review
from benchmark.p0_occlusion_continuity import calibration_fields, unit
from benchmark.p0_operator_line_audit import _camera_image, convert_zoom_to_camera

ROOT = Path(__file__).resolve().parents[1]


def predicted_crossing_centers(A1_camera, calib):
    """Image-geometry lattice; DOES NOT know actual over/under crossings."""
    ends = np.asarray(A1_camera,dtype=float)
    a,b=ends
    t=unit(b-a)
    nb=calib["B_normal"]
    origin=calib["B_origin"]
    signed_pitch=float(calib["B_pitch_signed"])
    rate=float(np.dot(t,nb)/signed_pitch)
    if abs(rate)<1e-8:
        return []
    period_a=1.0/abs(rate)
    q0=float(np.dot(a-origin,nb)/signed_pitch)
    q1=float(np.dot(b-origin,nb)/signed_pitch)
    lo,hi=min(q0,q1),max(q0,q1)
    result=[]
    # Include crossing sites only if the full 50%-period comparison fits
    # within the *already marked* A1 reference span, avoiding extrapolation.
    for k in range(math.ceil(lo),math.floor(hi)+1):
        distance=(k-q0)/rate
        if not 0<=distance<=float(np.linalg.norm(b-a)):
            continue
        mid=distance+.5*period_a
        if not 0<=mid<=float(np.linalg.norm(b-a)):
            mid=distance-.5*period_a
        if not 0<=mid<=float(np.linalg.norm(b-a)):
            continue
        result.append({
            "B_lattice_index_NOT_verified_crossing":k,
            "predicted_camera_xy":(a+distance*t).tolist(),
            "midperiod_camera_xy":(a+mid*t).tolist(),
            "A_axis_period_camera_px":float(period_a),
        })
    return result


def oriented_energy_maps(image, tA, tB):
    """Native-pixel Sobel gradient energy along both yarn-family normals."""
    lab=cv2.cvtColor(image,cv2.COLOR_BGR2LAB).astype(np.float32)
    L=lab[:,:,0]
    gx=cv2.Sobel(L,cv2.CV_32F,1,0,ksize=3)
    gy=cv2.Sobel(L,cv2.CV_32F,0,1,ksize=3)
    tA=unit(tA)
    tB=unit(tB)
    na=np.array([-tA[1],tA[0]],float)
    nb=np.array([-tB[1],tB[0]],float)
    Ea=((gx*na[0]+gy*na[1])**2).astype(np.float32)
    Eb=((gx*nb[0]+gy*nb[1])**2).astype(np.float32)
    return Ea,Eb


def local_dominance(Ea, Eb, center, tangent, camera_A_pitch, period_on_A):
    """Dimensionless fixed aperture relative to A/B yarn spacing.

    An unresolved aperture is missing evidence, not negative evidence.
    """
    h,w=Ea.shape
    center=np.asarray(center,dtype=float)
    t=unit(tangent)
    n=np.array([-t[1],t[0]],float)
    long=np.linspace(-.16*period_on_A,.16*period_on_A,17)
    wide=np.linspace(-.25*camera_A_pitch,.25*camera_A_pitch,13)
    x=center[0]+long[:,None]*t[0]+wide[None,:]*n[0]
    y=center[1]+long[:,None]*t[1]+wide[None,:]*n[1]
    if np.min(x)<2 or np.max(x)>w-3 or np.min(y)<2 or np.max(y)>h-3:
        return None
    mx,my=x.astype(np.float32),y.astype(np.float32)
    va=cv2.remap(Ea,mx,my,cv2.INTER_LINEAR)
    vb=cv2.remap(Eb,mx,my,cv2.INTER_LINEAR)
    aa=float(np.mean(va))
    bb=float(np.mean(vb))
    if (aa+bb)<=1.e-10:
        return None
    return {
        "A_gradient_energy":round(aa,5),
        "B_gradient_energy":round(bb,5),
        "B_minus_A_normalized":round((bb-aa)/(bb+aa),5),
    }


def sample_crossing_phase(photo, A1_camera, calib):
    """Shared rule/aperture for 01/03/06, no thresholds fitted to U06."""
    A1=np.asarray(A1_camera,float)
    ta=unit(A1[1]-A1[0])
    Ea,Eb=oriented_energy_maps(photo,ta,calib["B_tangent"])
    na=calib["normal"]
    sites=predicted_crossing_centers(A1,calib)
    output=[]
    for site in sites:
        p=np.asarray(site["predicted_camera_xy"],float)
        m=np.asarray(site["midperiod_camera_xy"],float)
        controls=[]
        for offset in (0.,-.5,.5):
            shift=offset*float(calib["pitch"])*na
            c=local_dominance(Ea,Eb,p+shift,ta,calib["pitch"],
                              site["A_axis_period_camera_px"])
            half=local_dominance(Ea,Eb,m+shift,ta,calib["pitch"],
                                 site["A_axis_period_camera_px"])
            controls.append({
                "transverse_offset_in_A_yarn_pitch":offset,
                "at_predicted_B_lattice_location":c,
                "at_midperiod_photo_control":half,
                "difference_B_dominance_predicted_minus_mid":
                   round(c["B_minus_A_normalized"]-half["B_minus_A_normalized"],5)
                   if c is not None and half is not None else None,
                "physical_class_of_both_locations":"UNKNOWN",
            })
        output.append({**site,"offset_A_pitch_controls":controls,
                       "B_lattice_site_is_verified_occlusion":False})
    def agg(index):
        values=[x["offset_A_pitch_controls"][index]["difference_B_dominance_predicted_minus_mid"]
                for x in output]
        good=[x for x in values if x is not None]
        return {"available_sites":len(good),
                "median_B_dominance_phase_difference":
                    round(float(np.median(good)),5) if good else None,
                "median_absolute_phase_change_SIGN_INVARIANT":
                    round(float(np.median(np.abs(good))),5) if good else None,
                "fraction_positive_phase_difference_NOT_ACCURACY":
                    round(float(np.mean(np.array(good)>0)),4) if good else None}
    a,b,c=agg(0),agg(1),agg(2)
    if all(x["median_absolute_phase_change_SIGN_INVARIANT"] is not None
           for x in (a,b,c)):
        excess=round(a["median_absolute_phase_change_SIGN_INVARIANT"]-max(
            b["median_absolute_phase_change_SIGN_INVARIANT"],
            c["median_absolute_phase_change_SIGN_INVARIANT"]),5)
    else:
        excess=None
    return {"sites":output,
            "summary_A1_operator_reference":a,
            "summary_unlabelled_half_A_pitch_minus":b,
            "summary_unlabelled_half_A_pitch_plus":c,
            "sign_invariant_phase_change_excess_over_both_UNLABELLED_offsets":excess,
            "sign_invariant_excess_NOT_proof_of_physical_yarn":True,
            "crossing_over_under_verified":False,
            "actual_physical_same_yarn_verified":False}


def fixed_phase_sensitivity_audit(photo,A1_camera,calib):
    """A pre-specified ±quarter/half B period *stress test*, not phase fitting.

    This evaluates sensitivity to reference-line placement. NEVER return an
    optimal offset or feed phase scan scores back into inference; a negative
    result at zero can reflect a shifted manual phase rather than different
    physics. Use identical fixed fractions across all fabrics.
    """
    fractions=(-.5,-.25,0.,.25,.5)
    sweep=[]
    for fraction in fractions:
        moved={**calib,
            "B_origin":np.asarray(calib["B_origin"],float)+
                        float(fraction)*float(calib["B_pitch_signed"])*calib["B_normal"]}
        r=sample_crossing_phase(photo,A1_camera,moved)
        stat=r["summary_A1_operator_reference"]
        sweep.append({
            "phase_shift_in_B_periods":fraction,
            "available_optical_windows":stat["available_sites"],
            "median_B_dominance_phase_difference_NOT_GT":
                stat["median_B_dominance_phase_difference"],
            "proves_B_over_A":False,
        })
    valid=[x["median_B_dominance_phase_difference_NOT_GT"]
           for x in sweep if x["median_B_dominance_phase_difference_NOT_GT"] is not None]
    return {
        "preselected_symmetric_fractions":list(fractions),
        "no_parameter_optimization_or_phase_selection":True,
        "curve":sweep,
        "phase_sign_invariant_across_test_offsets":
            (all(x>0 for x in valid) or all(x<0 for x in valid))
             if len(valid)==len(fractions) else None,
        "spread_max_minus_min":round(max(valid)-min(valid),5) if valid else None,
        "actual_physical_crossing_certified":False,
    }


def render_phase_overlay(photo,A1_camera,phase,out):
    img=photo.copy()
    a,b=np.rint(np.asarray(A1_camera)).astype(int)
    cv2.line(img,tuple(a),tuple(b),(0,220,30),2,cv2.LINE_AA)
    for row in phase["sites"]:
        p=tuple(np.rint(row["predicted_camera_xy"]).astype(int))
        m=tuple(np.rint(row["midperiod_camera_xy"]).astype(int))
        cv2.circle(img,p,5,(0,180,255),2,cv2.LINE_AA)
        cv2.circle(img,m,3,(225,190,10),1,cv2.LINE_AA)
    h,w=img.shape[:2]
    factor=min(1.,1500/max(w,h))
    if factor<1:img=cv2.resize(img,None,fx=factor,fy=factor,interpolation=cv2.INTER_AREA)
    cv2.imwrite(str(out),img)


def run(root, out, ids=("U20261013_01","U20261013_03","U20261013_06")):
    out.mkdir(parents=True,exist_ok=True)
    report={
        "experiment":"P0_E5_CROSS_FABRIC_B_PHASE_OPTICAL_STRESS",
        "E5_procedure_designed_after_U06_labels_visible_NOT_A_BLIND_HOLDOUT":True,
        "U06_labels_not_used_for_parameter_optimization":True,
        "training_or_parameter_fitting":False,
        "optical_indicator_cannot_certify_physical_occlusion":True,
        "physical_yarn_identity_accuracy":None,
        "A3_used":False,
        "U06_has_no_same_yarn_relations_cannot_test_link_accuracy":True,
        "samples":[],
    }
    for sid in ids:
        review=load_local_review(root,sid)
        ref=json.loads((root/"datasets/annotations/drafts"/(sid+".json")).read_text(encoding="utf-8"))
        photo,provenance=_camera_image(root,review)
        calib=calibration_fields(ref,provenance["crop_original_xyxy"][:2])
        A1_camera=convert_zoom_to_camera(ref["segments"]["reference"],
                   provenance["crop_original_xyxy"],provenance["enlargement_scale"])
        phase=sample_crossing_phase(photo,A1_camera,calib)
        sensitivity=fixed_phase_sensitivity_audit(photo,A1_camera,calib)
        result={
            "sample_id":sid,"image_sha256":review["image_sha256"],
            "operator_review_state":review["review_state"],
            "camera_A_pitch_px":round(float(calib["pitch"]),3),
            "camera_B_pitch_px":round(abs(float(calib["B_pitch_signed"])),3),
            "camera_A_axis_angle_deg":round(
                math.degrees(math.atan2(calib["tangent"][1],calib["tangent"][0]))%180,3),
            "visible_operator_fragments":sum(x["kind"]=="APPARENT_VISIBLE_YARN" for x in review["regions"]),
            "operator_false_tracks":sum(x["kind"]=="TWILL_PATTERN" for x in review["regions"]),
            "manual_same_relations_NEVER_USED_IN_PROBE":len(review["relations"]),
            "predicted_B_sites_NOT_verified_crossing_count":len(phase["sites"]),
            "operator_A1_photo_phase":phase["summary_A1_operator_reference"],
            "A1_sign_invariant_excess_over_unlabelled_half_pitch_controls":
                phase["sign_invariant_phase_change_excess_over_both_UNLABELLED_offsets"],
            "fixed_phase_sensitivity_NO_TUNING":sensitivity,
            "unlabelled_control_minus_half_A_pitch":phase["summary_unlabelled_half_A_pitch_minus"],
            "unlabelled_control_plus_half_A_pitch":phase["summary_unlabelled_half_A_pitch_plus"],
            "physical_crossing_verified":False,
            "physical_identity_accuracy":None,
        }
        report["samples"].append(result)
        with (out/(sid+"_phase_sites.json")).open("w",encoding="utf-8") as f:
            json.dump({"sample":result,"sites":phase["sites"]},f,ensure_ascii=False,indent=2)
        with (out/(sid+"_phase_sites.csv")).open("w",encoding="utf-8",newline="") as f:
            writer=csv.DictWriter(f,fieldnames=["B_index","offset_in_A_pitch",
                "B_minus_A_at_predicted","B_minus_A_at_midperiod",
                "phase_difference","physical_class"])
            writer.writeheader()
            for site in phase["sites"]:
                for control in site["offset_A_pitch_controls"]:
                    center=control["at_predicted_B_lattice_location"]
                    mid=control["at_midperiod_photo_control"]
                    writer.writerow({"B_index":site["B_lattice_index_NOT_verified_crossing"],
                        "offset_in_A_pitch":control["transverse_offset_in_A_yarn_pitch"],
                        "B_minus_A_at_predicted":center["B_minus_A_normalized"] if center else "",
                        "B_minus_A_at_midperiod":mid["B_minus_A_normalized"] if mid else "",
                        "phase_difference":control["difference_B_dominance_predicted_minus_mid"],
                        "physical_class":"UNKNOWN"})
        with (out/(sid+"_phase_sensitivity.csv")).open("w",encoding="utf-8",newline="") as f:
            writer=csv.DictWriter(f,fieldnames=[
                "phase_shift_in_B_periods",
                "available_optical_windows",
                "median_B_dominance_phase_difference_NOT_GT",
                "proves_B_over_A"])
            writer.writeheader()
            writer.writerows(sensitivity["curve"])
        render_phase_overlay(photo,A1_camera,phase,out/(sid+"_expected_B_phase_NOT_OCCLUSION_GT.jpg"))
        print(f'{sid} E5 A1_axis={result["camera_A_axis_angle_deg"]} A_pitch='
              f'{result["camera_A_pitch_px"]} B_pitch={result["camera_B_pitch_px"]} '
              f'sites={len(phase["sites"])} matched_native_windows='
              f'{phase["summary_A1_operator_reference"]["available_sites"]} '
              f'A1_median_phase={phase["summary_A1_operator_reference"]["median_B_dominance_phase_difference"]} '
              f'half_shift_median='
              f'{phase["summary_unlabelled_half_A_pitch_minus"]["median_B_dominance_phase_difference"]}/'
              f'{phase["summary_unlabelled_half_A_pitch_plus"]["median_B_dominance_phase_difference"]}'
              f' phase_shift_stable={sensitivity["phase_sign_invariant_across_test_offsets"]} '
              f'phase_shift_spread={sensitivity["spread_max_minus_min"]} '
              f'sign_invariant_specificity_excess='
              f'{phase["sign_invariant_phase_change_excess_over_both_UNLABELLED_offsets"]}'
              f' (OPTICAL_ONLY_NO_PHYSICAL_OCCLUSION_GT)',flush=True)
    (out/"summary.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return report


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=ROOT)
    p.add_argument("--out",type=Path,default=Path("experiments/p0-e5-cross-fabric-phase"))
    a=p.parse_args()
    run(a.root.resolve(),(a.out if a.out.is_absolute() else a.root.resolve()/a.out))


if __name__=="__main__":
    main()
