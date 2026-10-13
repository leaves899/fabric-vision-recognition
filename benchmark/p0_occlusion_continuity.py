"""P0-E4 cross-occlusion continuity, without sample-specific pixel tolerances.

Candidate generation & evidence use image + operator visible fragment geometry;
human SAME_PHYSICAL_YARN relations are read ONLY during final audit. Unknown
alternative links are NOT labelled negatives. No tuned scalar identity score.
Original camera photo is the ONLY input for morphology; 2x zoom supplies points.
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
)

ROOT = Path(__file__).resolve().parents[1]
POS = "APPARENT_VISIBLE_YARN"
METRICS = ("gap_over_pitch", "lateral_over_pitch",
           "endpoint_turn_fraction", "appearance_lab_delta_scaled",
           "profile_dissimilarity")
EPS = 1e-9


def unit(x):
    v = np.asarray(x, dtype=float)
    m = float(np.linalg.norm(v))
    if m <= EPS:
        raise ValueError("zero-length vector")
    return v / m


def calibration_fields(annotation, original_camera_crop_origin=(0, 0)):
    """Whitelist A1, A2, B1, B2; intentionally NEVER read A3."""
    seg = annotation["segments"]
    A1, A2, B1, B2 = (np.asarray(seg[name], float) for name in
                        ("reference", "check_same", "check_cross", "check_cross_second"))
    if annotation.get("same_family_intervals_confirmed") is not True or (
       annotation.get("cross_family_intervals_confirmed") is not True):
        raise ValueError("A/B inter-yarn reference intervals must be human-confirmed")
    na, nb = annotation.get("same_family_intervals"), annotation.get("cross_family_intervals")
    if type(na) is not int or na <= 0 or type(nb) is not int or nb <= 0:
        raise ValueError("invalid operator interval count")
    tangent = unit(A1[1] - A1[0])
    normal = np.array([-tangent[1], tangent[0]])
    b_tangent = unit(B1[1] - B1[0])
    b_normal = np.array([-b_tangent[1], b_tangent[0]])
    pitch = abs(float(np.dot(A2.mean(axis=0) - A1.mean(axis=0), normal))) / na / 2
    b_pitch = float(np.dot(B2.mean(axis=0) - B1.mean(axis=0), b_normal)) / nb / 2
    if pitch <= EPS or abs(b_pitch) <= EPS:
        raise ValueError("unresolved physical-pitch calibration")
    return {"tangent": tangent, "normal": normal, "pitch": pitch,
            "B_tangent": b_tangent, "B_normal": b_normal,
            "B_origin": B1.mean(axis=0) / 2 +
                np.asarray(original_camera_crop_origin, dtype=float),
            "B_pitch_signed": b_pitch,
            "uses_A3_holdout": False}


def endpoint_signature(image, endpoint, tangent, segment_length, pitch, into):
    """Profile entirely INSIDE the annotated visible fragment, not the gap.

    Sampling aperture scales with operator-confirmed local yarn pitch and
    visible fragment length; NO absolute-pixel observation threshold.
    """
    advance = segment_length * .23
    half_length = min(.18 * segment_length, .33 * pitch)
    half_width = min(.22 * pitch, .36 * segment_length)
    center = np.asarray(endpoint, float) + np.asarray(tangent, float) * into * advance
    rows = np.linspace(-half_length, half_length, 17)
    cols = np.linspace(-half_width, half_width, 17)
    n = np.array([-tangent[1], tangent[0]], float)
    xx = center[0] + rows[:, None] * tangent[0] + cols[None, :] * n[0]
    yy = center[1] + rows[:, None] * tangent[1] + cols[None, :] * n[1]
    h, w = image.shape[:2]
    if xx.min() < 1 or yy.min() < 1 or xx.max() >= w-2 or yy.max() >= h-2:
        return None
    patch = cv2.remap(image, xx.astype(np.float32), yy.astype(np.float32),
                      cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    lab = cv2.cvtColor(patch, cv2.COLOR_BGR2LAB).astype(float)
    central = lab[:, 7:10, :]
    profile = np.mean(lab[:, :, 0], axis=0)
    return {"lab": central.mean(axis=(0, 1)).tolist(),
            "luma_profile": profile.tolist(),
            "local_luma_spread": max(float(lab[:, :, 0].std()), EPS),
            "camera_endpoint": np.asarray(endpoint, float).tolist()}


def create_fragments(image, review, provenance, calib):
    """Does not read review['relations'] or any independent identity label."""
    t, n, pitch = calib["tangent"], calib["normal"], calib["pitch"]
    result = []
    for item in review["regions"]:
        if item["kind"] != POS or item["geometry"]["type"] != "LINE":
            continue
        coords = np.asarray(convert_zoom_to_camera(
            item["geometry"]["points"], provenance["crop_original_xyxy"],
            provenance["enlargement_scale"]), dtype=float)
        if np.dot(coords[1] - coords[0], t) < 0:
            coords = coords[::-1]
        a, b = coords
        direction = unit(b-a)
        length = float(np.linalg.norm(b-a))
        result.append({
            "id": item["id"], "start": a.tolist(), "end": b.tolist(),
            "u_start": float(np.dot(a, t)), "u_end": float(np.dot(b, t)),
            "v_start": float(np.dot(a, n)), "v_end": float(np.dot(b, n)),
            "direction": direction.tolist(), "camera_length": length,
            "start_signature": endpoint_signature(image, a, direction, length, pitch, +1),
            "end_signature": endpoint_signature(image, b, direction, length, pitch, -1),
        })
    return sorted(result, key=lambda z: z["id"])


def morphology_pair(a, b):
    if a is None or b is None:
        return {"appearance_lab_delta_scaled": None, "profile_dissimilarity": None}
    lab_a, lab_b = np.asarray(a["lab"]), np.asarray(b["lab"])
    # Absolute color scale is pixel-Lab; descriptive metric, not a hard class.
    delta = float(np.linalg.norm(lab_a - lab_b)) / 100.
    pa, pb = np.asarray(a["luma_profile"]), np.asarray(b["luma_profile"])
    pa = pa-pa.mean()
    pb = pb-pb.mean()
    denom = float(np.linalg.norm(pa)*np.linalg.norm(pb))
    corr = float(np.dot(pa,pb)/denom) if denom > EPS else None
    return {"appearance_lab_delta_scaled": round(delta, 5),
            "profile_dissimilarity": round((1-corr)/2, 5) if corr is not None else None}


def predicted_B_crossing(i, j, calib):
    """Geometry-only B-lattice expectation, NOT confirmed occlusion topology."""
    bnorm = calib["B_normal"]
    origin = calib["B_origin"]
    step = calib["B_pitch_signed"]
    lo = float(np.dot(np.asarray(i["end"])-origin, bnorm) / step)
    hi = float(np.dot(np.asarray(j["start"])-origin, bnorm) / step)
    low, high = min(lo, hi), max(lo, hi)
    indices = list(range(math.ceil(low), math.floor(high)+1))
    # The geometry can cross zero/multiple B lines. None is proof of over/under.
    return {"expected_B_lattice_intersections_NOT_physical_GT": len(indices),
            "B_lattice_indices": indices,
            "verified_actual_over_under": False,
            "verified_physical_occlusion": False}


def propose_candidates(fragments, calib):
    """All forward endpoint pairs; no hard 15-34px gate or fixed pixel shift.

    The full candidate set is deterministic and does not access SAME labels.
    Soft relative metrics are kept separate: no fitted weights/thresholds.
    """
    pitch = calib["pitch"]
    edges = []
    for i in fragments:
        for j in fragments:
            if i["id"] == j["id"]:
                continue
            du = float(j["u_start"] - i["u_end"])
            if du <= 0:
                continue
            dv = float(j["v_start"] - i["v_end"])
            A, B = np.asarray(i["direction"]), np.asarray(j["direction"])
            cos = float(np.clip(abs(np.dot(A, B)), 0, 1))
            morphology = morphology_pair(i["end_signature"], j["start_signature"])
            metrics = {
                "gap_over_pitch": round(du/pitch, 5),
                "lateral_over_pitch": round(abs(dv)/pitch, 5),
                "signed_lateral_over_pitch": round(dv/pitch, 5),
                "endpoint_turn_fraction": round(math.acos(cos)/(math.pi/2), 5),
                **morphology,
            }
            edges.append({
                "source": i["id"], "target": j["id"], **metrics,
                "B_geometry": predicted_B_crossing(i,j,calib),
                "real_physical_same_yarn_probability": None,
                "unknown_alternative_NOT_negative_GT": True,
            })
    return sorted(edges, key=lambda x:(x["source"],x["target"]))


def rank_evidence(edges):
    """Unweighted rank/pareto diagnostic; not a new physical-yarn classifier.

    Missing image evidence remains missing and cannot be silently scored as 0.
    Per-source alternatives share the same source and direction/length context.
    """
    by_source = {}
    for e in edges:
        by_source.setdefault(e["source"], []).append(e)
    result = []
    for src, group in sorted(by_source.items()):
        # Robust to ties; ranks start 1; missing signals stay None.
        for e in group:
            ranks = {}
            for metric in METRICS:
                v = e[metric]
                ranks[metric] = (1+sum(other[metric] is not None and
                    other[metric] < v-EPS for other in group)
                    if v is not None else None)
            # Pareto comparison uses ONLY fully observed 5-dimensional cues.
            comparable = [o for o in group if all(o[m] is not None for m in METRICS)]
            if all(e[m] is not None for m in METRICS):
                dominated = any(
                    all(o[m] <= e[m]+EPS for m in METRICS) and
                    any(o[m] < e[m]-EPS for m in METRICS)
                    for o in comparable if o is not e)
            else:
                dominated = None
            result.append({**e, "rank_among_all_forward_alternatives":ranks,
                           "pareto_dominated":dominated,
                           "forward_alternative_count":len(group),
                           "inference_identity_status":"UNKNOWN"})
    return result


def audit_operator_connections(candidates, relations, fragments):
    """Only audit reads human SAME edges. Never feeds them into generation."""
    lookup = {(e["source"], e["target"]):e for e in candidates}
    frags = {f["id"]:f for f in fragments}
    inspected=[]
    for rel in relations:
        if rel["relation"]!="SAME_PHYSICAL_YARN":
            continue
        a, b = rel["a"], rel["b"]
        if a not in frags or b not in frags:
            continue
        if frags[a]["u_start"]>frags[b]["u_start"]:
            a, b = b, a
        edge = lookup.get((a,b))
        inspected.append({
            "operator_source":a,"operator_target":b,
            "operator_relationship":"SAME_PHYSICAL_YARN_IMAGE_INTERPRETATION",
            "candidate_generated_without_relation":edge is not None,
            "alternative_continuations":edge["forward_alternative_count"] if edge else None,
            "rank_per_untuned_evidence":edge["rank_among_all_forward_alternatives"] if edge else None,
            "pareto_dominated":edge["pareto_dominated"] if edge else None,
            "physical_connection_verified":False,
        })
    groups = connected_positive_groups(
        [{"id":f["id"],"kind":POS} for f in fragments], relations)
    complete = [x for x in inspected if x["candidate_generated_without_relation"]]
    members_by_id={rid:f"operator_component_{i+1:02d}" for i,g in enumerate(groups)
                   for rid in g}
    for item in inspected:
        item["human_same_component_group_NOT_PHYSICAL_IDENTITY_GT"] = (
            members_by_id.get(item["operator_source"]))
    diagnostic={}
    for metric in METRICS:
        available=[r for r in complete
                   if r["rank_per_untuned_evidence"][metric] is not None]
        per_group={}
        for row in available:
            n=row["alternative_continuations"]
            rank=row["rank_per_untuned_evidence"][metric]
            # rank 1 is the most preferred; 1.0 normalized preference is best.
            preference=1.0 - (rank-1)/max(n-1,1)
            per_group.setdefault(row["human_same_component_group_NOT_PHYSICAL_IDENTITY_GT"],[]).append(preference)
        group_medians=[float(np.median(values)) for values in per_group.values()]
        diagnostic[metric]={
            "operator_links_scored_NOT_independent_GT":len(available),
            "operator_links_at_rank_one_NOT_accuracy":sum(
                r["rank_per_untuned_evidence"][metric]==1 for r in available),
            "distinct_operator_same_groups_scored":len(per_group),
            "median_group_preference_0_worst_1_best_DESCRIPTIVE_ONLY":
                round(float(np.median(group_medians)),4) if group_medians else None,
            "not_a_true_false_classification_metric":True,
        }
    return {
        "per_cue_operator_relation_competition_DIAGNOSTIC_ONLY":diagnostic,
        "same_operator_strokes_audited":len(inspected),
        "operator_same_links_found_in_all_forward_candidates":len(complete),
        "operator_same_links_not_generated":len(inspected)-len(complete),
        "operator_linked_component_count_NOT_PHYSICAL_YARN_COUNT":len(groups),
        "operator_component_sizes":sorted((len(g) for g in groups),reverse=True),
        "single_best_link_physical_identity_accuracy":None,
        "wrong_links_NOT_independent_GT":True,
        "A3_used_for_feature_or_candidate_choice":False,
        "operator_links":inspected,
    }


def render_audit(photo, frags, audit, output):
    """Overlay photographed endpoints + operator links ONLY after scoring."""
    canvas = photo.copy()
    features={f["id"]:f for f in frags}
    for f in frags:
        a,b = [tuple(np.rint(x).astype(int)) for x in (f["start"],f["end"])]
        cv2.line(canvas,a,b,(45,210,50),2,cv2.LINE_AA)
    for item in audit["operator_links"]:
        x,y=features[item["operator_source"]],features[item["operator_target"]]
        a=tuple(np.rint(x["end"]).astype(int))
        b=tuple(np.rint(y["start"]).astype(int))
        clr=(0,180,240) if item["candidate_generated_without_relation"] else (40,40,235)
        cv2.line(canvas,a,b,clr,1,cv2.LINE_AA)
    h,w=canvas.shape[:2]
    factor=min(1.,1400/max(h,w))
    if factor < 1.:
        canvas=cv2.resize(canvas,None,fx=factor,fy=factor,interpolation=cv2.INTER_AREA)
    cv2.imwrite(str(output),canvas)


def run(root:Path,out:Path,sample_ids=("U20261013_01","U20261013_03")):
    out.mkdir(parents=True,exist_ok=True)
    summary={
        "experiment":"P0_E4_CROSS_OCCLUSION_CONTINUITY_COMPETING_CONNECTIONS",
        "identity_ground_truth_independent":False,
        "annotation_evidence":"PHONE_IMAGE_OPERATOR_REVIEW",
        "not_a_physical_identity_accuracy_test":True,
        "absolute_pixel_gate_used":False,
        "scalar_weighted_identity_score_fitted":False,
        "A3_holdout_read":False,
        "cannot_certify_weave_or_real_yarn_count":True,
        "samples":[],
    }
    for sid in sample_ids:
        review=load_local_review(root,sid)
        if not review["regions"]:
            raise ValueError("Missing human visible fragment labels: "+sid)
        # Select fields without reading A3 into the evidence pipeline.
        reference=json.loads((root/"datasets/annotations/drafts"/(sid+".json")).read_text(encoding="utf-8"))
        photo,provenance=_camera_image(root,review)
        calib=calibration_fields(reference,provenance["crop_original_xyxy"][:2])
        fragments=create_fragments(photo,review,provenance,calib)
        edges=rank_evidence(propose_candidates(fragments,calib))
        # Critically: operator relationships enter ONLY after the complete
        # candidate list and its deterministic scores have been frozen.
        audited=audit_operator_connections(edges,review["relations"],fragments)
        rendered=out/(sid+"_continuity_POSTHOC_OPERATOR.jpg")
        render_audit(photo,fragments,audited,rendered)
        sample={
            "sample_id":sid,"photo_SHA":review["image_sha256"],
            "image_review_state":review["review_state"],
            "native_camera_evidence":True,
            "reference_A3_used":False,
            "A1_A2_pitch_camera_px_DESCRIPTIVE_ONLY":round(calib["pitch"],4),
            "B_pitch_camera_px_DESCRIPTIVE_ONLY":round(abs(calib["B_pitch_signed"]),4),
            "visible_operator_fragment_count_NOT_yarns":len(fragments),
            "forward_hypotheses_all_pairs":len(edges),
            "operator_image_same_links":audited,
            "all_unlabelled_competing_pairs_NOT_NEGATIVE_GT":True,
            "real_yarn_identity_accuracy":None,
            "inference_decision":"UNKNOWN_UNVERIFIED_PHYSICAL_IDENTITY",
            "artifact_overlay":rendered.name,
        }
        summary["samples"].append(sample)
        with (out/(sid+"_candidate_edges.json")).open("w",encoding="utf-8") as f:
            json.dump({"image_SHA":review["image_sha256"],
                       "sample_id":sid,
                       "human_same_relations_excluded_from_inference":True,
                       "edges":edges},f,ensure_ascii=False,indent=2)
        with (out/(sid+"_operator_link_ranks.csv")).open("w",encoding="utf-8",newline="") as f:
            writer=csv.DictWriter(f,fieldnames=[
                "operator_source","operator_target","candidate_generated_without_relation",
                "alternative_continuations","pareto_dominated"]+list(METRICS))
            writer.writeheader()
            for x in audited["operator_links"]:
                writer.writerow({
                    "operator_source":x["operator_source"],
                    "operator_target":x["operator_target"],
                    "candidate_generated_without_relation":x["candidate_generated_without_relation"],
                    "alternative_continuations":x["alternative_continuations"],
                    "pareto_dominated":x["pareto_dominated"],
                    **(x["rank_per_untuned_evidence"] or {}),
                })
        print(f'{sid} fragments={len(fragments)} forward_hypotheses={len(edges)} '
              f'operator_links={audited["same_operator_strokes_audited"]} '
              f'present={audited["operator_same_links_found_in_all_forward_candidates"]} '
              f'candidate_coverage_NOT_accuracy '
              f'(UNKNOWN_PHYSICAL_IDENTITY)',flush=True)
        for metric,stats in audited["per_cue_operator_relation_competition_DIAGNOSTIC_ONLY"].items():
            print(f'{sid} E4_CUE {metric}: linked_groups={stats["distinct_operator_same_groups_scored"]} '
                  f'group_median_preference={stats["median_group_preference_0_worst_1_best_DESCRIPTIVE_ONLY"]} '
                  f'top1_operator_links={stats["operator_links_at_rank_one_NOT_accuracy"]}/'
                  f'{stats["operator_links_scored_NOT_independent_GT"]} '
                  f'(SAME_IS_WEAK_OPERATOR_IMAGE_LABEL_NOT_PHYSICAL_GT)',flush=True)
    (out/"summary.json").write_text(
        json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return summary


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=ROOT)
    p.add_argument("--out",type=Path,default=Path("experiments/p0-e4-occlusion-continuity"))
    a=p.parse_args()
    root=a.root.resolve()
    out=a.out if a.out.is_absolute() else root/a.out
    run(root,out)


if __name__=="__main__":
    main()
