# Symmetric valley V3 falsification + operator physical-yarn direction audit — 2026-10-14

**Experimental status: NOT READY FOR V5.** V3 prototype was transcribed verbatim from the user's latest proposed algorithm; the separate diagnostic wrapper explicitly refuses to claim physical yarn identity. No code in main or V5 has been modified.

## Experiment reproducibility

- Code: `experiments/v15_reflection/symmetric_valley_user_v3.py` (original), `symmetric_valley_v3_guarded.py` (honest status), `audit_symmetric_valley_v3.py` (real operator annotations).
- Archived local DEV: twelve `rectified_input.png` files from `feasibility_51.zip` (six unrelated front/back pairs).
- Newly added *actual operator reference GT*: current `main` five `U20261013_{01,02,03,05,06}.json` labels + exact native `center_2x.jpg` paths, all verified against supplied `image_sha256`. `04` excluded, missing physical reference label.
- Ground truth means **operator-confirmed physical-yarn direction**, NOT confirmed visible segment pixels, seam centerline pixels, warp/weft identity, absolute 5cm scale, or individually counted yarn density. The reported angle error is the more permissive error to the **nearest of two unlabelled yarn families**, not an identified warp/weft accuracy.
- CI: [run 38498002402](https://github.com/leaves899/fabric-vision-recognition/actions/runs/38498002402), [operator audit JSON artifact](https://github.com/leaves899/fabric-vision-recognition/actions/runs/38498002402/artifacts/11863954200). All existing tests and V3 negative controls passed.

## Latest operator annotations — V2 vs V3

| ID | Operator family 1 | Operator family 2 | V2 candidate / nearest error | V3 candidate / nearest error |
|---|---:|---:|---:|---:|
| 01 | 161.617° | 73.764° | 53.75° / **20.014°** | 10.00° / **28.383°** |
| 02 | 162.106° | 71.391° | 16.75° / **34.644°** | 163.00° / **0.894°** |
| 03 | 161.086° | 69.418° | 1.00° / **19.914°** | 166.00° / **4.914°** |
| 05 | 90.390° | 0.585° | 74.00° / **16.390°** | 75.50° / **14.890°** |
| 06 | 85.664° | 175.301° | 76.75° / **8.914°** | 76.50° / **9.164°** |

| Metric on 5 operator-labelled DEV samples | V2 | V3 |
|---|---:|---:|
| Candidates (raw accepted) | 5/5 | 5/5 |
| Mean nearest-family error | **19.975°** | **11.649°** |
| Error <= 3° | 0/5 | 1/5 |
| Error <= 5° | 0/5 | 2/5 |
| Error > 8° among accepted | 5/5 | 3/5 |
| Real verified root count accuracy | not measured | not measured |

**V3 fails the proposed >=90% true-yarn-hit condition** on these 5 examples; raw `reject_reason="verified"` must not be called a physical verdict. This is only a 5-image DEV reference, not independent TEST.

## Historical 12 front/back images — V3 direction proposals

- V2: 12/12 accepted; V3: **12/12 accepted**, four quarter-turn state and axes invariant in 12/12.
- Arbitrary 15°, 30°, 45° rotations: V3 within 5° of the rotation-predicted **original unverified candidate** in **8/12, 9/12, 7/12** samples respectively. Old V2 had 10/12 at each tested rotation. Quarter-turn reproducibility does not imply correctness.
- 6/12 V3 candidates fall between 11.9° and 12.3° away from measured macro texture angle: exactly where the code forces `non_pattern_mask >=12°`. This is selection-induced displacement from the main pattern, not independent yarn discovery.
- `estimated_yarn_pitch_px` on all twelve only equals **6.0** or **8.4** px, because the estimator is `2*median(best_crown_dist)` where `best_crown_dist` was only allowed to take input values **2.0, 3.0, 4.2** px. This is a restricted template scale, NOT a detected periodic spacing; must not be used for 5cm density or harmonic correction.

## Strict falsification: synthetic images WITHOUT ANY physical yarn

| Synthetic condition | Raw V3 | Error type |
|---|---|---|
| 58° strong thin optical shadow stripes | Rejects (peak at 58.5° but flagged pattern overlap) | correct rejection |
| 58° broad optical shadow stripes | Rejects for low detected physical seam score | correct rejection |
| 58° **subtle** optical shadow stripes | **accepts 70.5°**, reports `verified` | false physical claim; forced subpeak |
| 58° /148° synthetic printed orthogonal crosshatch | **accepts 146.5°**, reports `verified` | false positive, 2D signal is not interlacing |
| 58° dot-modulated optical raster | **accepts 46.0°**, reports `verified` | false positive despite modulation |
| white float-only dots, no seams | Rejects | correct negative |
| synthetic 78° weak seams + 2D dots | accepts 78.5° | reasonable synthetic directional response |
| 78° straight microseams alone | rejects despite true generated dark lines | synthetic false negative due macro overlap/absence of 2D pattern |

These synthetic images test optical feature identifiability, not woven-fabric generalization.

## Mathematical / implementation audit of the proposed three constraints

1. The bilateral crowns are still *brightness curvature* on the same pixels as the valley; neither finite physical yarn widths nor separate individual entity identities were detected. Any properly modulated printed stripe can have the same valley-crown-valley signatures.
2. The claimed 'cross-occlusion same-yarn continuity' is **NOT implemented**. The code measures a local/global gradient energy ratio only. There is no detection of occluder intervals, no pairing of segments, no across-occlusion displacement measure `e_perp`, and no identity-competition test. Printed crosshatching fools this check.
3. 'Non-repeat pitch' is **NOT implemented**. The function calculates a median of the three predefined shoulder sampling distances and supplies no actual transverse repeated-root counting or rejection of different-root duplicates.
4. The 'macro pattern avoidance' fallback automatically picks a peak >=12° away if it is >1.8 * the histogram median. This criterion becomes trivial when the median approaches zero; it artificially accepts some optical alternatives.
5. Positive Hessian/negative Hessian curvature and two orthogonal optical gradient families do **not** prove actual warp/weft or face/back duality. The images do not prove side-specific identity.

## Decision

The new method is a useful **image-evidence generator**, with an exploratory mean nearest-family angle error decrease from ~20° to ~12° on five labelled samples. It is **not** a validated physical detector and does not reach real-yarn direction hit, per-yarn pitch, root/cm or deployment requirements.

Next work should target independently verifiable *local physical continuity*, using the existing `PHYSICAL_YARN_REFERENCE` lines as **directions and identity references**, with visible-region reviews as weak/noisy evidence, but never as pixel-level GT. Direct hypothesis competition with negative printed-grid controls must be required. Do not optimize fixed angle intervals to these five DEV photos.
