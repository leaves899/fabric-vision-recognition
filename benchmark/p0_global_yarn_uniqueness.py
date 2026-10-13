"""P0-E6.2 global *hypothesis* uniqueness on E4 forward fragment graph.

This is a constrained COMPETITION / falsification experiment, not a physical
yarn connector. A maximum-cardinality assignment deliberately illustrates
how an algorithm can join too much; it must NEVER be published as yarn count.

Input inference: original camera pixels + manually outlined VISIBLE LINE
fragments, A1/A2 pitch and B1/B2 orientation. Human SAME relations enter only
the post-hoc audit. The A3 holdout is never read. No sample03 pixel cutoff,
trained weights or calibrated confidence, no physical over/under GT.

Two predeclared parameter-free priority orders (geometry vs image-profile)
yield globally one-in/one-out assignments; *only* their common conflict-free
edges are displayed as tentative structural proposals, always UNKNOWN identity.
Potential ordering crossings result in ABSTAIN, never fabricated "bad" labels.
"""
from __future__ import annotations

import argparse
import copy
import csv
import json
import math
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
from scipy.optimize import linear_sum_assignment

from benchmark.local_image_review import load_local_review
from benchmark.p0_operator_line_audit import _camera_image, connected_positive_groups
from benchmark.p0_occlusion_continuity import (
    calibration_fields, create_fragments, propose_candidates,
)

ROOT=Path(__file__).resolve().parents[1]
GEOMETRY_METRICS=("lateral_over_pitch","endpoint_turn_fraction","gap_over_pitch")
APPEARANCE_METRICS=("profile_dissimilarity","appearance_lab_delta_scaled","lateral_over_pitch")
ALL_METRICS=tuple(dict.fromkeys(GEOMETRY_METRICS+APPEARANCE_METRICS))


def ordered_preferences(edges, metric_order):
    """Per source AND target candidate ordinal preference, never raw pixels.

    Missing image measurements are NOT silently substituted with 0.
    Each metric priority is fixed before observing labels; each approach
    has distinct assumptions and may fail on a different fabric.
    """
    valid=[e for e in edges if all(
        e.get(m) is not None and math.isfinite(float(e[m]))
        for m in metric_order)]
    rank_src={}
    rank_tgt={}
    groups_src=defaultdict(list)
    groups_tgt=defaultdict(list)
    for e in valid:
        groups_src[e["source"]].append(e)
        groups_tgt[e["target"]].append(e)
    def key(e):
        return tuple(float(e[m]) for m in metric_order)+(e["source"],e["target"])
    for source,group in groups_src.items():
        group.sort(key=key)
        for i,e in enumerate(group):
            rank_src[(e["source"],e["target"])]=(i/max(1,len(group)-1),i+1)
    for target,group in groups_tgt.items():
        group.sort(key=key)
        for i,e in enumerate(group):
            rank_tgt[(e["source"],e["target"])]=(i/max(1,len(group)-1),i+1)
    ranks={}
    for e in valid:
        pair=(e["source"],e["target"])
        sr=rank_src[pair]
        tr=rank_tgt[pair]
        ranks[pair]={
            "cost":(sr[0]+tr[0])/2,
            "source_rank":sr[1],
            "target_rank":tr[1],
            "source_candidates":len(groups_src[e["source"]]),
            "target_candidates":len(groups_tgt[e["target"]]),
        }
    return ranks


def naive_source_best(ranks):
    """Deliberately defective independent selection, for comparison only."""
    groups=defaultdict(list)
    for pair,x in ranks.items():
        groups[pair[0]].append((x["cost"],pair))
    edges=[min(rows,key=lambda p:(p[0],p[1]))[1]
           for rows in groups.values()]
    counts=defaultdict(int)
    for _,target in edges:counts[target]+=1
    return {
        "individual_source_best_count":len(edges),
        "targets_with_multiple_predecessors":sum(v>1 for v in counts.values()),
        "excess_predecessors_dropped_by_one_to_one":
             sum(max(0,v-1) for v in counts.values()),
        "not_a_valid_unique_yarn_network":True,
    }


