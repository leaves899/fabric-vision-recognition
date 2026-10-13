"""PR #16 DRAFT local visible-stroke audit of unchanged frozen V5/V4.
Physical long-line references are inferred whole-yarn trajectories, NOT pixel-center GT.
Phone-only local apparent-yarn and twill strokes are diagnostic, NOT physical identity truth.
Never turn these coverage values into validated per-yarn precision/recall or density.
"""
from __future__ import annotations
import argparse, json, math, sys
from pathlib import Path
import cv2
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"demo/v5"))
from v4_adapter import run_v4
from benchmark.manual_annotation import validate_annotation
from benchmark.local_image_review import validate_local_review
from benchmark.phase_offset_diagnostic import closest_track_distances, nearby_candidate_pitch

def axis(points):
    a,b=np.asarray(points,float)
    return float(np.degrees(np.arctan2(*(b-a)[::-1]))%180)

def axis_gap(a,b):
    return float(abs((a-b+90)%180-90))

def inside(points,origin,size):
    pts=np.asarray(points,float)-np.asarray(origin,float)
    return bool(np.all(pts[:,0]>=0) and np.all(pts[:,0]<size[0])
                and np.all(pts[:,1]>=0) and np.all(pts[:,1]<size[1]))

def run(sid, resultdir, *, track_override=None):
    raw=json.loads((resultdir/"v5_result.json").read_text(encoding="utf-8"))
    v5=raw["result"]
    meta=raw["original_image_provenance"]
    ann=validate_annotation(ROOT,json.loads((ROOT/"datasets/annotations/drafts"/(sid+".json")).read_text(encoding="utf-8")))
    local_path=ROOT/"datasets/physical_evidence_labels/manual_image_reviews"/(sid+".json")
    if local_path.is_file():
        local=validate_local_review(ROOT,json.loads(local_path.read_text(encoding="utf-8")))
    else:
        local={"review_state":"ABSENT","regions":[],"relations":[],"independent_physical_gt":False}
    path=ROOT/ann["image_path"]
    source=np.frombuffer(path.read_bytes(),np.uint8)
    image=cv2.imdecode(source,cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("cannot decode original image")
    import hashlib
    if hashlib.sha256(path.read_bytes()).hexdigest()!=meta["original_image_sha256"]:
        raise ValueError("source image mismatch")
    x0,y0,x1,y1=meta["crop_xyxy_original_px"]
    crop=image[y0:y1,x0:x1].copy()
    if [crop.shape[1],crop.shape[0]]!=meta["cropped_pixel_size_px"]:
        raise ValueError("image provenance crop does not match")
    v4=(run_v4(crop,float(v5["direction_evidence"]["v4_adapter_rotation_deg"]))
        if track_override is None else track_override)
    angleA=v5["direction_evidence"]["family_a_deg"]
    angleB=v5["direction_evidence"]["family_b_deg"]
    rel_ref=(np.asarray(ann["segments"]["reference"],float)-[x0,y0]).tolist()
    anchor_mid=np.mean(rel_ref,axis=0)
    pitches={}
    for name,track in (("A",v4["first"]),("B",v4["second"])):
        pitch,_=nearby_candidate_pitch(track,rel_ref,anchor_mid)
        pitches[name]=pitch
    lines=[]
    matched={}
    alltypes={}
    for region in local["regions"]:
        k=region["kind"]
        alltypes[k]=alltypes.get(k,0)+1
        geometry=region["geometry"]
        if geometry["type"]!="LINE":
            continue
        original_pts=geometry["points"]
        if not inside(original_pts,(x0,y0),(crop.shape[1],crop.shape[0])):
            lines.append({"region_id":region["id"],"kind":k,"status":"OUTSIDE_TEST_ROI"})
            continue
        local_pts=np.asarray(original_pts,float)-[x0,y0]
        deg=axis(local_pts)
        errA=axis_gap(deg,angleA) if angleA is not None else 90.
        errB=axis_gap(deg,angleB) if angleB is not None else 90.
        fam="A" if errA<=errB else "B"
        error=min(errA,errB)
        if error>20:
            lines.append({"region_id":region["id"],"kind":k,"status":"STROKE_DIRECTION_NOT_PARALLEL_TO_V5",
                          "stroke_axis_deg":round(deg,2),"nearest_family_direction_error_deg":round(error,2)})
            continue
        tracks=v4["first"] if fam=="A" else v4["second"]
        samples=np.linspace(local_pts[0],local_pts[1],15)
        # Union of candidate tracks may be spatially close even if each short
        # stroke does not line up with a continuous single trajectory.
        union=np.array(closest_track_distances(samples,tracks),float)
        pertrack=[]
        for idx,track in enumerate(tracks):
            dist=np.array(closest_track_distances(samples,[track]),float)
            if np.isfinite(dist).all():
                pertrack.append((round(float(np.median(dist)),3),idx,dist))
        best=min(pertrack,key=lambda v:v[0]) if pertrack else None
        pitch=pitches.get(fam)
        if pitch is None or pitch<=0: pitch=25.0
        # Tolerant fraction of local candidate period; these are descriptive
        # overlap diagnostics and NEVER independently verified physical GT.
        strict=.25*pitch
        loose=.50*pitch
        val={
           "region_id":region["id"],"kind":k,"status":"DIAGNOSTIC_ONLY",
           "family":fam,"axis_error_deg":round(error,2),
           "median_nearest_track_px":round(float(np.median(union)),2),
           "best_single_track_median_px":best[0] if best else None,
           "single_track_id":best[1] if best else None,
           "local_pitch_proxy_px":round(pitch,2),
           "sample_fraction_within_5px":round(float(np.mean(union<=5)),3),
           "sample_fraction_within_10px":round(float(np.mean(union<=10)),3),
           "sample_fraction_within_quarter_pitch":round(float(np.mean(union<=strict)),3),
           "sample_fraction_within_half_pitch":round(float(np.mean(union<=loose)),3),
           "single_track_fraction_within_half_pitch":round(float(np.mean(best[2]<=loose)),3) if best else None,
        }
        lines.append(val)
        matched[region["id"]]=val
    def describe(kind):
        items=[v for v in lines if v["kind"]==kind]
        inside_items=[v for v in items if v["status"]=="DIAGNOSTIC_ONLY"]
        others=[v for v in items if v["status"]!="DIAGNOSTIC_ONLY"]
        med=[v["median_nearest_track_px"] for v in inside_items]
        def count(key,threshold):
            return sum(x[key]>=threshold for x in inside_items)
        return {
            "total_saved":alltypes.get(kind,0),"parallel_and_inside_roi":len(inside_items),
            "excluded_or_outside":len(others),
            "median_nearest_track_px":round(float(np.median(med)),2) if med else None,
            "local_strokes_covered_at_least_60pct_within_5px":count("sample_fraction_within_5px",.6),
            "local_strokes_covered_at_least_60pct_within_10px":count("sample_fraction_within_10px",.6),
            "local_strokes_covered_at_least_60pct_within_quarter_pitch":count("sample_fraction_within_quarter_pitch",.6),
            "local_strokes_covered_at_least_60pct_within_half_pitch":count("sample_fraction_within_half_pitch",.6),
            "one_candidate_track_covers_at_least_60pct_within_half_pitch":count("single_track_fraction_within_half_pitch",.6),
        }
    relations={"total_saved":len(local["relations"]),"same_relation_testable":0,"same_relation_matching_track":0,
               "same_relation_different_track":0}
    for link in local["relations"]:
        if link["relation"]!="SAME_PHYSICAL_YARN":continue
        a,b=matched.get(link["a"]),matched.get(link["b"])
        if not a or not b or a["family"]!=b["family"] or a["single_track_id"] is None or b["single_track_id"] is None:continue
        if min(a["single_track_fraction_within_half_pitch"],b["single_track_fraction_within_half_pitch"])<.6:continue
        relations["same_relation_testable"]+=1
        if a["single_track_id"]==b["single_track_id"]:
            relations["same_relation_matching_track"]+=1
        else:
            relations["same_relation_different_track"]+=1
    result={
        "sample_id":sid,"source_pr":16,"pr16_source_sha":"da1c9961547dba48065016ae66da53b1ec7187ab",
        "v4_sha256":v5["v4"]["frozen_sha256"],"v5_source_unchanged":True,
        "local_review_state":local["review_state"],
        "physical_identity_ground_truth":False,
        "reference_semantics":ann.get("annotation_target","PHYSICAL_YARN_REFERENCE"),
        "roi_original_xyxy":meta["crop_xyxy_original_px"],
        "v5_family_a_deg":angleA,"v5_family_b_deg":angleB,
        "candidate_A_count":len(v4["first"]),"candidate_B_count":len(v4["second"]),
        "candidate_pitch_proxy":pitches,"marked_region_types":alltypes,
        "apparent_visible_yarn":describe("APPARENT_VISIBLE_YARN"),
        "twill_pattern":describe("TWILL_PATTERN"),
        "relations":relations,
        "all_local_stroke_evidence":lines,
        "interpretation":"Draft apparent-visible short strokes are not independent physical centerline GT. Small overlap distances are supportive only; misses/offsets and alias can coexist. TWILL strokes are negatives only at image-label level, not physically verified.",
    }
    (resultdir/"pr16_local_evidence_v5_audit.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    # Overlay is for independent human review, and does not imply acceptance.
    preview=crop.copy()
    for key,color in (("first",(45,50,245)),("second",(54,205,72))):
        for track in v4[key]:
            poly=np.rint(np.asarray(track)).astype(np.int32)
            if len(poly)>1:cv2.polylines(preview,[poly],False,color,1,cv2.LINE_AA)
    for region in local["regions"]:
        g=region["geometry"]
        if g["type"]!="LINE":continue
        pts=np.rint(np.asarray(g["points"],float)-[x0,y0]).astype(np.int32)
        color=(0,230,255) if region["kind"]=="APPARENT_VISIBLE_YARN" else (255,0,255)
        cv2.line(preview,tuple(pts[0]),tuple(pts[1]),color,2,cv2.LINE_AA)
    cap=min(1.,1300/max(preview.shape[:2]))
    if cap<1:preview=cv2.resize(preview,(round(preview.shape[1]*cap),round(preview.shape[0]*cap)),interpolation=cv2.INTER_AREA)
    banner=np.full((32,preview.shape[1],3),(25,25,25),np.uint8)
    cv2.putText(banner,"V5 A RED, B GREEN, LOCAL APPARENT YARN YELLOW, TWILL MAGENTA",
                (5,22),cv2.FONT_HERSHEY_SIMPLEX,.43,(255,255,255),1,cv2.LINE_AA)
    cv2.imwrite(str(resultdir/"pr16_local_strokes_overlay.jpg"),np.vstack([banner,preview]))
    summary={k:v for k,v in result.items() if k!="all_local_stroke_evidence"}
    print("PR16_V5_EVIDENCE_JSON="+json.dumps(summary,ensure_ascii=False,sort_keys=True),flush=True)
    return summary

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--id",required=True)
    p.add_argument("--result-dir",type=Path,required=True)
    args=p.parse_args()
    resultdir=args.result_dir if args.result_dir.is_absolute() else ROOT/args.result_dir
    run(args.id,resultdir)
if __name__=="__main__":main()
