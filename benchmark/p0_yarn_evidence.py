"""P0-1: physical-yarn versus texture COMPETING-EVIDENCE audit.

NEVER turn operator PHYSICAL_YARN_REFERENCE into a visible-segment mask.
A1/A2+verified interval calibrate candidate geometry; A3 is never fitted.
This module does NOT claim to classify physical yarns from a single RGB image.
It exports inspectable per-candidate evidence, unlabeled side controls, and an
explicit UNKNOWN decision until independent physical evidence labels exist.

This is an E1 experiment, not a new V4/V5 production recognizer.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import cv2
import numpy as np

from benchmark.first_yarn_lattice_evidence import infer_lattice
from benchmark.manual_annotation import segment_axis_deg, validate_annotation

ROOT = Path(__file__).resolve().parents[1]
HYPOTHESES = ("YARN", "GAP", "TWILL", "COLOR", "SHADOW", "UNKNOWN")
LABELS = ("PHYSICAL_YARN_VISIBLE", "GAP", "TWILL_TEXTURE",
          "COLOR_STRIPE", "SHADOW", "UNCERTAIN")
INDEPENDENT_SOURCES = ("MICROSCOPE_PHYSICAL_CONFIRMATION",
                       "MULTI_LIGHT_PHYSICAL_CONFIRMATION",
                       "DIRECT_PHYSICAL_INSPECTION")


def evidence_for_site(sample_id: str, site: dict, pitch: float) -> dict:
    """Optical evidence is NOT a calibrated physical identity probability."""
    observed = site.get("local_observations", [])
    real = [x for x in observed if x.get("y") is not None]
    supported = [x for x in real if x.get("supported") is True]
    n = len(real)
    ratio = len(supported) / n if n else 0.
    margins = [float(x["paired_flank_score"]) for x in supported
               if x.get("paired_flank_score") is not None]
    flank = float(np.median(margins)) if margins else None
    jitter = site.get("linear_drift_corrected_center_jitter_2x_px")
    smoothness = (max(0., 1.-float(jitter)/max(1., pitch*.12))
                  if jitter is not None else None)
    # Related optical terms are intentionally NOT treated as independent
    # evidence or multiplied into a physical-yarn probability.
    score = round(.7*ratio+.3*max(0.,min(1.,(flank or 0.)/.6)),4) if n else None
    status = ("UNCERTAIN_IMAGE_SUPPORTED" if site.get("image_evidence_supported")
              else "REJECTED_INSUFFICIENT_IMAGE_EVIDENCE")
    return {
        "candidate_id":f"{sample_id}:A:{site['nominal_physical_yarn_index']}",
        "family":"A",
        "annotation_semantics":"PHYSICAL_YARN_REFERENCE",
        "identity_hypothesis":"UNKNOWN",
        "competing_explanations":list(HYPOTHESES),
        "identity_status":status,
        "image_evidence_score":score,
        "physical_identity_probability":None,
        "count_eligible":False,
        "physical_identity_verified":False,
        "nominal_physical_yarn_index":site["nominal_physical_yarn_index"],
        "visible_support_intervals":site.get("candidate_supported_short_runs_zoom_native_xy", []),
        "inferred_occluded_intervals":None,
        "evidence":{
            "paired_boundaries":{"median_optical_contrast":round(flank,3)
                                 if flank is not None else None},
            "longitudinal_consistency":{"supported_windows":len(supported),
                                        "valid_windows":n,
                                        "fraction":round(ratio,3)},
            "track_stability":{"residual_px":jitter,
                               "relative_consistency":round(smoothness,3)
                               if smoothness is not None else None},
            "period_consistency":{"nominal_pitch_2x_px":round(pitch,3),
                                  "source":"A1_A2_OPERATOR_CONFIRMED_INTERVALS"},
            "fiber_morphology":None,
            "crossing_occlusion_topology":None,
            "independent_multiview":None
        },
        "rejection_reasons":[
            "NO_INDEPENDENT_PHYSICAL_IDENTITY_EVIDENCE",
            "Twill, dye and gap may have same optical line response",
        ],
    }


def validate_physical_evidence_labels(data):
    """No fabricated labels. Phone-only judgments are never independent GT."""
    if data.get("schema_version") != "1.0" or not isinstance(data.get("labels"),list):
        raise ValueError("physical-evidence label schema must be 1.0 with labels array")
    seen=set()
    for label in data["labels"]:
        if not isinstance(label,dict):
            raise ValueError("each independent evidence label must be an object")
        required=("candidate_id","sample_id","physical_fabric_id","image_sha256",
                  "label","evidence_source","reviewer","independent_review")
        if any(not label.get(x) for x in required):
            raise ValueError("evidence label requires nonempty provenance and reviewer fields")
        if label["candidate_id"] in seen:
            raise ValueError("duplicate candidate evidence label")
        seen.add(label["candidate_id"])
        if label["label"] not in LABELS:
            raise ValueError("unrecognized physical/texture label")
        if label["independent_review"] is not True:
            raise ValueError("labels used as GT must be independently reviewed")
        if label["evidence_source"] not in INDEPENDENT_SOURCES:
            raise ValueError("PHONE_ONLY is not independent physical yarn identity evidence")
    return data["labels"]


def extract_patch(img,xy,side=112):
    """Black-padding outside actual source photo; no reflected fake content."""
    h,w=img.shape[:2]
    x,y=(int(round(float(v))) for v in xy)
    x0=x-side//2; y0=y-side//2
    x1=x0+side; y1=y0+side
    patch=np.zeros((side,side,3),np.uint8)
    xx0=max(0,x0); yy0=max(0,y0); xx1=min(w,x1); yy1=min(h,y1)
    if xx0<xx1 and yy0<yy1:
        patch[yy0-y0:yy1-y0,xx0-x0:xx1-x0]=img[yy0:yy1,xx0:xx1]
    return patch


def gallery_triptych(img, center, normal, pitch, candidate_id, out_path):
    """Side samples are UNLABELED controls, NEVER hard negative labels."""
    displacement=np.asarray(normal,float)*(pitch*.5)
    a=extract_patch(img,np.asarray(center)-displacement)
    b=extract_patch(img,center)
    c=extract_patch(img,np.asarray(center)+displacement)
    out=np.hstack([a,b,c])
    header=np.full((48,out.shape[1],3),28,np.uint8)
    cv2.putText(header,"SIDE (unlabeled)  |  CANDIDATE  |  SIDE (unlabeled)",
                (3,20),cv2.FONT_HERSHEY_SIMPLEX,.40,(240,240,240),1,cv2.LINE_AA)
    cv2.putText(header,candidate_id[:43],(4,40),
                cv2.FONT_HERSHEY_SIMPLEX,.4,(150,220,210),1,cv2.LINE_AA)
    out_path.parent.mkdir(parents=True,exist_ok=True)
    if not cv2.imwrite(str(out_path),np.vstack([header,out])):
        raise IOError("cannot write evidence gallery")


def sample_gallery_center(site, visual):
    """Choose actual observed pixel or invert only a nominal hypothesis point."""
    short=site.get("candidate_supported_short_runs_zoom_native_xy",[])
    if short:
        run=max(short,key=len)
        return list(np.asarray(run,float).mean(axis=0))
    if visual is None:return None
    rotated,_,affine,origin=visual
    inv=cv2.invertAffineTransform(affine)
    pt=np.array([[[rotated.shape[1]*.5,
                   site["nominal_y_2x_px"]]]],np.float32)
    projected=cv2.transform(pt,inv)[0,0]+np.asarray(origin,float)
    return projected.tolist()


def run_e1(root:Path, out:Path, max_gallery_per_fabric=12):
    out.mkdir(parents=True,exist_ok=True)
    label_path=root/"datasets/physical_evidence_labels/local_patches.json"
    labels=validate_physical_evidence_labels(
        json.loads(label_path.read_text(encoding="utf-8")))
    # Treat label records as audit data, NEVER as fitter inputs or auto thresholds.
    known={row["candidate_id"]:row for row in labels}
    samples=[]
    for path in sorted((root/"datasets/annotations/drafts").glob("U20261013_*.json")):
        ann=validate_annotation(root,json.loads(path.read_text(encoding="utf-8")))
        if ann["review_state"]!="OPERATOR_REVIEWED":
            continue
        raw=(root/ann["image_path"]).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=ann["image_sha256"]:
            raise RuntimeError("stale image hash")
        img=cv2.imdecode(np.frombuffer(raw,np.uint8),cv2.IMREAD_COLOR)
        if img is None or (img.shape[1],img.shape[0])!=(ann["image_width"],ann["image_height"]):
            raise RuntimeError("source zoom native dimensions do not match annotation")
        inferred,visual=infer_lattice(img,ann)
        pitch=inferred.get("nominal_physical_pitch_2x_px")
        sites=inferred.get("sites",[])
        candidates=[evidence_for_site(ann["sample_id"],site,pitch) for site in sites]
        # Gallery balances high-support hypotheses and unsupported controls.
        support=[i for i,s in enumerate(sites) if s["image_evidence_supported"]]
        weak=[i for i,s in enumerate(sites) if not s["image_evidence_supported"]]
        chosen=support[:max_gallery_per_fabric//2]+weak[:max_gallery_per_fabric-max_gallery_per_fabric//2]
        a=math.radians(segment_axis_deg(ann["segments"]["reference"]))
        normal=(-math.sin(a),math.cos(a))
        for i in chosen:
            item=candidates[i]
            center=sample_gallery_center(sites[i],visual)
            if center is None:continue
            filename=(out/"patches"/(item["candidate_id"].replace(":","_")+".jpg"))
            gallery_triptych(img,center,normal,pitch,item["candidate_id"],filename)
            item["inspection_gallery"]=(filename.relative_to(out)).as_posix()
            item["inspection_center_zoom_native_xy"]=[round(v,2) for v in center]
        audited=[]
        for item in candidates:
            verified=known.get(item["candidate_id"])
            if verified:
                if verified["sample_id"]!=ann["sample_id"] or verified["image_sha256"]!=ann["image_sha256"]:
                    raise RuntimeError("physical evidence label refers to wrong source image")
                audited.append({"candidate_id":item["candidate_id"],"label":verified["label"],
                                "source":verified["evidence_source"]})
        samples.append({
            "sample_id":ann["sample_id"],"physical_fabric_id":ann["fabric_id"],
            "image_sha256":ann["image_sha256"],"label_semantics":"PHYSICAL_YARN_REFERENCE",
            "operator_A1_A2_interval_count":ann["same_family_intervals"],
            "operator_A3_used_for_candidate_scoring":False,
            "candidate_count_NOT_REAL_YARN_COUNT":len(candidates),
            "image_supported_count_NOT_REAL_YARN_COUNT":sum(
                site["image_evidence_supported"] for site in sites),
            "independently_verified_patches":audited,
            "candidates":candidates
        })
        print(f'{ann["sample_id"]}: candidate={len(candidates)} '
              f'optical_supported={sum(s["image_evidence_supported"] for s in sites)} '
              f'independent_labels={len(audited)}',flush=True)
    if len(samples)!=5:raise RuntimeError("expected five reviewed existing fabric photos")
    summary={"experiment":"E1_P0_PHYSICAL_YARN_VS_TEXTURE",
             "annotation_semantics":"PHYSICAL_YARN_REFERENCE",
             "image_only_scores_are_not_physical_identity_probabilities":True,
             "unlabeled_side_comparisons_are_not_negative_ground_truth":True,
             "physical_identity_accuracy":None,
             "actual_yarn_count_accuracy":None,
             "physical_identity_probability_calibrated":False,
             "has_independent_physical_labels":bool(labels),
             "reviewed_fabrics":len(samples),"samples":samples,
             "next_required_input":"Independently verified physical visible-yarn and non-yarn texture patches; do not use inferred reference-line pixels as segmentation GT."}
    (out/"summary.json").write_text(
        json.dumps(summary,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    return summary


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--root",type=Path,default=ROOT)
    parser.add_argument("--out",type=Path,default=Path("experiments/p0-yarn-evidence"))
    args=parser.parse_args()
    root=args.root.resolve()
    folder=args.out if args.out.is_absolute() else root/args.out
    run_e1(root,folder)


if __name__=="__main__":
    main()