def global_assignment(fragments, ranks):
    """Exact max-cardinality min-ordinal-rank bipartite assignment.

    Src/tgt copies allow one predecessor AND one successor; forward-u edges
    guarantee no directed cycle. Dummies model unmatched stubs, but because
    cardinality is optimized FIRST, this is a *forced upper-bound scenario*:
    unmatched is not calibrated physical abstention and selected edges are
    NOT asserted true yarns.
    """
    ids=sorted(x["id"] for x in fragments)
    n=len(ids)
    if not n:
        return []
    lookup={x:i for i,x in enumerate(ids)}
    dummy=float(n+2)
    huge=dummy*(n+3)
    # An independent dummy per source permits abstention in the matrix.
    # Hungarian optimizes max count first, then sum of ordinal ranks.
    matrix=np.full((n,2*n),huge,dtype=np.float64)
    matrix[:,n:]=dummy
    for (source,target),v in ranks.items():
        matrix[lookup[source],lookup[target]]=min(1.,v["cost"])
    rows,cols=linear_sum_assignment(matrix)
    chosen=[]
    for r,c in zip(rows,cols):
        if c<n and matrix[r,c]<dummy:
            chosen.append((ids[r],ids[c]))
    return sorted(chosen)


def edge_intersection(first,second,fragments):
    """Proper crossing of projected gap chords, not actual optical crossing.

    T-junctions and shared endpoints are not judged. Woven yarn can bow and
    projection may mislead, so a crossing only triggers topology *ambiguity*.
    """
    a,b=first
    c,d=second
    if len({a,b,c,d})<4:
        return False
    f=fragments
    p=np.array([f[a]["u_end"],f[a]["v_end"]],float)
    q=np.array([f[b]["u_start"],f[b]["v_start"]],float)
    s=np.array([f[c]["u_end"],f[c]["v_end"]],float)
    t=np.array([f[d]["u_start"],f[d]["v_start"]],float)
    def cross(x,y):return float(x[0]*y[1]-x[1]*y[0])
    def orientation(x,y,z):return cross(y-x,z-x)
    a1,a2=orientation(p,q,s),orientation(p,q,t)
    b1,b2=orientation(s,t,p),orientation(s,t,q)
    tol=1e-10*max(1.,float(np.linalg.norm(q-p))*float(np.linalg.norm(t-s)))
    return a1*a2 < -tol and b1*b2 < -tol


def crossing_conflicts(chosen, fragments):
    fmap={f["id"]:f for f in fragments}
    conflicts=[]
    for ix,a in enumerate(chosen):
        for b in chosen[ix+1:]:
            if edge_intersection(a,b,fmap):
                conflicts.append([list(a),list(b)])
    return conflicts


def validate_unique(chosen, fragments):
    ids={f["id"] for f in fragments}
    src=[a for a,_ in chosen]
    tgt=[b for _,b in chosen]
    if (len(src)!=len(set(src)) or len(tgt)!=len(set(tgt)) or
        any(a==b or a not in ids or b not in ids for a,b in chosen)):
        return False
    f={x["id"]:x for x in fragments}
    return all(f[b]["u_start"]>f[a]["u_end"] for a,b in chosen)


def path_components(fragments,edges):
    """Illustrative chaining ONLY. Component length is NOT number of yarns."""
    nxt=dict(edges)
    prev={b:a for a,b in edges}
    fragments_by_id={f["id"]:f for f in fragments}
    paths=[]
    seen=set()
    for start in sorted(fragments_by_id):
        if start in prev:continue
        seq=[]
        x=start
        while x is not None and x not in seen:
            seen.add(x)
            seq.append(x)
            x=nxt.get(x)
        paths.append(seq)
    if len(seen)!=len(fragments):
        raise ValueError("cycle or repeated fragment; invalid DAG")
    return paths


