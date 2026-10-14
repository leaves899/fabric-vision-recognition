# V1.5 half-wave dark seam ablation — 2026-10-14

## Status: RESEARCH ONLY — not physically verified

Experiment lives on `experiment/v15-dark-seam-ablation-20261014`. The old V1.5 V4 and official V5 are untouched. Code: `experiments/v15_reflection/dark_seam_study.py`. This never certifies warp/weft, physical yarn centerlines, 5cm density, or weave.

## User proposal: what was actually tested

Half-wave dark transform `max(0, background-L)`, bright-dot exclusion mask, Hessian micro-ridge orientation, and a comparison between a Gaussian-mean background and a **true local median**. The suggested code labels GaussianBlur as "local median"; that is mathematically false. A Gaussian mean near white bright points creates dark negative halos around them.

The proposed Hessian angle `0.5 atan2(2Ixy, Ixx-Iyy) + 90°` is the *normal* of a bright ridge in the inverted dark-channel. Its tangent is `0.5 atan2(...)` without `+90°`. On straight-ridge synthetic images at 0, 30, 60, 90, 120, 150 degrees, corrected tangent error was <1°.

## Actual photographic experiment

User-provided `feasibility_51.zip`, 6 front/back pairs (12 calibrated-size 1200px images). No independently reviewed true physical yarn axes for these twelve; **angle accuracy NOT_EVALUATED**. All outcomes below are candidate diagnostics, not correctness.

| DEV metric | Observation |
|---|---:|
| Raw half-wave Hessian emitted image-ridge candidate | 12/12 |
| Mask keeps only | 4.42%–19.28% of pixels |
| Five-strip / four-tile-style spatial candidate consistency (local script) | 8/12 |
| Previous V1.5 V4 direction proposals | 2/12 |
| Gaussian vs median direction agreement | 11/12 |
| Double-background decision+angle stable at 0/90/180/270 | 9/12 |

The leftover masked-dark image still visibly consists partly of bright-float outlines and optical shadows. **Neither 11/12 proposals nor 9/12 rotations is validated physical yarn accuracy.**

## Positive / negative controls

- Optical dot lattice with **no dark yarn seams at all**: direct half-wave/Hessian emits a false ~91° axis. Two-background proposal correctly abstains. This is a necessary regression guard against halo hallucination.
- Synthetic dot lattice plus physically constructed weak 78° dark seams: proposed axis ~77.75°, all four quarter-turn rotations consistent.
- Synthetic thin straight ridges test Hessian tangent geometry.

## Lattice inversion caution

The displayed algebra for `d1=u+v, d2=u-(R-1)v` is correct **only if d1 and d2 are known, signed, full 2D displacement vectors with confirmed lattice indexes**. Two stripe angles and spacings obtained from FFT are not those vectors. Treating `d1=13*[cos 58°,sin 58°]`, `d2=30*[cos(-32°),sin(-32°)]`, and `R=4` as if they were indexed displacements produces `u≈20.43°`, `v≈124.57°`, not `78°/-12°`, and u/v are not perpendicular. Never force lattice inversion or a hard-coded `14–35°` 'twill correction' as a physical measurement.

## Acceptance

**Do not replace V5/manual direction**. This research improves negative-control rejection but also accepts many optical ridges in real photographs. Next research: require two-sided yarn shoulders, local ridge continuity without float-edge overlap, explicit alternative hypothesis competition and fabric-disjoint, operator-reviewed test data. No eligible absolute pitch/density ground truth => G2 NOT_EVALUATED. Do not merge based on synthetic tests.

Local reproducible figure and report are supplied as companion artifact to the user. The CI workflow tests both new synthetic falsification controls and old V1.5 regression tests.
