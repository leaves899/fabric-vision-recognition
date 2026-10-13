# V1.5 V4 — Native-detail FFT/ACF experiment (2026-10-13)

**Independent research branch:** `experiment/v15-fft-acf-v4`, based on V3. Does not change `main`, frozen V4, or `demo/v5`. Its separate `experiments/v15_reflection/engine.py` now imports `orient_v4.propose_axes`.

## Hypothesis / mechanics

V3 relied on an entire photograph reduced to <=512 px, with radial-whitened 2D FFT and independent strip projections checked by 1D ACF. Fine yarn pitch can alias during downsizing. More importantly, FFT magnitude and the ACF derived from it are Fourier-dual and can agree on a twill pattern with no physical-yarn proof.

V4 retains V3 as the global proposal engine and adds:
1. 640 px *native-resolution* center tile, Gaussian smoothing at 0.8/1.5/2.5 px and principal Hessian curvature rather than raw gradient orientations, whose mixtures create diagonal ghost axes.
2. Only when two scales show reliable orthogonal directional evidence (pair-strength >=1.28 and dispersion <=8deg), reject global proposals separated >12deg from the native curvature lattice.
3. For V3 abstentions, run the same FFT/ACF proposal on two spatially separated *native* 512px tiles (not upsampled); promote to **still unvalidated** candidate only if both proposed axes agree to <=5deg and both lie within 9deg of the strong native Hessian direction.
4. Preserve explicit rejection and optional human two-point fallback; never claim identified physical yarns, verified warp/weft identity, or density GT.

All thresholds are provisional DEV research settings, not calibrated confidence scores or certified release requirements.

## Real GitHub Actions evidence

Source: [Actions run #38328234972](https://github.com/leaves899/fabric-vision-recognition/actions/runs/38328234972); V2/V3/V4 synthetic unit tests **30/30 PASS**, all 66/66 DEV images processed, all reviewed rotations included.

| DEV statistic | V3 | V4 |
|---|---:|---:|
| Direction proposals / 66 | 10 | 8 |
| Proposal fraction | 15.15% | 12.12% |
| Operator-reviewed references with proposals / 5 | 2 | 1 |
| Errors on accepted reviewed references | 0.805deg, 6.606deg | 0.805deg |
| Accepted reviewed references with error >5deg | 1 | 0 |
| Operator-reviewed all-rotation stable proposed samples | 2 | 1 |

The V4-rejected previously incorrect candidate was U001 (V3 error 6.606deg); V4 still accepts P001 (0.805deg). Five reviewed reference photos are not a reliable estimate of population accuracy; rejected photos must remain in the coverage denominator.

## Historical archive six fabric front/back images

12 rectified photographs, **no independent true physical axis or density GT**:
- V3 proposed 3/12.
- V4 proposed 2/12, rejecting the 3 previously accepted 37-41deg macroscale hypotheses after a native Hessian conflict, and recovering two distinct proposals on images 4(2) and 5(2), about 58.5deg and 56.0deg respectively. Those recovered values are NOT verified correct.
- Local desktop mean wall-clock: V3 68.8ms/image; V4 202.7ms/image. No RK3576 benchmark.

## Acceptance decision

**G2 NOT_PASSED, true physical density G2 NOT_EVALUATED.** All 66 repository images are DEV, zero frame-confirmed 5cm squares, zero independent physical counted-root labels, zero eligible TEST. Higher-quality images alone do not create a certified ground truth. The ≥80% fabric-level coverage and ≤2% per-axis density MAPE acceptance thresholds remain unproven and currently missed by proxy proposal coverage.

V4's defensible gain is better **error abstention on U001**, with a coverage penalty. Do not promote this to the production V5 pipeline.

## Next hard requirement

Build an independent, fabric-disjoint 10+ fabric dataset with operator-confirmed true 50mm square, real yarn axis references, multiple hand-counted crossing cutlines, and record photographic rotation variation. Evaluate angle precision and both axes' density MAPE, P95, harmonic doubling, proposed/abstained coverage, split leakage, and RK3576 resident memory with frontend running. Only then can an 80% / 2% release claim be made.