def compare_structures(fragments, edges):
    """Two explicit priorities + global one-to-one + crossings as abstentions."""
    geometry_ranks=ordered_preferences(edges,GEOMETRY_METRICS)
    appearance_ranks=ordered_preferences(edges,APPEARANCE_METRICS)
    G=global_assignment(fragments,geometry_ranks)
    P=global_assignment(fragments,appearance_ranks)
    assert validate_unique(G,fragments)
    assert validate_unique(P,fragments)
    overlap=sorted(set(G)&set(P))
    crossings_G=crossing_conflicts(G,fragments)
    crossings_P=crossing_conflicts(P,fragments)
    crossings_both=crossing_conflicts(overlap,fragments)
    conflicted={tuple(edge) for pair in crossings_both for edge in pair}
    clean=sorted(x for x in overlap if x not in conflicted)
    assert validate_unique(clean,fragments)
    assert not crossing_conflicts(clean,fragments)
    return {
        "priority_sets":{
            "GEOMETRIC_CONTINUITY":list(GEOMETRY_METRICS),
            "ENDPOINT_IMAGE_APPEARANCE":list(APPEARANCE_METRICS),
        },
        "solver":"SCIPY_EXACT_BIPARTITE_MAX_CARDINALITY_MIN_UNTUNED_ORDINAL_RANK",
        "forced_cardinality_is_NOT_an_identity_confidence":True,
        "geometry_ranks_available":len(geometry_ranks),
        "appearance_ranks_available":len(appearance_ranks),
        "local_geometry_baseline":naive_source_best(geometry_ranks),
        "global_geometry_links_FORCED_HYPOTHESES":len(G),
        "global_appearance_links_FORCED_HYPOTHESES":len(P),
        "geometry_gap_chord_crossing_pairs":len(crossings_G),
        "appearance_gap_chord_crossing_pairs":len(crossings_P),
        "both_strategies_agree_links":len(overlap),
        "agreed_links_in_topological_crossing":len(conflicted),
        "agreed_links_after_crossing_ABSTENTION":len(clean),
        "geometry_one_to_one":validate_unique(G,fragments),
        "appearance_one_to_one":validate_unique(P,fragments),
        "agreed_topology_conflict_free":not bool(crossing_conflicts(clean,fragments)),
        "independent_physical_ground_truth":False,
        "real_physical_yarn_identity_accuracy":None,
        "geometry_links":[list(x) for x in G],
        "appearance_links":[list(x) for x in P],
        "agreed_links_pre_topology":[list(x) for x in overlap],
        "topology_ambiguities":crossings_both,
        "intersection_ABSTAIN_unknown":[list(x) for x in sorted(conflicted)],
        "structure_only_consensus_UNKNOWN_PHYSICAL_IDENTITY":[list(x) for x in clean],
        "structure_only_candidate_paths_NOT_REAL_YARN_COUNTS":path_components(fragments,clean),
    }


