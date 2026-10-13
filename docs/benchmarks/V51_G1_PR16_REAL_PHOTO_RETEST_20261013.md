# V5.1-G1 conservative local candidate refinement — measured outcome (2026-10-13)

## Source and reproducibility
- Experiment PR: #21, branch `experiment/v51-g1-image-local-refinement-20261013`, based on PR20/PR16 reviewed annotations.
- Frozen V4 SHA-256: `dde5d84193a3f3d02bb55ad72a8c2b9f2a640034563ed936736ad46808b8dad1`. Frozen V4/V5 outputs never altered.
- First run: https://github.com/leaves899/fabric-vision-recognition/actions/runs/38369837664 (five photos; 5/5 runtime success, 0/3 available local-image label groups improved).
- Conservative phase-preserving revision: https://github.com/leaves899/fabric-vision-recognition/actions/runs/38370468091 (five photos; 5/5 runtime success, but still **not accepted** for accuracy).
- Label provenance: PR16 `LOCAL_IMAGE_EVIDENCE_REVIEW` **DRAFT**, only 01,03,06 have short-stroke marks. These are not independent physical yarn identity ground truth, even though they are useful geometry probes. Two-point A1/A2/A3 lines are inferred whole-yarn trajectories, not pixelwise visible masks.

## Real photo comparison
Coverage = at least 60% of each selected apparent-yarn short-stroke sample points within a specified distance to candidate lines, on 2x enlarged unmarked crop.

| Sample | labeled apparent-yarn strokes | Original V5 <=5px | Raw G1 <=5px | Phase-preserving G1 <=5px | V5 <=10px | Phase-preserving G1 <=10px | V5 <=half candidate pitch | Phase-preserving G1 <=half pitch |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| U20261013_01 | 10 | 10 | 3 | 3 | 10 | 10 | 10 | 10 |
| U20261013_03 | 85 | 56 | 21 | 34 | 82 | 79 | 84 | 85 |
| U20261013_06 | 55 | 26 | 22 | 26 | 39 | 41 | 52 | 47 |
| **Total** | **150** | **92** | **46** | **63** | **131** | **130** | **146** | **142** |

02 and 05 have no newly saved local short strokes; both are executed and visually saved but their short-stroke coverage cannot be scored. Across all 5 photos A/B candidate counts and IDs stay unchanged; this G1 does not address physical count/density.

## Technical finding
G1 uses grayscale two-sided extrema and longitudinal multi-transect agreement, then optimizes offsets via Viterbi. On controlled synthetic curved ridges it improves position and passes a 90-degree rotation and blank-image abstention test. On real woven textiles, **strong optical ridges also belong to weave gaps, twill, dye changes and shadows**; they are not discriminative proof of yarn centerlines. The refiner follows these bright/dark profiles and degrades V5's already useful LightGBM-based localization.

A second iteration removed per-track global median phase and capped local residual adjustment at 0.17 candidate pitch; this reduces degradation but does not surpass V5 on real data.

**Decision: G1 accuracy gate FAILED; do NOT enable this output in user-facing V5 or merge it into main.** Keep experimental implementation for controlled comparisons only.

## Next focused experiment (G1.2)
Capture original frozen V4's **per-pixel LightGBM score maps** through optional adapter-side diagnostics, without modifying frozen algorithm weights/decisions. Compare the frozen probability support at original V5 track vs nearby normal offsets, and allow local adjustments only when original and independent longitudinal/multiscale evidence agree. Unknown/ambiguous cases abstain and keep V5. Once no-regression gate is demonstrated, test on new fabrics not involved in G1 iteration and only then consider default integration. Do not tune or certify yarn identification on this same group of PR16 DRAFT strokes.
