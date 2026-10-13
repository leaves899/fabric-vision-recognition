"""P0-E6.3: exact counterfactual structural identifiability of yarn hypotheses.

NO color/distance threshold fitting; operator positive/negative labels are
loaded only by the final audit function. This experiment determines whether
an apparent 'unique' global one-to-one matching is actually inevitable across
ALL maximum-cardinality graph matchings. Graph necessity is NOT physical-yarn
truth: maximum-cardinality itself is an unvalidated model assumption.

Counterfactuals remove one edge and, separately, FORCE each competing
source continuation. Equal cardinality proves mathematically indistinguishable
UNDER THE CARDINALITY OBJECTIVE, regardless of local optical scoring.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from collections import defaultdict

import cv2
import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import maximum_bipartite_matching

from benchmark.local_image_review import load_local_review
from benchmark.p0_operator_line_audit import _camera_image
from benchmark.p0_occlusion_continuity import calibration_fields, create_fragments, propose_candidates
from benchmark.p0_global_yarn_uniqueness import compare_structures
from benchmark.p0_native_occlusion_audit import audit_alternatives

ROOT=Path(__file__).resolve().parents[1]
CONTEXT_ID="U20261013_03"
CONFIRMATION_RELATIVE_PATH=(
    "datasets/physical_evidence_labels/operator_confirmations/"
    "U20261013_03_E63_counterexample.json"
)


def graph_from_fragments(fragments,edges):
    """Ordinal-ID bipartite adjacency independent of image scoring and labels."""
    ids=sorted(f["id"] for f in fragments)
    if len(ids)!=len(set(ids)):
        raise ValueError("duplicate fragment ID")
    ix={x:i for i,x in enumerate(ids)}
    seen=set()
    row,col=[],[]
    for e in edges:
        a,b=e["source"],e["target"]
        if a not in ix or b not in ix or a==b:raise ValueError("invalid edge")
        pair=(a,b)
        if pair in seen:raise ValueError("duplicate edge")
        seen.add(pair)
        row.append(ix[a])
        col.append(ix[b])
    graph=csr_matrix((np.ones(len(row),dtype=np.int8),(row,col)),
                     shape=(len(ids),len(ids)),dtype=np.int8)
    return ids,ix,graph


def maximum_cardinality(graph):
    """Maximum bipartite matching number; no physical truth interpretation."""
    if graph.shape[0]==0:return 0
    return int(np.count_nonzero(
        maximum_bipartite_matching(graph,perm_type="column")!=-1))


def max_links_with_edge_forced(graph,row,col):
    """Keep (row,col), forbid every other edge at row and col, solve remainder."""
    if not bool(graph[row,col]):return None
    rem=graph.tolil(copy=True)
    rem[row,:]=0
    rem[:,col]=0
    rem=rem.tocsr()
    rem.eliminate_zeros()
    return 1+maximum_cardinality(rem)


def remove_edge_cardinality(graph,row,col):
    if not bool(graph[row,col]):return None
    rem=graph.tolil(copy=True)
    rem[row,col]=0
    rem=rem.tocsr()
    rem.eliminate_zeros()
    return maximum_cardinality(rem)


def exact_structural_identifiability(fragments, edges, candidate_links=None):
    """Exact graph-only structural ambiguity certificate.

    A link is 'necessary' iff removing it reduces the MAX-CARDINALITY matching
    size. This is a *counterfactual within the chosen model*, not evidence
    that the edge is a real yarn or crosses a verified physical occlusion.

    A link from the E6.2 solution that can be replaced by a different maximum
    matching remains UNKNOWN. No geometry/image cost may silently select it.
    """
    ids,ix,g=graph_from_fragments(fragments,edges)
    k=maximum_cardinality(g)
    if len(ids):
        m=maximum_bipartite_matching(g,perm_type="column")
        witness=sorted((ids[i],ids[j]) for i,j in enumerate(m) if j!=-1)
    else:witness=[]
    necessary=[]
    for a,b in witness:
        if remove_edge_cardinality(g,ix[a],ix[b])<k:
            necessary.append((a,b))
    alternative_by_source=defaultdict(list)
    if candidate_links is not None:
        for edge in edges:
            alternative_by_source[edge["source"]].append(edge["target"])
    audits=[]
    for a,b in sorted(candidate_links or []):
        if a not in ix or b not in ix:raise ValueError("unregistered audit edge")
        if not bool(g[ix[a],ix[b]]):raise ValueError("audit edge not in graph")
        forced=max_links_with_edge_forced(g,ix[a],ix[b])
        drop=remove_edge_cardinality(g,ix[a],ix[b])
        other=[]
        for target in sorted(alternative_by_source[a]):
            if target==b:continue
            count=max_links_with_edge_forced(g,ix[a],ix[target])
            if count==k:other.append(target)
        audits.append({
            "source":a,"target":b,
            "forced_edge_max_cardinality":forced,
            "original_graph_max_cardinality":k,
            "remove_edge_max_cardinality":drop,
            "essential_in_ALL_max_cardinality_matchings":drop<k,
            "alternative_targets_for_same_source_admitting_equal_maximum":other,
            "alternative_target_count":len(other),
            "actual_physical_yarn_identity":"UNKNOWN",
            "assumption":"MAXIMUM_BIPARTITE_CARDINALITY_NOT_PHYSICAL_LAW"
        })
    return {
        "method":"EXACT_BIPARTITE_MAX_MATCHING_EDGE_REMOVAL_AND_FORCED_EDGE",
        "number_of_fragments":len(ids),
        "number_of_candidate_edges":len(edges),
        "max_cardinality_NOT_real_yarn_count":k,
        "edges_necessary_in_all_max_cardinality_matchings_NOT_REAL_GT":[list(e) for e in necessary],
        "necessary_edge_count_NOT_identity_accuracy":len(necessary),
        "model_is_cardinality_only_NOT_observed_physical_occlusion":True,
        "matching_graph_weak_operator_labels_used":False,
        "candidate_link_counterfactuals":audits,
        "structural_uniqueness_cannot_certify_physical_yarn":True,
    }


def posthoc_operator_confirmation(root,sid,cert,comp):
    """ONLY here can manual counterexample and human SAME labels be loaded."""
    if sid!=CONTEXT_ID:
        return {"human_confirmation_available":False,
                "independent_physical_ground_truth_accuracy":None}
    p=root/CONFIRMATION_RELATIVE_PATH
    if not p.exists():
        return {"human_confirmation_available":False,
                "independent_physical_ground_truth_accuracy":None}
    user=json.loads(p.read_text(encoding="utf-8"))
    if user["sample_id"]!=sid or user["audit_only_NOT_inference_input"] is not True:
        raise ValueError("operator audit provenance mismatch")
    original={tuple(x) for x in comp["structure_only_consensus_UNKNOWN_PHYSICAL_IDENTITY"]}
    aud={(x["source"],x["target"]):x for x in cert["candidate_link_counterfactuals"]}
    positives=[]
    negatives=[]
    for key,kind,arr in (
        ("positive","USER_SAME",user["operator_confirms_image_inferred_same_yarn"]),
        ("negative","USER_NOT_SAME",user["operator_rejects_same_yarn"])):
        for x in arr:
            e=(x["source"],x["target"])
            pair=aud.get(e)
            d={
                "pair":list(e),"operator_stance":kind,
                "was_E62_consensus_link":e in original,
                "has_same_cardinality_alternative_under_model":
                    bool(pair and pair["alternative_target_count"]>0),
                "essential_under_cardinality_model":pair["essential_in_ALL_max_cardinality_matchings"]
                    if pair else None,
                "is_independent_microscopic_physical_GT":False,
            }
            if key=="positive":positives.append(d)
            else:negatives.append(d)
    return {
        "human_confirmation_available":True,
        "source":"USER_DIRECT_CONFIRMATION_IN_CHAT_2026-10-13",
        "operator_positive_continuations":positives,
        "operator_rejected_continuations":negatives,
        "independent_physical_ground_truth_accuracy":None,
        "user_confirmed_cases_are_NOT_used_for_candidate_choice":True,
    }


def render_uncertainty(photo,fragments,comp,cert,out):
    """Photo overlay of currently contested *structural* E6.2 connectors.

    Display yellow for a graph-model necessary edge and RED for non-necessary
    contested ones; neither is a physically verified yarn.
    """
    img=photo.copy()
    fmap={f["id"]:f for f in fragments}
    essential={tuple(x) for x in cert["edges_necessary_in_all_max_cardinality_matchings_NOT_REAL_GT"]}
    counter={tuple(x) for x in comp["structure_only_consensus_UNKNOWN_PHYSICAL_IDENTITY"]}
    for f in fragments:
        a,b=[tuple(np.rint(q).astype(int)) for q in (f["start"],f["end"])]
        cv2.line(img,a,b,(60,180,55),2,cv2.LINE_AA)
    for a,b in sorted(counter):
        p=tuple(np.rint(fmap[a]["end"]).astype(int))
        q=tuple(np.rint(fmap[b]["start"]).astype(int))
        clr=(10,210,240) if (a,b) in essential else (25,55,225)
        cv2.line(img,p,q,clr,2,cv2.LINE_AA)
    h,w=img.shape[:2]
    sc=min(1.,1400/max(h,w))
    if sc<1:img=cv2.resize(img,None,fx=sc,fy=sc,interpolation=cv2.INTER_AREA)
    cv2.rectangle(img,(0,0),(img.shape[1],42),(17,20,30),-1)
    cv2.putText(img,"GREEN=OPERATOR STROKE / RED=REPLACEABLE / YELLOW=GRAPH-NECESSARY (NOT GT)",
                (6,25),cv2.FONT_HERSHEY_SIMPLEX,.46,(250,250,250),1,cv2.LINE_AA)
    if not cv2.imwrite(str(out),img):
        raise ValueError("unable to write overlay")


def render_operator_pair_audit(photo,fragments,posthoc,out):
    """NEVER use manually confirmed pair colors to alter inference."""
    img=photo.copy()
    positions={f["id"]:f for f in fragments}
    for f in fragments:
        a,b=[tuple(np.rint(p).astype(int)) for p in (f["start"],f["end"])]
        cv2.line(img,a,b,(55,160,50),1,cv2.LINE_AA)
    for kind,color in (("operator_positive_continuations",(70,220,70)),
                       ("operator_rejected_continuations",(30,40,240))):
        for item in posthoc.get(kind,[]):
            a,b=item["pair"]
            p=tuple(np.rint(positions[a]["end"]).astype(int))
            q=tuple(np.rint(positions[b]["start"]).astype(int))
            cv2.line(img,p,q,color,3,cv2.LINE_AA)
    if not cv2.imwrite(str(out),img):
        raise ValueError("unable to save review overlay")


def run(root:Path,out:Path,ids=("U20261013_01","U20261013_03","U20261013_06")):
    out.mkdir(parents=True,exist_ok=True)
    summary={
        "experiment":"P0_E63_COUNTERFACTUAL_GRAPH_UNIQUENESS_NOT_IDENTITY",
        "manual_counterexample_inference_leak":False,
        "not_fitted_to_sample03_or_any_operator_link":True,
        "A3_untouched":True,
        "no_fixed_pixel_cutoffs":True,
        "unresolved_physical_yarn_connections_report_UNKNOWN":True,
        "physical_yarn_identity_accuracy":None,
        "samples":[],
    }
    for sid in ids:
        rev=load_local_review(root,sid)
        photo,prov=_camera_image(root,rev)
        ref=json.loads((root/"datasets/annotations/drafts"/(sid+".json")).read_text(encoding="utf-8"))
        cal=calibration_fields(ref,prov["crop_original_xyxy"][:2])
        frags=create_fragments(photo,rev,prov,cal)
        edges=propose_candidates(frags,cal)
        comp=compare_structures(frags,edges)
        # Evidence/inference ends HERE. No human relationships were loaded.
        consensus=[tuple(x) for x in comp["structure_only_consensus_UNKNOWN_PHYSICAL_IDENTITY"]]
        # Audit ALL candidate forward links from E62 disputed sources, including
        # operator choices ONLY if present in candidate graph and never for tuning.
        sources={a for a,b in consensus}
        audit_links=sorted({(e["source"],e["target"]) for e in edges if e["source"] in sources})
        cert=exact_structural_identifiability(frags,edges,audit_links)
        optical=audit_alternatives(photo,frags,audit_links,cal["pitch"])
        (out/(sid+"_native_gap_observations_UNKNOWN.json")).write_text(
            json.dumps({"sample_id":sid,
                        "original_camera_image_only":True,
                        "operator_relations_excluded":True,
                        "optical_observations":optical},
                       ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        necessary={tuple(x) for x in cert["edges_necessary_in_all_max_cardinality_matchings_NOT_REAL_GT"]}
        consensus_necessary=sorted(necessary & set(consensus))
        # Then and ONLY THEN load the new USER-confirmed positive/negative case.
        posthoc=posthoc_operator_confirmation(root,sid,cert,comp)
        if sid==CONTEXT_ID and posthoc["human_confirmation_available"]:
            render_operator_pair_audit(
                photo,frags,posthoc,out/(sid+"_OPERATOR_ONLY_correct_vs_wrong.jpg"))
        render_uncertainty(photo,frags,comp,cert,out/(sid+"_E63_replaceability_NOT_physical_yarn.jpg"))
        record={
            "sample_id":sid,
            "visible_human_candidate_strokes":len(frags),
            "forward_candidate_links":len(edges),
            "maximum_cardinality":cert["max_cardinality_NOT_real_yarn_count"],
            "E62_force_assigned_structural_consensus_count":len(consensus),
            "necessary_under_all_max_matchings_count":cert["necessary_edge_count_NOT_identity_accuracy"],
            "E62_consensus_edges_necessary_under_cardinality_only":len(consensus_necessary),
            "E62_consensus_edges_REPLACEABLE_unknown":
                len(consensus)-len(consensus_necessary),
            "E62_consensus_graph_necessary_edge_ids_NOT_real_yarns":[list(x) for x in consensus_necessary],
            "user_operator_counterexample_posthoc":posthoc,
            "physical_yarn_identity_accuracy":None,
            "native_optical_gap_links_audited_NOT_verified":len(optical["links"]),
            "native_optical_certified_connections":0,
        }
        with (out/(sid+"_counterfactual_identifiability.json")).open("w",encoding="utf-8") as f:
            json.dump({"summary":record,"graph_certificate":cert},
                      f,indent=2,ensure_ascii=False)
        summary["samples"].append(record)
        print(f'{sid} E63 fragments={len(frags)} candidates={len(edges)} '
              f'maximum_cardinality={record["maximum_cardinality"]} '
              f'graph_essential={record["necessary_under_all_max_matchings_count"]} '
              f'E62_consensus={len(consensus)} '
              f'E62_replaceable={record["E62_consensus_edges_REPLACEABLE_unknown"]} '
              f'operator_positive_negative_POSTHOC_ONLY '
              f'physical_identity_UNKNOWN',flush=True)
        if posthoc.get("human_confirmation_available"):
            for category in ("operator_positive_continuations","operator_rejected_continuations"):
                for item in posthoc[category]:
                    print(f'{sid} E63_POSTHOC {category} {item["pair"]} '
                          f'previously_selected={item["was_E62_consensus_link"]} '
                          f'has_equal_cardinality_alternative='
                          f'{item["has_same_cardinality_alternative_under_model"]}'
                          f' (WEAK_OPERATOR_NOT_PHYSICAL_GT)',flush=True)
    (out/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return summary


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",type=Path,default=ROOT)
    ap.add_argument("--out",type=Path,default=Path("experiments/p0-e63-physical-identifiability"))
    x=ap.parse_args()
    root=x.root.resolve()
    run(root,x.out if x.out.is_absolute() else root/x.out)


if __name__=="__main__":
    main()