def posthoc_audit(comp,review,fragments):
    """Human SAME labels inaccessible to graph candidate generation.

    UNLABELLED is unknown, not different physical yarn. Direct matches are
    descriptions of similarity to an operator hypothesis, NOT recall.
    """
    f={x["id"]:x for x in fragments}
    operator=[]
    for rel in review["relations"]:
        if rel["relation"]!="SAME_PHYSICAL_YARN" or rel["a"] not in f or rel["b"] not in f:
            continue
        a,b=rel["a"],rel["b"]
        if f[a]["u_start"]>f[b]["u_start"]:
            a,b=b,a
        operator.append((a,b))
    gset={tuple(x) for x in comp["geometry_links"]}
    pset={tuple(x) for x in comp["appearance_links"]}
    cset={tuple(x) for x in comp["structure_only_consensus_UNKNOWN_PHYSICAL_IDENTITY"]}
    groups=connected_positive_groups(
        [{"id":x["id"],"kind":"APPARENT_VISIBLE_YARN"} for x in fragments],
        review["relations"])
    groups_map={rid:i for i,group in enumerate(groups) for rid in group}
    operator_crossings=crossing_conflicts(operator,fragments)
    operator_sources=defaultdict(int)
    operator_targets=defaultdict(int)
    for source,target in operator:
        operator_sources[source]+=1
        operator_targets[target]+=1
    grouped_within={(a,b) for a,b in cset if a in groups_map and b in groups_map
                    and groups_map[a]==groups_map[b]}
    # Between different annotated components is NOT physical negative truth:
    # these human groups may be incomplete or represent unknown connections.
    group_unlinked=cset-grouped_within
    return {
        "operator_same_link_projected_chord_crossing_pairs_DIAGNOSTIC":len(operator_crossings),
        "operator_same_link_source_degree_excess":sum(max(0,v-1) for v in operator_sources.values()),
        "operator_same_link_target_degree_excess":sum(max(0,v-1) for v in operator_targets.values()),
        "consensus_links_within_a_known_operator_same_component":len(grouped_within),
        "consensus_links_between_UNLINKED_operator_groups_NOT_NEGATIVE_GT":len(group_unlinked),
        "operator_same_links_WEAK_PHONE_IMAGE_LABELS":len(operator),
        "operator_connected_groups_NOT_TRUE_YARN_COUNT":len(groups),
        "operator_link_directly_in_forced_geometry":sum(x in gset for x in operator),
        "operator_link_directly_in_forced_appearance":sum(x in pset for x in operator),
        "operator_link_directly_in_topology_consensus":sum(x in cset for x in operator),
        "operator_groups_touched_by_consensus":len({
            groups_map[a] for a,b in cset
            if a in groups_map and b in groups_map and groups_map[a]==groups_map[b]}),
        "operator_absent_links_are_not_independent_NEGATIVE_truth":True,
        "independent_physical_yarn_identity_accuracy":None,
        "note":"No SAME relationships were read before both assignment solutions were frozen",
    }


