"""P0-1 E2: original-camera local line appearance audit, NOT yarn classification.

The operator's zoom-2x LOCAL_IMAGE_EVIDENCE_REVIEW is weak PHONE-IMAGE
interpretation. Image evidence never certifies yarn physical identity. An
unusually long TWILL_PATTERN stroke is ONE operator negative *track*, not
many independent negative examples when divided into local optical windows.
Human SAME_PHYSICAL_YARN links are one hypothesized strand, not 10 strands.

Use only original camera photos and the original crop->zoom transform.
Do not read A3 holdout, GT masks, or optimize weights from the weak labels.
The report explicitly audits angle confounding, fabric-heldout feasibility,
short-window availability and the number of truly independent negative tracks.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

from benchmark.local_image_review import load_local_review
from benchmark.manual_annotation import (
    _zoom_review_provenance, image_stats, samples, validate_annotation,
    segment_axis_deg,
)

ROOT = Path(__file__).resolve().parents[1]
OPERATOR_SOURCE = "PHONE_IMAGE_OPERATOR_REVIEW"
POS = "APPARENT_VISIBLE_YARN"
NEG = "TWILL_PATTERN"
FEATURE_NAMES = (
    "center_vs_flanks_abs_z", "paired_side_contrast_z",
    "paired_contrast_support_fraction", "transverse_vs_axial_gradient",
    "center_flank_sign_stability", "local_luma_std", "local_chroma_std",
)


def axis_deg(points):
    a, b = np.asarray(points, dtype=float)
    return float(np.degrees(np.arctan2(b[1]-a[1], b[0]-a[0])) % 180)


def acute_axis_delta(a, b):
    """Undirected 0..90 degree distance; a printed stripe can mimic a yarn."""
    d = abs((float(a)-float(b)) % 180)
    return min(d, 180-d)


def convert_zoom_to_camera(points, crop_xyxy, scale=2):
    if scale != 2:
        raise ValueError("Only manifest-verified enlargement scale=2 is supported")
    arr = np.asarray(points, dtype=np.float64)
    if arr.shape != (2, 2) or not np.all(np.isfinite(arr)):
        raise ValueError("Expected a two-point operator stroke")
    return (arr / 2.0 + np.array(crop_xyxy[:2], dtype=np.float64)).tolist()


def _camera_image(root, review):
    row = samples(root)[review["sample_id"]]
    zoom_sha, zoom_size = image_stats(root, row)
    if review["image_sha256"] != zoom_sha:
        raise ValueError("Manual annotation photo hash mismatch")
    provenance = _zoom_review_provenance(root, row, zoom_sha, zoom_size)
    if provenance.get("enlargement_scale") != 2:
        raise ValueError("Requires registered 2x-to-original photo provenance")
    file = root / provenance["original_image_path"]
    if hashlib.sha256(file.read_bytes()).hexdigest() != provenance["original_image_sha256"]:
        raise ValueError("Original camera JPEG hash mismatch")
    with Image.open(file) as im:
        rgb = np.asarray(ImageOps.exif_transpose(im).convert("RGB"))
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), provenance


def _clip_array(channels, center, tangent, length_px=16., half_width=6.):
    """Undistorted original-camera sample; rows along the stroke, cols normal."""
    h, w = channels.shape[:2]
    unit = np.asarray(tangent, dtype=np.float32)
    unit = unit / max(1e-6, np.linalg.norm(unit))
    normal = np.array([-unit[1], unit[0]], np.float32)
    t = np.linspace(-length_px/2,length_px/2,33,dtype=np.float32)
    d = np.linspace(-half_width,half_width,25,dtype=np.float32)
    x = float(center[0]) + t[:,None]*unit[0] + d[None,:]*normal[0]
    y = float(center[1]) + t[:,None]*unit[1] + d[None,:]*normal[1]
    inside = (x>=1) & (x<w-2) & (y>=1) & (y<h-2)
    if float(inside.mean()) < .99:
        return None
    return cv2.remap(channels,x,y,cv2.INTER_LINEAR,
                     borderMode=cv2.BORDER_CONSTANT,borderValue=0)


def local_optical_features(patch):
    """Use fixed photo-only descriptors; do not learn decision cutoffs from labels."""
    if patch is None or patch.shape[:2] != (33,25):
        return None
    lab = cv2.cvtColor(patch.astype(np.uint8),cv2.COLOR_BGR2LAB).astype(np.float32)
    luma = lab[:,:,0]
    mid = np.mean(luma[:,11:14],axis=1)
    left = np.mean(luma[:,5:8],axis=1)
    right = np.mean(luma[:,17:20],axis=1)
    contrast = mid - .5*(left+right)
    left_delta = mid-left
    right_delta = mid-right
    pair = np.where(left_delta*right_delta>0,
                    np.minimum(np.abs(left_delta),np.abs(right_delta)),0.)
    sigma = max(2.,float(np.std(luma)))
    # Width and luminance/chroma features remain optical, not physical GT.
    trans = np.mean(np.abs(np.diff(luma,axis=1)))
    axial = np.mean(np.abs(np.diff(luma,axis=0)))
    med = np.median(contrast)
    fraction = float(np.mean(pair > max(1.0,.12*sigma)))
    return {
        "center_vs_flanks_abs_z":float(abs(np.median(contrast))/sigma),
        "paired_side_contrast_z":float(np.median(pair)/sigma),
        "paired_contrast_support_fraction":fraction,
        "transverse_vs_axial_gradient":float(trans/max(1.,axial)),
        "center_flank_sign_stability":float(np.mean(np.sign(contrast)==np.sign(med))),
        "local_luma_std":float(np.std(luma)),
        "local_chroma_std":float(np.mean(np.std(lab[:,:,1:],axis=(0,1)))),
    }


def windows_for_stroke(photo, coords, max_windows=7):
    a,b=np.asarray(coords,np.float32)
    distance=float(np.linalg.norm(b-a))
    if distance<7:
        return []
    direction=(b-a)/distance
    # Every clip covers 16 true camera pixels. A 500px twill path yields no
    # more than 7 correlated clips, still only ONE negative labeled track.
    n=min(max_windows,max(1,int(distance//20)))
    fractions=np.linspace(.15,.85,n) if n>1 else [.5]
    results=[]
    for t in fractions:
        center=a+float(t)*(b-a)
        patch=_clip_array(photo,center,direction)
        feat=local_optical_features(patch)
        if feat is not None:
            results.append({"center_camera_xy":[round(float(z),2) for z in center],
                            **{k:round(v,4) for k,v in feat.items()}})
    return results


def connected_positive_groups(regions,relations):
    """Links are provenance; do not infer unlinked patches are different yarns."""
    positive={r["id"] for r in regions if r["kind"]==POS}
    parent={id:id for id in positive}
    def find(x):
        while parent[x]!=x:
            parent[x]=parent[parent[x]]
            x=parent[x]
        return x
    for rel in relations:
        if rel["relation"]=="SAME_PHYSICAL_YARN" and rel["a"] in positive and rel["b"] in positive:
            a,b=find(rel["a"]),find(rel["b"])
            parent[a]=b
    groups={}
    for id in sorted(parent):
        groups.setdefault(find(id),[]).append(id)
    return [sorted(members) for members in groups.values()]


def camera_pitch_from_operator_A1_A2(reference, normalizer=2):
    """A1/A2 plus *human verified* N: geometric pitch, NOT an image label.

    This function never sees or uses A3 holdout. Units returned are original
    camera pixels; using the 2x zoom for photometry would be invalid.
    """
    a,b,n=reference
    if not a or not b or type(n) is not int or n<1 or normalizer!=2:
        return None
    angle=math.radians(axis_deg(a))
    normal=np.array([-math.sin(angle),math.cos(angle)])
    delta=np.asarray(b,dtype=float).mean(axis=0)-np.asarray(a,dtype=float).mean(axis=0)
    return float(abs(np.dot(delta,normal))/(n*normalizer))


def unlabelled_half_pitch_controls(photo,record,pitch):
    """Controls match each operator stroke's direction & length exactly.

    They may land on another physical yarn, gap, twill, or shadow.
    Their physical labels are ALWAYS UNKNOWN; do not count them as negatives.
    """
    if pitch is None or pitch<2.0 or record.get("camera_original_xy") is None:
        return None
    geom=np.asarray(record["camera_original_xy"],float)
    direction=geom[1]-geom[0]
    direction/=max(1e-8,np.linalg.norm(direction))
    normal=np.array([-direction[1],direction[0]])
    result=[]
    for shift in (-.5*pitch,.5*pitch):
        points=geom+shift*normal
        windows=windows_for_stroke(photo,points.tolist())
        feat={key:round(float(np.median([w[key] for w in windows])),4)
              for key in FEATURE_NAMES} if windows else None
        result.append({
            "camera_original_xy":np.around(points,3).tolist(),
            "offset_camera_pixels":round(float(shift),3),
            "known_physical_class":None,
            "operator_labelled_negative":False,
            "optical_features":feat,
            "correlated_optical_windows":len(windows),
        })
    return result


def half_pitch_probe(sample,photo,pitch):
    positives=[r for r in sample["records"]
               if r["kind"]==POS and r["geometry_type"]=="LINE"]
    probe=[]
    for rec in positives:
        sides=unlabelled_half_pitch_controls(photo,rec,pitch)
        rec["UNLABELLED_direction_matched_half_pitch_controls"]=sides
        if sides and rec["optical_features"] and all(x["optical_features"] for x in sides):
            for key in ("paired_side_contrast_z","center_vs_flanks_abs_z"):
                probe.append((key,rec["optical_features"][key],
                              max(side["optical_features"][key] for side in sides)))
    stats={}
    for key in ("paired_side_contrast_z","center_vs_flanks_abs_z"):
        selected=[(pos,control) for k,pos,control in probe if k==key]
        stats[key]={
            "candidate_operator_strokes_compared":len(selected),
            "fraction_candidate_optical_score_exceeds_both_unlabelled_sides":
                round(sum(a>b for a,b in selected)/len(selected),4) if selected else None,
            "valid_true_false_yarn_comparison":False,
        }
    sample["A1_A2_verified_nominal_pitch_camera_original_px"]=round(pitch,3) if pitch is not None else None
    sample["unlabelled_direction_length_matched_control_stats"]=stats


def nearest_length_matched_twill_pairs(photo, sample, *, max_distance_camera_px=40.0,
                                     max_angle_diff_deg=10.0):
    """Descriptive, same-orientation, same-length, nearby user LINE contrast.

    The two long twill strokes may share the same origin and can overlap;
    always match at most one false track per positive stroke and report
    actual group/negative-track counts. Never split a long line into
    independent GT. Reject distant matches and off-segment projections.
    """
    records=sample["records"]
    true=[r for r in records
          if r["kind"]==POS and r["geometry_type"]=="LINE"]
    false=[r for r in records
           if r["kind"] in ("TWILL_PATTERN","GAP","COLOR_STRIPE","SHADOW")
           and r["geometry_type"]=="LINE"]
    members=sample["positive_relation_groups_NOT_DISTINCT_YARN_COUNT"]
    group_of={rid:f"operator_group_{i+1:02d}" for i,g in enumerate(members)
              for rid in g}
    pairs=[]
    for pos in true:
        if not pos.get("optical_features"):continue
        points=np.asarray(pos["camera_original_xy"],float)
        pmid=np.mean(points,axis=0)
        pos_len=float(np.linalg.norm(points[1]-points[0]))
        pa=axis_deg(points)
        options=[]
        for neg in false:
            baseline=np.asarray(neg["camera_original_xy"],float)
            na=axis_deg(baseline)
            da=acute_axis_delta(pa,na)
            if da>max_angle_diff_deg:continue
            diff=baseline[1]-baseline[0]
            length=float(np.linalg.norm(diff))
            if length<=pos_len+1.e-6:continue
            unit=diff/length
            progress=float(np.dot(pmid-baseline[0],unit))
            # The negative crop must remain entirely on the actual user path;
            # extrapolating a candidate beyond their manually marked limits
            # would manufacture fake-line pixels not supplied by the operator.
            if not (pos_len/2<=progress<=length-pos_len/2):continue
            projection=baseline[0]+progress*unit
            distance=float(np.linalg.norm(pmid-projection))
            if distance>max_distance_camera_px:continue
            control=np.asarray([projection-.5*pos_len*unit,
                                projection+.5*pos_len*unit],float)
            observations=windows_for_stroke(photo,control.tolist())
            if not observations:continue
            c_features={key:round(float(np.median([x[key] for x in observations])),4)
                        for key in FEATURE_NAMES}
            options.append((distance,neg["id"],{
                "operator_yarn_region_id":pos["id"],
                "operator_yarn_group_id":group_of.get(pos["id"]),
                "operator_false_track_id":neg["id"],
                "operator_false_track_kind":neg["kind"],
                "positive_window_length_camera_px":round(pos_len,3),
                "negative_window_length_camera_px":round(pos_len,3),
                "angle_difference_deg":round(da,3),
                "center_separation_camera_px":round(distance,3),
                "false_local_camera_xy":np.round(control,3).tolist(),
                "positive_features":pos["optical_features"],
                "nearby_false_local_features":c_features,
                "score_differences_DESCRIPTIVE_ONLY":{
                    key:round(pos["optical_features"][key]-c_features[key],4)
                    for key in FEATURE_NAMES},
                "operator_photo_class_is_not_independent_physical_GT":True,
                "same_line_length_and_direction_does_not_prove_entity_identity":True,
            }))
        if options:
            pairs.append(min(options,key=lambda q:(q[0],q[1]))[2])
    # Do not score many linked short segments as independent yarns. A1/A2
    # anchors cannot promote these groupings to independent GT either.
    keys=("center_vs_flanks_abs_z","paired_side_contrast_z",
          "paired_contrast_support_fraction","transverse_vs_axial_gradient")
    summaries={}
    for key in keys:
        eligible=[p for p in pairs if p["operator_yarn_group_id"] is not None]
        grouped={}
        for p in eligible:
            grouped.setdefault(p["operator_yarn_group_id"],[]).append(
                p["score_differences_DESCRIPTIVE_ONLY"][key])
        medians=[float(np.median(x)) for x in grouped.values()]
        summaries[key]={
            "matched_stroke_median_difference":round(float(np.median([
                p["score_differences_DESCRIPTIVE_ONLY"][key] for p in pairs
            ])),4) if pairs else None,
            "linked_operator_yarn_groups_median_difference":round(float(np.median(medians)),4)
                if medians else None,
            "linked_operator_yarn_groups_positive_difference":sum(x>0 for x in medians),
            "linked_operator_yarn_groups_compared":len(medians),
            "probability_of_real_yarn_identity":None,
        }
    result={
        "comparison":"NEARBY_DIRECTION_AND_LENGTH_MATCHED_OPERATOR_IMAGE_ONLY",
        "max_center_separation_camera_px":max_distance_camera_px,
        "max_angle_difference_deg":max_angle_diff_deg,
        "matched_operator_strokes_NOT_independent":len(pairs),
        "unique_operator_yarn_same_strand_groups_NOT_VERIFIED_COUNT":
            len(set(p["operator_yarn_group_id"] for p in pairs)),
        "unique_operator_false_track_ids_NOT_independent_GT":
            len(set(p["operator_false_track_id"] for p in pairs)),
        "matched_operator_false_track_ids":
            sorted(set(p["operator_false_track_id"] for p in pairs)),
        "per_feature":summaries,
        "pairs":pairs,
        "real_physical_identity_accuracy":None,
        "unverified_phone_image_labels_only":True,
        "holdout_A3_used":False,
    }
    sample["length_direction_spatial_matched_false_track_comparison"]=result
    return result


def summarize_sample(photo,review,provenance,reference_axis):
    records=[]
    for reg in review["regions"]:
        geom=reg["geometry"]
        if geom["type"] != "LINE":
            records.append({"id":reg["id"],"kind":reg["kind"],
                            "geometry_type":geom["type"],
                            "optical_features":None,"reason":"REGION_NOT_A_TRACK"})
            continue
        camera_points=convert_zoom_to_camera(
            geom["points"],provenance["crop_original_xyxy"],
            provenance["enlargement_scale"])
        measurements=windows_for_stroke(photo,camera_points)
        med={key:round(float(np.median([m[key] for m in measurements])),4)
             for key in FEATURE_NAMES} if measurements else None
        records.append({
            "id":reg["id"],"kind":reg["kind"],"geometry_type":"LINE",
            "zoom_native_xy":geom["points"],
            "camera_original_xy":[[round(float(v),3) for v in p] for p in camera_points],
            "stroke_axis_deg":round(axis_deg(camera_points),3),
            "axis_delta_to_A1_deg":round(acute_axis_delta(axis_deg(camera_points),reference_axis),3),
            "length_camera_original_px":round(float(np.linalg.norm(np.diff(
                np.asarray(camera_points),axis=0))),3),
            "optical_windows_count_NOT_independent_training_samples":len(measurements),
            "optical_features":med,
            "windows":measurements,
            "physical_identity_probability":None,
            "independent_physical_ground_truth":False,
        })
    bykind=lambda name:[r for r in records if r["kind"]==name and r["geometry_type"]=="LINE"]
    positives=bykind(POS)
    negatives=bykind(NEG)
    groups=connected_positive_groups(review["regions"],review["relations"])
    near_neg=[x for x in negatives if x["axis_delta_to_A1_deg"]<=15.]
    def pooled(name):
        values=[r["optical_features"][name] for r in positives if r["optical_features"]]
        other=[r["optical_features"][name] for r in negatives if r["optical_features"]]
        return {"positive_operator_segments_median":round(float(np.median(values)),4) if values else None,
                "twill_operator_tracks_median":round(float(np.median(other)),4) if other else None,
                "descriptive_only":True}
    return {
        "sample_id":review["sample_id"],"review_state":review["review_state"],
        "annotation_source":review["annotation_source"],"A3_used":False,
        "warp_weft_identity":"UNKNOWN",
        "reference_A1_axis_deg":round(float(reference_axis),3),
        "human_apparent_yarn_short_strokes":len(positives),
        "human_twill_visual_tracks":len(negatives),
        "positive_relation_groups_NOT_DISTINCT_YARN_COUNT":groups,
        "positive_short_strokes_with_unknown_mutual_identity":
            sum(len(group)==1 for group in groups),
        "orientation_matched_twill_negative_tracks_15deg":len(near_neg),
        "optical_comparison_status":(
            "NOT_IDENTIFIABLE_TWILL_NEGATIVE_DIRECTION_CONFOUND"
            if not near_neg else "DESCRIPTIVE_WEAK_LABEL_COMPARISON_ONLY"
        ),
        "feature_medians_operator_labels":{key:pooled(key) for key in FEATURE_NAMES},
        "records":records,
        "physical_yarn_identity_accuracy":None,
        "physical_yarn_count_accuracy":None,
        "fabric_independent_heldout_accuracy":None,
    }


def visual_gallery(photo,sample,out,provenance):
    """Native camera pixels for measurements; image rescale is DISPLAY ONLY."""
    h,w=photo.shape[:2]
    overlay=photo.copy()
    for r in sample["records"]:
        if r.get("camera_original_xy") is None:continue
        a,b=[tuple(np.rint(p).astype(int)) for p in r["camera_original_xy"]]
        color=(15,215,48) if r["kind"]==POS else (28,190,255)
        cv2.line(overlay,a,b,color,3,cv2.LINE_AA)
        cv2.putText(overlay,r["id"],a,cv2.FONT_HERSHEY_SIMPLEX,.5,color,1,cv2.LINE_AA)
    scale=min(1.0,1350/max(h,w))
    if scale<1:overlay=cv2.resize(overlay,None,fx=scale,fy=scale,interpolation=cv2.INTER_AREA)
    cv2.imwrite(str(out/(sample["sample_id"]+"_annotated_camera_original.jpg")),overlay)
    # ONE card per operator track; a 500px twill LINE is not seven negatives.
    chosen=sample["records"][:12]
    twill=[r for r in sample["records"] if r["kind"]==NEG and r not in chosen]
    chosen+=twill[:3]
    cards=[]
    for rec in chosen:
        center=rec.get("camera_original_xy")
        if not center:continue
        midpoint=np.asarray(center,float).mean(axis=0)
        px,py=np.rint(midpoint).astype(int)
        x0,y0=px-43,py-43
        patch=np.zeros((86,86,3),np.uint8)
        xa,ya=max(0,x0),max(0,y0)
        xb,yb=min(w,x0+86),min(h,y0+86)
        if xa<xb and ya<yb:patch[ya-y0:yb-y0,xa-x0:xb-x0]=photo[ya:yb,xa:xb]
        s=3
        tile=cv2.resize(patch,None,fx=s,fy=s,interpolation=cv2.INTER_NEAREST)
        line=np.asarray(center,float)-np.array([x0,y0])
        points=np.rint(line*s).astype(int)
        clr=(10,235,30) if rec["kind"]==POS else (0,220,250)
        cv2.line(tile,tuple(points[0]),tuple(points[1]),clr,2,cv2.LINE_AA)
        cv2.putText(tile,rec["id"]+" "+("YARN CAND." if rec["kind"]==POS else "TWILL CAND."),
                    (5,18),cv2.FONT_HERSHEY_SIMPLEX,.43,(255,255,255),1,cv2.LINE_AA)
        cards.append(tile)
    if cards:
        rows=[]
        for start in range(0,len(cards),4):
            batch=cards[start:start+4]
            rows.append(np.hstack(batch+[np.zeros_like(cards[0])]*(4-len(batch))))
        cv2.imwrite(str(out/(sample["sample_id"]+"_local_camera_cards_DISPLAY_3x.jpg")),np.vstack(rows))


def direction_matched_unlabelled_gallery(photo,sample,out,max_tracks=12):
    """3-column photo-only view: half-pitch left | human | half-pitch right.

    Side positions are NOT trusted negatives. Same crop size, direction,
    native camera sampling, and DISPLAY-only enlargement across all columns.
    """
    h,w=photo.shape[:2]
    positives=[r for r in sample["records"]
               if r["kind"]==POS and r.get("UNLABELLED_direction_matched_half_pitch_controls")]
    output=[]
    for track in positives[:max_tracks]:
        sides=track["UNLABELLED_direction_matched_half_pitch_controls"]
        items=[sides[0]["camera_original_xy"],track["camera_original_xy"],
               sides[1]["camera_original_xy"]]
        cells=[]
        for j,coords in enumerate(items):
            center=np.asarray(coords,float).mean(axis=0)
            cx,cy=np.rint(center).astype(int)
            x0,y0=cx-34,cy-34
            tile=np.zeros((68,68,3),np.uint8)
            xa,ya=max(0,x0),max(0,y0)
            xb,yb=min(w,x0+68),min(h,y0+68)
            if xa<xb and ya<yb:
                tile[ya-y0:yb-y0,xa-x0:xb-x0]=photo[ya:yb,xa:xb]
            # All three cells are enlarged for DISPLAY only; camera original
            # pixel evidence is never computed on these crops.
            tile=cv2.resize(tile,(204,204),interpolation=cv2.INTER_NEAREST)
            line=(np.asarray(coords,float)-[x0,y0])*3
            p,q=np.rint(line).astype(int)
            cv2.line(tile,tuple(p),tuple(q),
                     (10,225,50) if j==1 else (0,190,255),2,cv2.LINE_AA)
            head=["LEFT UNKNOWN","OPERATOR YARN CAND.","RIGHT UNKNOWN"][j]
            cv2.putText(tile,head,(3,14),cv2.FONT_HERSHEY_SIMPLEX,
                        .39,(255,255,255),1,cv2.LINE_AA)
            cells.append(tile)
        output.append(np.hstack(cells))
    if output:
        cv2.imwrite(str(out/(sample["sample_id"]+"_orientation_matched_UNLABELLED_comparisons.jpg")),
                    np.vstack(output))


def run(root:Path,out:Path):
    out.mkdir(parents=True,exist_ok=True)
    samples_output=[]
    for sid in ("U20261013_01","U20261013_03"):
        annotation=load_local_review(root,sid)
        if not annotation["regions"]:raise RuntimeError("missing new manual review")
        # Reference line supplies only a rough orientation baseline. The
        # A3 held-out yarn is never loaded, calibrated to, or evaluated here.
        references=json.loads((root/"datasets/annotations/drafts"/(sid+".json")).read_text(encoding="utf-8"))
        if references.get("annotation_target") not in ("PHYSICAL_YARN_REFERENCE","PHYSICAL_YARN_TRAJECTORY"):
            raise RuntimeError("not physical yarn reference semantics")
        A1=references.get("segments",{}).get("reference")
        if not A1:raise RuntimeError("missing A1")
        ref_angle=segment_axis_deg(A1)
        A2=references.get("segments",{}).get("check_same")
        intervals=references.get("same_family_intervals")
        if references.get("same_family_intervals_confirmed") is not True:
            raise ValueError("do not use unconfirmed A1/A2 yarn intervals")
        pitch=camera_pitch_from_operator_A1_A2((A1,A2,intervals))
        photo,provenance=_camera_image(root,annotation)
        result=summarize_sample(photo,annotation,provenance,ref_angle)
        half_pitch_probe(result,photo,pitch)
        nearest_length_matched_twill_pairs(photo,result)
        visual_gallery(photo,result,out,provenance)
        direction_matched_unlabelled_gallery(photo,result,out)
        samples_output.append(result)
        print(f'{sid} apparent_strokes={result["human_apparent_yarn_short_strokes"]} '
              f'twill_tracks={result["human_twill_visual_tracks"]} '
              f'positive_relation_groups={len(result["positive_relation_groups_NOT_DISTINCT_YARN_COUNT"])} '
              f'orientation_matched_neg={result["orientation_matched_twill_negative_tracks_15deg"]} '
              f'comparison={result["optical_comparison_status"]}',flush=True)
        for key in ("center_vs_flanks_abs_z", "paired_side_contrast_z",
                    "paired_contrast_support_fraction", "transverse_vs_axial_gradient"):
            items=result["feature_medians_operator_labels"][key]
            print(f'{sid} optical {key} apparent={items["positive_operator_segments_median"]} '
                  f'twill={items["twill_operator_tracks_median"]} '
                  f'(DESCRIPTIVE_ONLY_NOT_YARN_PROOF)',flush=True)
        paired=result["length_direction_spatial_matched_false_track_comparison"]
        print(f'{sid} PAIR_MATCH image_only: strokes={paired["matched_operator_strokes_NOT_independent"]} '
              f'linked_positive_groups={paired["unique_operator_yarn_same_strand_groups_NOT_VERIFIED_COUNT"]} '
              f'false_tracks={paired["unique_operator_false_track_ids_NOT_independent_GT"]} '
              f'median_center_minus_false_dual_edge_fraction='
              f'{paired["per_feature"]["paired_contrast_support_fraction"]["linked_operator_yarn_groups_median_difference"]}'
              f' (NO_VERIFIED_PHYSICAL_ACCURACY)',flush=True)
        check=result["unlabelled_direction_length_matched_control_stats"]["paired_side_contrast_z"]
        print(f'{sid} PHOTO_ONLY matched_half_pitch paired_contrast '
              f'operator_strokes_compared={check["candidate_operator_strokes_compared"]} '
              f'center_greater_both_unlabelled_sides_fraction='
              f'{check["fraction_candidate_optical_score_exceeds_both_unlabelled_sides"]} '
              f'(UNLABELLED_NO_NEGATIVE_GROUND_TRUTH)',flush=True)
    observed_negative_fabrics=sum(bool(s["human_twill_visual_tracks"]) for s in samples_output)
    comparable_fabrics=sum(bool(s["orientation_matched_twill_negative_tracks_15deg"]) for s in samples_output)
    summary={
        "experiment":"P0_E2_ORIGINAL_CAMERA_OPERATOR_LINE_APPEARANCE_AUDIT",
        "protocol":"original_camera_rgb_only_zoom_to_camera_coord_map_2x",
        "photo_resize_for_display_only":True,
        "annotation_semantics":"PHONE_IMAGE_OPERATOR_REVIEW",
        "operator_review_states":[s["review_state"] for s in samples_output],
        "independent_physical_gt_available":False,
        "real_physical_yarn_identity_accuracy":None,
        "real_yarn_count_accuracy":None,
        "number_of_operator_annotated_fabrics":len(samples_output),
        "fabrics_with_twill_negative_tracks":observed_negative_fabrics,
        "fabrics_with_orientation_matched_twill_negatives_15deg":comparable_fabrics,
        "class_separation_claim":"NOT_EVALUABLE" if comparable_fabrics==0 else "DESCRIPTIVE_ONLY_NO_INDEPENDENT_GT",
        "long_negative_line_is_one_track_NOT_N_independent_negative_samples":True,
        "A3_held_out_from_analysis":True,
        "A1_is_direction_baseline_NOT_autonomous_direction_GT":True,
        "direction_length_matched_half_pitch_controls_are_UNLABELLED":True,
        "requires_to_test_non_direction_texture_discrimination":
            "Add short TWILL_PATTERN visual false tracks approximately parallel to real yarn A1 on a different fabric, if recognizable. Otherwise mark UNCERTAIN; do not invent negatives.",
        "samples":samples_output,
    }
    (out/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    with (out/"track_features.csv").open("w",encoding="utf-8",newline="") as f:
        headers=["sample_id","region_id","kind","axis_delta_to_A1_deg",
                 "length_camera_original_px","n_correlated_windows"]+list(FEATURE_NAMES)
        writer=csv.DictWriter(f,fieldnames=headers)
        writer.writeheader()
        for sample in samples_output:
            for r in sample["records"]:
                if r.get("optical_features") is None:continue
                writer.writerow(dict(sample_id=sample["sample_id"],region_id=r["id"],
                                     kind=r["kind"],axis_delta_to_A1_deg=r["axis_delta_to_A1_deg"],
                                     length_camera_original_px=r["length_camera_original_px"],
                                     n_correlated_windows=r["optical_windows_count_NOT_independent_training_samples"],
                                     **r["optical_features"]))
    return summary


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--root",type=Path,default=ROOT)
    parser.add_argument("--out",type=Path,default=Path("experiments/p0-e2-operator-line-audit"))
    args=parser.parse_args()
    root=args.root.resolve()
    out=args.out if args.out.is_absolute() else root/args.out
    run(root,out)


if __name__=="__main__":
    main()
