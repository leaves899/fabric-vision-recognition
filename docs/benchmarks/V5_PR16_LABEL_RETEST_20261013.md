# Frozen V5 retest against PR #16 operator labels (2026-10-13)
Source PR16 commit: `da1c9961547dba48065016ae66da53b1ec7187ab`, with all original manual reference lines preserved. PR16 advanced later to `d1bce71928d5a2cbaf1e5464a895f8b4ddb71069`; compare confirms intervening commits changed workflow/diagnostic code only, **no annotation files**. Therefore this retest uses the latest reviewed annotations.

CI run: https://github.com/leaves899/fabric-vision-recognition/actions/runs/38366810961 (5/5 V5 runs succeeded).
Candidate traces are produced by unchanged frozen V4/V5 on native-pixel crop of the existing 2x zoom photo; output counts are not physical strand counts.

| sample | V5 A/B candidate count | independent axis err | PR16 apparent visible strokes | >=60% within 5px | >=60% within 10px | >=60% within 1/4 candidate period | >=60% within 1/2 candidate period |
|---|---:|---:|---:|---:|---:|---:|---:|
| 01 | 43/55 | 0.30° | 10 | 10/10 | 10/10 | 10/10 | 10/10 |
| 02 | 49/60 | 0.65° | 0 | n/a | n/a | n/a | n/a |
| 03 | 38/43 | 0.02° | 85 | 56/85 | 82/85 | 67/85 | 84/85 |
| 05 | 40/29 | 0.21° | 0 | n/a | n/a | n/a | n/a |
| 06 | 39/52 | 1.03° | 55 | 26/55 | 39/55 | 29/55 | 52/55 |

Total PR16 draft local strokes (01/03/06) **146/150** within half candidate pitch, **92/150** within 5px. Same-yarn relation consistency: 01: 9/9; 03: 70/70 relations eligible for geometric comparison. These are image-only DRAFT labels and do **not** establish pixel-level yarn centerline, physical identity, accuracy or precision.

Important correction: original A1/A2/A3 long-line labels are operator-inferred *physical yarn paths through occlusion*, not exact visible-segment centerlines. Sample 05's 16.85px and 06's 11.69px whole-reference distances must not, by themselves, be treated as proof of wrong yarn identity. New 06 data supports **broadly correct candidate-grid alignment with residual position shifts and some coverage gaps**. Sample 05 has no newly annotated visible short strokes, so no local short-stroke completeness judgment.

Twill pattern negatives remain unverified: 03 has 1/2 annotated twill lines near candidates within the half-pitch threshold, while 01/06 lines are oblique to both V5 families and are ineligible for same-direction audit. Do not claim successful yarn-vs-texture separation. No 5cm physical calibration or full-image density was verified.

**Evidence**: GitHub Actions artifacts from run linked above contain V5 JSON, candidate overlays, local apparent-yarn/twill overlay, per-stroke audit, position diagnostics and three-panel images.
**Conclusion**: V5 usable as human-direction-conditioned A/B candidate initializer; not verified as exact physical-yarn counting/identity detector. Do not merge the new test files to main without review.