def shuffled_start_signatures_controls(fragments,calib):
    """Geometry-preserving PHOTO-SIGNATURE shuffle as a negative control.

    Seven predeclared normalized shifts, not chosen from the current labels or
    results. Preserve u/v geometry, orientation, A/B pitch and EACH source's
    end signature. Move only target-side start photo signatures cyclically.
    This destroys a portion of cross-gap appearance correspondence but does
    not create valid physical negative yarn GT.
    """
    n=len(fragments)
    if n<2:
        return []
    offsets=sorted({x%n for x in (
        1, max(1,n//8),max(1,n//4),max(1,n//3),
        max(1,n//2),max(1,(2*n)//3),max(1,(3*n)//4)
    ) if x%n!=0})
    ordered=sorted(fragments,key=lambda x:x["id"])
    control=[]
    for offset in offsets:
        switched=copy.deepcopy(ordered)
        for index,item in enumerate(switched):
            item["start_signature"]=copy.deepcopy(
                ordered[(index+offset)%n].get("start_signature"))
        # No human SAME relations or changed photo geometry in this call.
        edges=propose_candidates(switched,calib)
        comp=compare_structures(switched,edges)
        control.append({
            "circular_signature_shift_in_operator_stroke_order":offset,
            "photo_signature_control_NOT_REAL_NEGATIVE_GROUND_TRUTH":True,
            "operator_relations_used":False,
            "geometry_forced_matching_links":comp["geometry_links"],
            "appearance_forced_matching_links":comp["appearance_links"],
            "structural_consensus_edges":comp["structure_only_consensus_UNKNOWN_PHYSICAL_IDENTITY"],
            "structural_consensus_count":comp["agreed_links_after_crossing_ABSTENTION"],
        })
    return control


def paint(photo,fragments,comp,out):
    img=photo.copy()
    byid={x["id"]:x for x in fragments}
    for frag in fragments:
        a=tuple(np.rint(frag["start"]).astype(int))
        b=tuple(np.rint(frag["end"]).astype(int))
        cv2.line(img,a,b,(40,200,45),2,cv2.LINE_AA)
    for source,target in comp["structure_only_consensus_UNKNOWN_PHYSICAL_IDENTITY"]:
        a=tuple(np.rint(byid[source]["end"]).astype(int))
        b=tuple(np.rint(byid[target]["start"]).astype(int))
        cv2.line(img,a,b,(40,210,245),2,cv2.LINE_AA)
    h,w=img.shape[:2]
    scale=min(1.,1500/max(h,w))
    if scale<1:img=cv2.resize(img,None,fx=scale,fy=scale,interpolation=cv2.INTER_AREA)
    cv2.rectangle(img,(0,0),(min(img.shape[1],720),35),(25,30,40),-1)
    cv2.putText(img,"GREEN: OPERATOR SHORT STROKES / YELLOW: CONSENSUS STRUCTURE UNKNOWN",
                (6,22),cv2.FONT_HERSHEY_SIMPLEX,.41,(255,255,255),1,cv2.LINE_AA)
    cv2.imwrite(str(out),img)


def run(root:Path,out:Path,ids=("U20261013_01","U20261013_03","U20261013_06")):
    out.mkdir(parents=True,exist_ok=True)
    summary={
        "experiment":"P0_E6_2_GLOBAL_HYPOTHESIS_UNIQUENESS",
        "input_semantics":"PHONE_IMAGE_OPERATOR_REVIEW_DRAFT_NOT_REAL_YARN_GROUND_TRUTH",
        "physical_identity_accuracy":None,
        "human_SAME_labels_used_for_inference":False,
        "human_SAME_labels_only_posthoc_audit":True,
        "A3_holdout_used":False,
        "frozen_V4_V5_not_modified_or_run":True,
        "pixel_distance_cutoffs":False,
        "unverified_crossings_trigger_abstention_not_false_GTs":True,
        "unmatched_and_unlabelled_are_NOT_NEGATIVE_GTs":True,
        "samples":[],
    }
    for sid in ids:
        review=load_local_review(root,sid)
        photo,provenance=_camera_image(root,review)
        references=json.loads((root/"datasets/annotations/drafts"/(sid+".json")).read_text(encoding="utf-8"))
        calib=calibration_fields(references,provenance["crop_original_xyxy"][:2])
        fragments=create_fragments(photo,review,provenance,calib)
        edges=propose_candidates(fragments,calib)
        # The entire inference graph/solution is frozen before reading labels.
        comp=compare_structures(fragments,edges)
        # Counterfactual permutations are fixed independently of weak operator
        # labels; no parameter selection or image-specific threshold.
        null_controls=shuffled_start_signatures_controls(fragments,calib)
        audited=posthoc_audit(comp,review,fragments)
        for ctrl in null_controls:
            ctrl["WEAK_operator_direct_SAME_overlap_POSTHOC_NOT_accuracy"]=(
                posthoc_audit({
                    "geometry_links":ctrl["geometry_forced_matching_links"],
                    "appearance_links":ctrl["appearance_forced_matching_links"],
                    "structure_only_consensus_UNKNOWN_PHYSICAL_IDENTITY":
                        ctrl["structural_consensus_edges"],
                },review,fragments)["operator_link_directly_in_topology_consensus"])
        # A low or high null overlap is NOT formal statistical evidence of
        # real physical yarn identity with only weak same-photo labels.
        overlay=out/(sid+"_global_consensus_UNKNOWN.jpg")
        paint(photo,fragments,comp,overlay)
        with (out/(sid+"_global_hypotheses.json")).open("w",encoding="utf-8") as f:
            json.dump({"sample_id":sid,"image_sha":review["image_sha256"],
                "pitch_source":"A1_A2_OPERATOR_CONFIRMED_PHYSICAL_INTERVALS",
                "all_forwards_before_association":len(edges),
                "structural_competition":comp,"posthoc_operator_audit":audited,
                "geometry_held_constant_shuffled_photo_signatures_CONTROLS":null_controls,
                "physical_certification":None},f,ensure_ascii=False,indent=2)
        record={
            "sample_id":sid,"camera_original_image_verified":True,
            "operator_visible_strokes_NOT_YARNS":len(fragments),
            "possible_forward_connections":len(edges),
            "operator_reviewed_same_links_POSTHOC":audited["operator_same_links_WEAK_PHONE_IMAGE_LABELS"],
            "operator_same_groups_NOT_REAL_YARN_COUNT":audited["operator_connected_groups_NOT_TRUE_YARN_COUNT"],
            "naive_duplicate_predecessor_targets":
                comp["local_geometry_baseline"]["targets_with_multiple_predecessors"],
            "geometric_forced_max_matching":comp["global_geometry_links_FORCED_HYPOTHESES"],
            "appearance_forced_max_matching":comp["global_appearance_links_FORCED_HYPOTHESES"],
            "two_priority_agreed_hypotheses":comp["both_strategies_agree_links"],
            "consensus_with_crossing_abstained":comp["agreed_links_after_crossing_ABSTENTION"],
            "operator_links_directly_in_structural_consensus_NOT_RECALL":
                audited["operator_link_directly_in_topology_consensus"],
            "signature_shuffle_controls_count":len(null_controls),
            "signature_shuffle_control_direct_operator_overlaps_NOT_ACCURACY":[
                x["WEAK_operator_direct_SAME_overlap_POSTHOC_NOT_accuracy"]
                for x in null_controls],
            "signature_shuffle_control_consensus_size":[
                x["structural_consensus_count"] for x in null_controls],
            "consensus_links_within_annotated_operator_same_groups":
                audited["consensus_links_within_a_known_operator_same_component"],
            "consensus_links_across_UNLINKED_groups_not_false_GTs":
                audited["consensus_links_between_UNLINKED_operator_groups_NOT_NEGATIVE_GT"],
            "operator_same_link_chord_crossing_pairs_DIAGNOSTIC":
                audited["operator_same_link_projected_chord_crossing_pairs_DIAGNOSTIC"],
            "physical_yarn_count":None,
            "physical_yarn_identity_accuracy":None,
            "artifact_overlay":overlay.name,
        }
        summary["samples"].append(record)
        print(f'{sid} E6_2 fragments={len(fragments)} candidates={len(edges)} '
              f'naive_duplicate_targets={record["naive_duplicate_predecessor_targets"]} '
              f'forced_geometry={record["geometric_forced_max_matching"]} '
              f'forced_appearance={record["appearance_forced_max_matching"]} '
              f'agreement={record["two_priority_agreed_hypotheses"]} '
              f'crossing_veto_consensus={record["consensus_with_crossing_abstained"]} '
              f'forced_G_crossings={comp["geometry_gap_chord_crossing_pairs"]} '
              f'forced_P_crossings={comp["appearance_gap_chord_crossing_pairs"]} '
              f'operator_SAME_chord_crossings={record["operator_same_link_chord_crossing_pairs_DIAGNOSTIC"]} '
              f'consensus_within_annotated_groups={record["consensus_links_within_annotated_operator_same_groups"]} '
              f'consensus_across_UNLINKED_groups={record["consensus_links_across_UNLINKED_groups_not_false_GTs"]} '
              f'photo_signature_shuffle_WEAK_direct_overlaps='
              f'{record["signature_shuffle_control_direct_operator_overlaps_NOT_ACCURACY"]} '
              f'operator_posthoc_DIRECT_overlap='
              f'{record["operator_links_directly_in_structural_consensus_NOT_RECALL"]}/'
              f'{record["operator_reviewed_same_links_POSTHOC"]} '
              f'(NOT_PHYSICAL_IDENTITY_ACCURACY)',flush=True)
    (out/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return summary


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=ROOT)
    p.add_argument("--out",type=Path,default=Path("experiments/p0-e62-global-uniqueness"))
    args=p.parse_args()
    root=args.root.resolve()
    out=args.out if args.out.is_absolute() else root/args.out
    run(root,out)


if __name__=="__main__":
    main()
