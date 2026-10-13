"""E6 V5-inspired multi-transect photo evidence, not a yarn identity detector.

Borrow V5's multiple cross-section idea, NOT its V4 track coordinates or
hand-tuned phase. Each operator LINE is ONE linked candidate track, even when
it has five correlated transverse photo cuts. E3 matched fake photo lines are
cropped to the same camera length and nearby location as the positive line.

A ridge in all cuts can ALSO belong to colored, printed, shadow or twill
textures. Therefore neither positive responses nor profile stability can
certify a real physical strand or occlusion topology.
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
from benchmark.p0_operator_line_audit import (
    _camera_image, convert_zoom_to_camera, connected_positive_groups,
    nearest_length_matched_twill_pairs, summarize_sample,
)
from benchmark.p0_occlusion_continuity import calibration_fields

ROOT=Path(__file__).resolve().parents[1]
CUT_FRACTIONS=(.15,.325,.5,.675,.85)
CUT_POINTS=25
# A cross-section follows a half yarn-period per side, independent of image
# resolution; 25 interpolation samples DO NOT CREATE 25 optical observations.


def photo_transverse_cuts(image, endpoints, pitch, fractions=CUT_FRACTIONS):
    """Return raw luminance transects or None near borders / bad geometry."""
    pts=np.asarray(endpoints,dtype=float)
    if pts.shape!=(2,2) or not np.isfinite(pts).all() or pitch<=0:
        return None
    v=pts[1]-pts[0]
    length=float(np.linalg.norm(v))
    if length <= 0:
        return None
    t=v/length
    n=np.array([-t[1],t[0]])
    offsets=np.linspace(-.5*pitch,.5*pitch,CUT_POINTS)
    centers=[pts[0]+float(q)*v for q in fractions]
    xx=np.array([p[0]+offsets*n[0] for p in centers],np.float32)
    yy=np.array([p[1]+offsets*n[1] for p in centers],np.float32)
    h,w=image.shape[:2]
    if np.min(xx)<1 or np.max(xx)>=w-2 or np.min(yy)<1 or np.max(yy)>=h-2:
        return None
    L=cv2.cvtColor(image,cv2.COLOR_BGR2LAB)[:,:,0].astype(np.float32)
    profile=cv2.remap(L,xx,yy,cv2.INTER_LINEAR)
    return profile


def characterize_cuts(cuts):
    """Polarity-agnostic center-vs-flank morphology, dimensionless.

    We cannot infer that a bright or dark luma stripe is an actual yarn.
    Reject completely flat cuts as UNRESOLVED; centerline may be in yarn gap.
    """
    if cuts is None:
        return {"state":"UNRESOLVED","reason":"MISSING_NATIVE_CUTS",
                "number_of_CORRELATED_transects":0}
    cuts=np.asarray(cuts,float)
    if cuts.ndim!=2 or cuts.shape[1]!=CUT_POINTS:
        raise ValueError("expected transverse strip of 25 normal-direction samples")
    middle=np.mean(cuts[:,11:14],axis=1)
    left=np.mean(cuts[:,4:7],axis=1)
    right=np.mean(cuts[:,18:21],axis=1)
    contrast=middle-.5*(left+right)
    sigma=np.std(cuts,axis=1)
    # Pure brightness / shadows / photographic stripes may share these traits.
    relative=contrast/np.maximum(sigma,1.)
    polarity=np.sign(contrast)
    observed=np.sum(sigma>1)
    if observed == 0:
        return {"state":"UNRESOLVED","reason":"FLAT_NATIVE_CUTS",
                "number_of_CORRELATED_transects":len(cuts)}
    return {
        "state":"OPTICAL_ONLY",
        "number_of_CORRELATED_transects":len(cuts),
        "nonflat_native_cut_fraction":round(float(np.mean(sigma>1)),5),
        "center_vs_flanks_abs_response_z":round(float(abs(np.median(relative))),5),
        "center_polarity_consistency_unverified":round(float(max(
            np.mean(polarity>0),np.mean(polarity<0))),5),
        "two_sided_center_peak_fraction":round(float(np.mean(
            ((middle-left)*(middle-right)>0)&(sigma>1))),5),
        "local_cut_response_variation_z":round(float(np.std(relative)),5),
        "physical_yarn_identity_probability":None,
    }


def analyze_track(image,endpoints,pitch):
    cuts=photo_transverse_cuts(image,endpoints,pitch)
    return characterize_cuts(cuts),cuts


def group_median_differences(matched,feature):
    groups={}
    for p in matched:
        delta=p.get("comparison_metrics",{}).get(feature)
        if delta is None:continue
        gid=p["operator_yarn_group_id"]
        if gid is None:continue
        groups.setdefault(gid,[]).append(delta)
    values=[float(np.median(v)) for v in groups.values()]
    return {
        "linked_operator_yarn_groups_compared":len(groups),
        "linked_group_median_green_minus_false":
            round(float(np.median(values)),5) if values else None,
        "physical_yarn_accuracy":None,
    }


def run(root,out,ids=("U20261013_01","U20261013_03","U20261013_06")):
    out.mkdir(parents=True,exist_ok=True)
    summary={
        "experiment":"P0_E6_V5_MULTITRANSECT_MORPHOLOGY_ONLY",
        "V5_inspiration":"multiple_cross_sections_and_count_one_physical_candidate_track_once",
        "frozen_V4_V5_executed_or_modified":False,
        "number_of_transverse_cuts_per_operator_track":len(CUT_FRACTIONS),
        "CROSSINGS_ACTUAL_OVER_UNDER_VERIFIED":False,
        "input_photo_only_weak_labels_NOT_INDEPENDENT_GT":True,
        "real_physical_yarn_accuracy":None,
        "A3_calibration_or_scoring_used":False,
        "samples":[],
    }
    for sid in ids:
        review=load_local_review(root,sid)
        photo,provenance=_camera_image(root,review)
        refs=json.loads((root/"datasets/annotations/drafts"/(sid+".json")).read_text(encoding="utf-8"))
        calibration=calibration_fields(refs,provenance["crop_original_xyxy"][:2])
        pitch=calibration["pitch"]
        # Hand review relations remain post-hoc grouping only.
        A1=np.asarray(refs["segments"]["reference"],float)
        angle=(math.degrees(math.atan2(*(A1[1]-A1[0])[::-1]))%180)
        E3=summarize_sample(photo,review,provenance,angle)
        matches=nearest_length_matched_twill_pairs(photo,E3)["pairs"]
        records={}
        for item in review["regions"]:
            if item["geometry"]["type"]!="LINE":continue
            p=convert_zoom_to_camera(item["geometry"]["points"],
                    provenance["crop_original_xyxy"],provenance["enlargement_scale"])
            measured,_=analyze_track(photo,p,pitch)
            records[item["id"]]={
                "id":item["id"],"operator_photo_label":item["kind"],
                "original_camera_line_xy":p,
                "physical_identification":"UNKNOWN",
                "native_A_pitch_camera_px":round(pitch,4),
                "camera_sampling_warning":
                    "LOW_SAMPLES_PER_YARN_PERIOD" if pitch<8 else None,
                "optical_multitransect":measured,
            }
        paired=[]
        for match in matches:
            p=records[match["operator_yarn_region_id"]]
            f,cuts=analyze_track(photo,match["false_local_camera_xy"],pitch)
            key_metrics=("center_vs_flanks_abs_response_z",
                         "center_polarity_consistency_unverified",
                         "two_sided_center_peak_fraction",
                         "local_cut_response_variation_z")
            pfeat=p["optical_multitransect"]
            diffs={
                key:round(pfeat[key]-f[key],5) if
                    pfeat.get(key) is not None and f.get(key) is not None else None
                for key in key_metrics
            }
            paired.append({
                "operator_yarn_region_id":p["id"],
                "operator_yarn_group_id":match["operator_yarn_group_id"],
                "operator_false_track_id":match["operator_false_track_id"],
                "nearby_length_direction_equal_camera_pixels":True,
                "positive_features":pfeat,"false_features":f,
                "comparison_metrics":diffs,
                "physical_class_claim":None,
            })
        keys=("center_vs_flanks_abs_response_z",
              "center_polarity_consistency_unverified",
              "two_sided_center_peak_fraction",
              "local_cut_response_variation_z")
        good=[r for r in records.values() if r["operator_photo_label"]=="APPARENT_VISIBLE_YARN"]
        false=[r for r in records.values() if r["operator_photo_label"]=="TWILL_PATTERN"]
        def agg(x,key):
            vals=[p["optical_multitransect"].get(key) for p in x]
            vals=[v for v in vals if v is not None]
            return round(float(np.median(vals)),5) if vals else None
        comparisons={key:{
            "human_visible_fragments_median":agg(good,key),
            "human_twill_tracks_median_UNMATCHED_LENGTH":agg(false,key),
            "MATCHED_nearby_group_level_green_minus_fake":
                 group_median_differences(paired,key),
            "cannot_infer_physical_identity":True,
        } for key in keys}
        ids_in_groups=connected_positive_groups(review["regions"],review["relations"])
        info={
            "sample_id":sid,"original_image_SHA":review["image_sha256"],
            "operator_visible_fragments":len(good),
            "operator_twill_visual_tracks":len(false),
            "same_operator_component_count_NOT_YARN_GT":len(ids_in_groups),
            "human_same_relations_not_used_in_feature_extraction":True,
            "native_A_pitch_camera_px":round(pitch,3),
            "optical_sampling_warning":"LOW_SAMPLES_PER_PERIOD" if pitch<8 else None,
            "E3_nearby_true_false_stroke_pairs_NOT_independent":len(paired),
            "E3_unique_true_operator_groups_in_pairs":len(set(p["operator_yarn_group_id"] for p in paired)),
            "E3_unique_false_track_ids_in_pairs":len(set(p["operator_false_track_id"] for p in paired)),
            "multitransect_features":comparisons,
            "physical_identity_accuracy":None,
        }
        summary["samples"].append(info)
        with (out/(sid+"_track_multitransects.json")).open("w",encoding="utf-8") as file:
            json.dump({"sample":info,"track_records":list(records.values()),"matched_pairs":paired},
                      file,ensure_ascii=False,indent=2)
        with (out/(sid+"_matched_multitransect.csv")).open("w",encoding="utf-8",newline="") as f:
            writer=csv.DictWriter(f,fieldnames=[
                "human_visible_segment","human_visible_relation_group",
                "human_fake_track","difference_center_bilateral_response",
                "difference_polarity_consistency","difference_two_sided_peak",
                "difference_cut_response_variability"])
            writer.writeheader()
            for row in paired:
                m=row["comparison_metrics"]
                writer.writerow({
                    "human_visible_segment":row["operator_yarn_region_id"],
                    "human_visible_relation_group":row["operator_yarn_group_id"],
                    "human_fake_track":row["operator_false_track_id"],
                    "difference_center_bilateral_response":m["center_vs_flanks_abs_response_z"],
                    "difference_polarity_consistency":m["center_polarity_consistency_unverified"],
                    "difference_two_sided_peak":m["two_sided_center_peak_fraction"],
                    "difference_cut_response_variability":m["local_cut_response_variation_z"],
                })
        print(f'{sid} E6 V5_TRANSECTS: {len(good)} operator_yarn_short_strokes; '
              f'{len(false)} fake_tracks; A_pitch_original_px={pitch:.3f}; '
              f'linked_groups_with_matches={info["E3_unique_true_operator_groups_in_pairs"]}; '
              f'matched_segments={len(paired)}; '
              f'center_peak_fraction_diff='
              f'{comparisons["two_sided_center_peak_fraction"]["MATCHED_nearby_group_level_green_minus_fake"]["linked_group_median_green_minus_false"]}; '
              f'low_res_warning={info["optical_sampling_warning"]}; '
              f'physical_identity=UNKNOWN',flush=True)
    (out/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return summary


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=ROOT)
    p.add_argument("--out",type=Path,default=Path("experiments/p0-e6-v5-inspired-multitransects"))
    a=p.parse_args()
    root=a.root.resolve()
    out=a.out if a.out.is_absolute() else root/a.out
    run(root,out)


if __name__=="__main__":
    main()
