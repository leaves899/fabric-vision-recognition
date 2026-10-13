"""First-principles, annotation-blind candidate measurement of woven fabric.

No learned models, training, hidden annotation injection, or fabricated physical scale.
Outputs are CANDIDATE/UNAVAILABLE; never assert physical ground truth automatically.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import cv2
import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.signal import find_peaks, peak_widths

VERSION = "pure10-fp-v0.1.0"
STATUSES = ("CANDIDATE", "CONFIRMED", "UNAVAILABLE", "NOT_EVALUATED")
PARAMETERS = (
    "warp_direction_angle", "weft_direction_angle",
    "warp_arrangement", "weft_arrangement",
    "warp_apparent_width_grade", "weft_apparent_width_grade",
    "weave_structure", "warp_density_per_cm", "weft_density_per_cm",
    "surface_texture_and_color",
)


def entry(status="UNAVAILABLE", value=None, reason="", evidence=None):
    return {"status": status, "value": value, "reason": reason,
            "evidence": evidence or {}}


def _axis_error(a, b):
    return abs((a - b + 90) % 180 - 90)


def _image(path):
    # imdecode handles non-ASCII paths on Windows.
    raw = np.fromfile(str(path), dtype=np.uint8)
    im = cv2.imdecode(raw, cv2.IMREAD_COLOR)
    if im is None:
        raise ValueError(f"Cannot decode image: {path}")
    return im


def _preprocess(bgr, max_side=840):
    h, w = bgr.shape[:2]
    scale = min(1.0, max_side / max(h, w))
    if scale < 1:
        bgr = cv2.resize(bgr, (round(w * scale), round(h * scale)),
                         interpolation=cv2.INTER_AREA)
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    gray = lab[:, :, 0].astype(np.float32)
    # Local normalisation removes lighting gradients without assuming yarn color.
    detail = gray - cv2.GaussianBlur(gray, (0, 0), 12.0)
    detail = cv2.GaussianBlur(detail, (0, 0), 0.7)
    side = int(min(detail.shape[:2]) * 0.86)
    y, x = np.array(detail.shape[:2]) // 2
    square = detail[y-side//2:y-side//2+side, x-side//2:x-side//2+side]
    source = bgr[y-side//2:y-side//2+side, x-side//2:x-side//2+side]
    return square, source, scale


def _rotate(arr, angle):
    h, w = arr.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), float(angle), 1.0)
    return cv2.warpAffine(arr, matrix, (w, h), flags=cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_REFLECT_101)


def _acf(profile, max_lag):
    p = np.asarray(profile, np.float64)
    p -= np.mean(p)
    if np.std(p) < 1e-7:
        return np.zeros(max_lag + 1)
    fft_n = 1 << (2 * len(p) - 1).bit_length()
    spectrum = np.fft.rfft(p, fft_n)
    corr = np.fft.irfft(spectrum * np.conj(spectrum), fft_n)[:max_lag+1]
    corr /= np.maximum(1, len(p) - np.arange(max_lag+1))
    return corr / max(corr[0], 1e-8)


def _bands(square, dimension):
    """Three disjoint bands: candidate must recur across real spatial regions."""
    n = square.shape[1-dimension]
    for start, end in ((0.09, 0.36), (0.37, 0.63), (0.64, 0.91)):
        if dimension == 0:  # row profile, average columns
            yield square[:, int(start*n):int(end*n)].mean(axis=1)
        else:               # column profile, average rows
            yield square[int(start*n):int(end*n), :].mean(axis=0)


def _periodicity(square, dimension, min_period=5.0):
    profiles = list(_bands(square, dimension))
    size = len(profiles[0])
    max_lag = min(int(size * .16), 90)
    start = max(4, math.ceil(min_period))
    if max_lag <= start + 3:
        return {"score": 0., "period": None, "support": 0.}
    acfs = [_acf(p, max_lag) for p in profiles]
    # Median across independently observed bands penalizes isolated twill motifs.
    med = np.median(acfs, axis=0)
    peaks, _ = find_peaks(med[start:max_lag])
    peaks = peaks + start
    if not len(peaks):
        return {"score": 0., "period": None, "support": 0.}
    choices = []
    for period in peaks:
        vals = np.array([a[period] for a in acfs])
        consistency = float(np.clip(vals.min() / max(vals.max(), .01), 0, 1))
        harmonic = float(np.clip(med[2*period], 0, 1)) if 2*period <= max_lag else 0.
        # A distant dominant multiple is less convincing than local yarn pitch.
        strength = float(max(0., np.median(vals)))
        score = strength * (.65 + .35*consistency) + .12*harmonic
        score *= float(np.sqrt(start / period) * .25 + .75)
        choices.append((score, int(period), consistency, vals.tolist()))
    score, period, consistency, vals = max(choices)
    return {"score": round(score, 5), "period": period,
            "support": round(consistency, 4),
            "band_acf": [round(float(v), 4) for v in vals]}


def _candidate_rotation(detail, angle):
    rotated = _rotate(detail, angle)
    d = int(min(rotated.shape[:2]) * .69)
    h, w = rotated.shape[:2]
    view = rotated[(h-d)//2:(h-d)//2+d, (w-d)//2:(w-d)//2+d]
    a = _periodicity(view, 0)
    b = _periodicity(view, 1)
    # Both near-orthogonal structures are necessary; a strong diagonal alone
    # is not sufficient evidence for TWO distinct yarn systems.
    sa, sb = a["score"], b["score"]
    joint = float(math.sqrt(max(sa, 0.) * max(sb, 0.)))
    joint *= float(.65 + .35*min(sa, sb)/max(sa, sb, 1e-9))
    return joint, a, b


def _search_orientation(detail):
    coarse = []
    for angle in range(0, 90, 5):
        score, a, b = _candidate_rotation(detail, angle)
        coarse.append((score, angle, a, b))
    # Multiple basins help avoid locking onto the first dominant twill band.
    starts = sorted(coarse, reverse=True)[:3]
    angles = sorted({(a + delta) % 90 for _, a, _, _ in starts
                     for delta in range(-4, 5)})
    tested = []
    for angle in angles:
        score, a, b = _candidate_rotation(detail, angle)
        tested.append((score, angle, a, b))
    best = max(tested)
    ranked = sorted(tested, reverse=True)
    # Direction margin compares geometrically distinct hypotheses, not +/-1°.
    rivals = [v for v in ranked if min(abs(v[1]-best[1]),
               90-abs(v[1]-best[1])) >= 8]
    margin = best[0] - (rivals[0][0] if rivals else 0.)
    return best, float(margin)


def _centers(profile, estimated_period):
    if estimated_period is None:
        return {"centers": [], "widths_px": [], "cv": None, "coverage": 0}
    p = float(estimated_period)
    arr = np.asarray(profile, np.float64)
    hp = gaussian_filter1d(arr, max(.75, p*.10))
    hp -= gaussian_filter1d(arr, max(2.5, p*.95))
    candidate = []
    for sign in (+1, -1):
        signal = sign * hp
        indexes, properties = find_peaks(signal, distance=max(3, int(p*.70)),
              prominence=max(1e-6, np.std(signal)*.4))
        # Edge-like alternating half periods often create a false count. Only
        # measured ridges, NEVER synthetic interpolated comb positions.
        widths = peak_widths(signal, indexes, rel_height=.5)[0] if len(indexes) else []
        distances = np.diff(indexes)
        cv = float(np.std(distances)/np.mean(distances)) if len(distances) > 2 else 1.
        coverage = float(min(1., len(indexes)*p/max(1,len(arr))))
        mismatch = float(np.median(abs(distances-p))/p) if len(distances) else 1.
        score = coverage * math.exp(-3.0*mismatch) * math.exp(-cv)
        candidate.append((score, indexes, widths, cv, coverage))
    score, inds, widths, cv, coverage = max(candidate, key=lambda x:x[0])
    return {"centers": [float(x) for x in inds],
            "widths_px": [round(float(x), 3) for x in widths],
            "cv": round(float(cv), 5), "coverage": round(coverage, 4),
            "comb_score": round(float(score), 4)}


def _arrangement(lines, period, good):
    if not good or len(lines["centers"]) < 5 or lines["coverage"] < .45:
        return entry(reason="Insufficient independently located line centers")
    cv = lines["cv"]
    state = "较规则" if cv < .10 else ("局部不规则" if cv < .24 else "排列不规则")
    return entry("CANDIDATE", {"class": state, "spacing_cv": cv,
          "measured_centers": len(lines["centers"]), "mean_pitch_px": period},
          "Image-based peak positions; not individually verified yarn identities")


def _width_grade(lines, period, good):
    widths = [v for v in lines["widths_px"] if np.isfinite(v) and 1 <= v <= period]
    if not good or len(widths) < 5:
        return entry(reason="Yarn boundaries not supported by enough ridge profiles")
    p10, p50, p90 = np.percentile(widths, [10, 50, 90])
    ratio = float(p50 / period)
    grade = "相对较细" if ratio < .32 else ("相对中等" if ratio < .63 else "相对较粗")
    return entry("CANDIDATE",
        {"relative_grade": grade, "profile_half_prominence_width_px":
           {"p10": round(float(p10), 2), "p50": round(float(p50), 2),
            "p90": round(float(p90), 2)},
         "ridge_width_to_pitch_ratio": round(ratio, 4)},
        "Optical ridge half-prominence is NOT physically validated yarn diameter or Ne/tex")


def _hsv_color(bgr):
    view = cv2.resize(bgr, (min(256, bgr.shape[1]), min(256, bgr.shape[0])),
                      interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(view, cv2.COLOR_BGR2HSV)
    h, s, v = np.moveaxis(hsv, -1, 0)
    low = (s < 42)
    hue = h[~low]
    if len(hue) < 200:
        color = "黑/灰" if float(np.median(v)) < 130 else "灰/白"
    else:
        hue_value = float(np.median(hue))
        color = ("红" if hue_value < 9 or hue_value >= 174 else
                 "橙/棕" if hue_value < 22 else "黄" if hue_value < 38 else
                 "绿" if hue_value < 85 else "青" if hue_value < 105 else
                 "蓝" if hue_value < 135 else "紫/红")
    gray = cv2.cvtColor(view, cv2.COLOR_BGR2GRAY)
    detail = cv2.Laplacian(gray, cv2.CV_32F)
    return entry("CANDIDATE", {"color_family": color, "median_hsv":
       [round(float(np.median(t)), 1) for t in (h,s,v)],
       "texture_laplacian_std": round(float(detail.std()), 3),
       "surface_class": "高频肌理明显" if float(detail.std()) > 16 else "纹理较平缓"},
       "Descriptive color/texture statistics; NOT weave structure inference")


def _weave(rotated_gray, row, col, good_a, good_b):
    """Conservative photometric surface-dominance hypotheses at intersections.

    1 means horizontal-family dominance, 0 vertical-family dominance, -1 unknown.
    This is NOT a proof of physical yarn-over-yarn position.
    """
    rows, cols = row["centers"], col["centers"]
    n = len(rows)*len(cols)
    ev = {"candidate_crossings": n, "over_under_verified_cells": 0,
          "photometric_dominance_matrix": None,
          "organization_matrix_physical_truth": None}
    if not (good_a and good_b and len(rows) >= 7 and len(cols) >= 7):
        return entry(reason="Two physically distinct periodic families not supported",
                     evidence=ev)
    step_y = float(np.median(np.diff(rows)))
    step_x = float(np.median(np.diff(cols)))
    rad = max(2, int(.32 * min(step_x, step_y)))
    src = rotated_gray.astype(np.float32)
    dx = np.abs(cv2.Sobel(src, cv2.CV_32F, 1, 0, ksize=3))
    dy = np.abs(cv2.Sobel(src, cv2.CV_32F, 0, 1, ksize=3))
    matrix = np.full((len(rows), len(cols)), -1, np.int8)
    contrasts = []
    for i, y in enumerate(rows):
        for j, x in enumerate(cols):
            yy, xx = round(y), round(x)
            if min(xx, yy) < rad or yy+rad >= len(src) or xx+rad >= len(src[0]):
                continue
            energy_x = float(np.median(dx[yy-rad:yy+rad+1, xx-rad:xx+rad+1]))
            energy_y = float(np.median(dy[yy-rad:yy+rad+1, xx-rad:xx+rad+1]))
            ratio = (energy_y + 1e-3)/(energy_x + 1e-3)
            contrasts.append(float(abs(np.log(ratio))))
            if ratio > 1.7:
                matrix[i,j] = 1
            elif ratio < 1/1.7:
                matrix[i,j] = 0
    known = matrix >= 0
    count = int(known.sum())
    ev["photometric_dominance_matrix"] = matrix.tolist()
    ev["known_photometric_cells"] = count
    ev["photometric_coverage"] = round(count/matrix.size,4)
    ev["meaning"] = "1 horizontal dominant, 0 vertical dominant, -1 uncertain; NOT verified physical over-under"
    if count < 32 or count/matrix.size < .55:
        return entry(reason="Crossing photometric anisotropy is inconclusive",
                     evidence=ev)
    indices = np.indices(matrix.shape)
    ii,jj=indices[0],indices[1]
    templates = []
    for period, label, steps in ((2,"平纹",[1]),(3,"2/1斜纹",[1,-1]),
                                 (4,"3/1斜纹",[1,-1]),
                                 (5,"缎纹候选",[2,-2])):
        for sign in (1,-1):
            for shift in steps:
                for phase in range(period):
                    patt = (((ii+shift*jj+phase)%period)<(1 if sign==1 else period-1)).astype(np.int8)
                    accuracy = float((patt[known]==matrix[known]).mean())
                    templates.append((accuracy,label,period,shift,phase,sign))
    ranked=sorted(templates,reverse=True)
    best=ranked[0]
    competitors=[v for v in ranked[1:] if v[1]!=best[1]]
    separation=best[0]-(competitors[0][0] if competitors else .5)
    ev["best_template"]={"type":best[1], "photometric_match_fraction":round(best[0],4),
       "margin_to_other_weaves":round(separation,4), "period":best[2],
       "shift":best[3], "phase":best[4]}
    if best[0]<.89 or separation<.10:
        return entry(reason="Cannot distinguish physical weave from surface twill/color pattern",
                     evidence=ev)
    return entry("CANDIDATE", {"candidate_weave": best[1],
       "supporting_photometric_cells":count,
       "photometric_template_match":round(best[0],4)},
       "Unverified photometric template ONLY; not physical over-under proof",
       ev)


def _square_frame(image, corners):
    if corners is None:
        return image, None
    pts = np.array(corners, np.float32)
    if pts.shape != (4,2) or not np.isfinite(pts).all():
        raise ValueError("corners must be four ordered [x,y] points")
    area = cv2.contourArea(pts)
    if abs(area) < 100:
        raise ValueError("frame corners are degenerate")
    target = np.float32([[0,0],[999,0],[999,999],[0,999]])
    matrix = cv2.getPerspectiveTransform(pts, target)
    return cv2.warpPerspective(image, matrix, (1000,1000)), 200.0


def analyze(image_path, *, warp_family=None, corners=None, evidence_path=None):
    if warp_family not in (None, "a", "b"):
        raise ValueError("warp_family must be a, b, or omitted")
    p = Path(image_path)
    raw = _image(p)
    physical_roi, px_per_cm = _square_frame(raw, corners)
    detail, colored, scale = _preprocess(physical_roi)
    if min(detail.shape) < 120:
        raise ValueError("Image is too small for repeatability analysis")
    (joint, theta, a, b), margin = _search_orientation(detail)
    evidence = _rotate(colored, theta)
    measurement = _rotate(detail, theta)
    side = int(min(measurement.shape[:2]) * .69)
    h, w = measurement.shape[:2]
    ys, xs = (h-side)//2, (w-side)//2
    tile = measurement[ys:ys+side, xs:xs+side]
    tile_bgr = evidence[ys:ys+side, xs:xs+side].copy()
    a = _periodicity(tile, 0)
    b = _periodicity(tile, 1)
    row = _centers(tile.mean(axis=1), a["period"])
    col = _centers(tile.mean(axis=0), b["period"])
    # The score is a candidate gate, not empirically calibrated probability.
    good_a = a["score"] >= .14 and a["support"] >= .12 and row["coverage"] >= .45
    good_b = b["score"] >= .14 and b["support"] >= .12 and col["coverage"] >= .45
    axes = {
       "a": {"angle_image_deg": float(theta % 180), "period_px": a["period"],
             "periodicity": a, "line_evidence": row, "supported": bool(good_a)},
       "b": {"angle_image_deg": float((theta+90)%180), "period_px": b["period"],
             "periodicity": b, "line_evidence": col, "supported": bool(good_b)}
    }
    if px_per_cm is not None:
        # Homography is to 1000px / 5cm; analysis resize may reduce it.
        px_per_cm *= scale
    fields = {}
    for role, family in (("warp", warp_family),
                         ("weft", "b" if warp_family == "a"
                           else "a" if warp_family == "b" else None)):
        if family is None:
            for name in ("direction_angle", "arrangement",
                         "apparent_width_grade", "density_per_cm"):
                fields[f"{role}_{name}"] = entry(
                    reason="Yarn families detected but warp/weft physical identity not supplied")
            continue
        signal = a if family == "a" else b
        lines = row if family == "a" else col
        supported = good_a if family == "a" else good_b
        fields[f"{role}_direction_angle"] = (
            entry("CANDIDATE", round(axes[family]["angle_image_deg"], 3),
                "Geometric orientation hypothesis, not an operator-confirmed axis",
                {"periodicity": signal}) if supported
            else entry(reason="Orthogonal periodic response failed the evidence gate"))
        fields[f"{role}_arrangement"] = _arrangement(lines, signal["period"], supported)
        fields[f"{role}_apparent_width_grade"] = _width_grade(
            lines, signal["period"], supported)
        if px_per_cm and supported and signal["period"] and len(lines["centers"]) >= 5:
            value = round(float(px_per_cm/signal["period"]), 4)
            fields[f"{role}_density_per_cm"] = entry("CANDIDATE", value,
                "5cm frame calibrated, but physical single-yarn count is unverified",
                {"calibration_px_per_cm_in_analysis": round(px_per_cm,3)})
        else:
            fields[f"{role}_density_per_cm"] = entry(reason=(
                "Missing verified 5cm frame corners, or independent yarn-count evidence"))
    fields["weave_structure"] = _weave(tile, row, col, good_a, good_b)
    fields["surface_texture_and_color"] = _hsv_color(physical_roi)
    assert set(fields) == set(PARAMETERS)
    if evidence_path:
        for y in row["centers"]:
            cv2.line(tile_bgr, (0, round(y)), (side-1, round(y)), (30,220,30), 1)
        for x in col["centers"]:
            cv2.line(tile_bgr, (round(x), 0), (round(x), side-1), (40,40,235), 1)
        output = Path(evidence_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        cv2.imencode(".png", tile_bgr)[1].tofile(str(output))
    return {"engine_version": VERSION, "image": str(p),
            "image_sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            "annotation_used_in_inference": False,
            "physical_calibration": "provided_5cm_corners" if corners else "UNAVAILABLE",
            "yarn_identity": "operator_selected" if warp_family else "UNKNOWN",
            "coordinate_system": "homography_rectified" if corners else "source_image",
            "analysis_rotation_deg": float(theta),
            "joint_candidate_score": round(float(joint), 5),
            "orientation_ambiguity_margin": round(float(margin), 5),
            "axis_families": axes,
            "parameters": fields}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("image", type=Path)
    ap.add_argument("--warp-family", choices=("a", "b"),
                    help="Independent operator decision; never inferred from texture")
    ap.add_argument("--corners-json", type=Path,
                    help="JSON: [[tl_x,tl_y],[tr_x,tr_y],[br_x,br_y],[bl_x,bl_y]]")
    ap.add_argument("--output", type=Path)
    ap.add_argument("--evidence", type=Path)
    args = ap.parse_args()
    corners = json.loads(args.corners_json.read_text(encoding="utf-8")) if args.corners_json else None
    res = analyze(args.image, warp_family=args.warp_family,
                  corners=corners, evidence_path=args.evidence)
    output = json.dumps(res, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output + "\n", encoding="utf-8")
    else:
        print(output)


if __name__ == "__main__":
    main()
