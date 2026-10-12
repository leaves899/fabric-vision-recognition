# EXP-V15-001 — first executable reflectance-only baseline (2026-10-12)

Branch: `experiment/v15-reflectance-engine`, isolated from V5. Implemented Gate2, 50mm coplanar frame rectification, manual or unvalidated FFT direction, 5-strip projection/FFT/autocorrelation pitch, count-vs-spacing cross-check, reject reasons and candidate-only ten-slot JSON. No transmission pictures.

## Actual reproducible CI

- Commit `a98df3442a8ee4cb6095182e94f841a0251a3e8d`; GitHub Actions run #38240635121 (PASS).
- Synthetic experiment unit/protocol tests: 13/13. Unmodified existing benchmark regression: 47/47.
- Real uncalibrated denim smoke: `LOW_CONFIDENCE`; both physical densities null (PASS of anti-hallucination safety).
- Reviewed real-photo audit: 5 operator-reviewed photos with matching SHA, 0 missing/mismatched files. Real physical density GT: 0 eligible samples; no real density MAPE/P95 may be stated.

## Real reflection photo orientation diagnostic

Only the *nearest unlabelled axis-family* angular error to the human-clicked reference axis is shown, not true physical yarn instance accuracy. It allows choosing `theta` or `theta+90` to avoid falsely penalizing warp/weft identity ambiguity.

| Photo | FFT patch dispersion | Nearest operator-reference axis error | Auto status |
|---|---:|---:|---|
| P001 | 1.3310° | 1.3118° | proposed, not validated |
| T001 | 5.6656° | 36.5132° | proposed, **wrong orientation risk** |
| T004 | 1.2691° | 31.0617° | proposed, **wrong orientation risk** |
| T007 | 0.0000° | 31.8125° | proposed, **wrong orientation risk** |
| U001 | 87.7802° | 5.5779° | abstained as unstable |

**Failure mode:** small patch-to-patch FFT dispersion cannot prove true yarn alignment: twill surface texture can produce strongly consensual but false axes. Therefore this algorithm is not a reliable unattended replacement for V5 manual two-point reference. The alternative manual-direction-conditioned projection is not an auto direction validation.

## Gate 2 / Gate 3 and release rules

- Candidate pitch positions represent periodic image-intensity responses, NOT identified physical yarns. Counting them is not a trustworthy density until independent multi-cutline counts establish correspondence.
- 50mm calibration requires explicit physical frame confirmation; missing scale never produces roots/cm.
- Capture `mm/px` is assessed at native input frame edge resolution; working ROI `mm/px` is separately reported because decimation to <=1792px cannot improve native capture resolution.
- `CANDIDATE`, `LOW_CONFIDENCE`, `UNAVAILABLE` and `NOT_EVALUATED` are not interchangeable with confirmed truths.
- GOAL G1 is software-execution evidence only. GOAL G2 remains FAILED / NOT_EVALUATED for automatic true-axis and real physical density. GOAL G3 device and production acceptance is not measured.

## Next iteration (not image-specific tuning)

1. Diagnose direction method disagreement (local phase periodicity, two-family orthogonal support, twill vs real yarn direction); add stricter abstention to avoid high-confidence wrong orientation.
2. Create independent 5cm-frame, fabric-separated verified physical count GT: at least 10 fabrics, two weave families, multi-cutline counts for both axes. Keep TRAIN/VALIDATION/TEST fabric-disjoint.
3. Compare V5 manual-axis conditional baseline vs new algorithm on the same frozen test set. Release only if target error, coverage, P95 and false-orientation conditions pass.
4. Validate original high-resolution crop, width P10, repeat capture and RK3576 4GB alongside frontend before actual engine acceptance.

Evidence: https://github.com/leaves899/fabric-vision-recognition/actions/runs/38240635121
