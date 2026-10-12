# EXP-V15-001: Independent V1.5 reflectance-only Density MVP

## Problem / baseline

V5 relies on two operator-selected points to orient frozen V4 candidate lines. V1.5 calls for reflection/transmission metrology, but the available product contract is ordinary phone reflection photographs, optionally front/back, with a manually confirmed coplanar 5cm square. FFT/structure-tensor texture directions can be twill, not real yarn axes. No training/test leakage or back-filled GT allowed.

## GOAL and stop conditions

**G0 — Isolation:** All new algorithm implementation is under `experiments/v15_reflection/`. `demo/v5/` and `benchmark/` stay byte-for-byte unchanged. The branch will NOT be merged into main without a later, explicit decision.

**G1 — Executable MVP:** Gate 2, verified-frame optional rectification, two perpendicular candidate axes, five-strip projection/FFT/autocorr periods, independently calculated period/count densities, Gate 3 reasons, explicit `candidate_only`, all ten output parameter slots (including honest `UNAVAILABLE`). Synthetic test suite + GitHub Actions PASS. Deterministic repeated runs and 90° synthetic orientation test.

**G2 — Independent real-image accuracy:** Use an independently verified fabric-separated TEST partition containing **at least 10 distinct fabric IDs and two different weave families**, confirmed physical-scale frames and multi-cutline count GT for warp and weft. Report overall and per-fabric P95, MAPE, abstention coverage, harmonic failures, rotation consistency and candidate-vs-V5 comparison. **Target among accepted predictions: mean absolute density percentage error ≤2% for each axis and transparent ≥80% fabric-level coverage**. Report unconditional sample failures, never score only surviving samples.

**G3 — Production readiness:** Gate2/3 thresholds tuned exclusively on DEV, frozen before TEST; >1 independent phone capture per fabric; evidence overlay manually inspected; independent operator checks candidate peak-to-physical-yarn correspondence. RK3576 4GB with simultaneous frontend: actual time/RSS measurements. Never claim G3 from unit tests.

## Current state

G0 implemented by branching. G1 software CI PASS (GitHub Actions #38240635121; synthetic tests + unchanged benchmark regression + real uncalibrated smoke). G2 automatic orientation baseline FAILED on real operator-reviewed images (3/5 large angular errors), and G2 physical density / G3 **BLOCKED**, because existing public photos lack confirmed inner-square physical frame and real per-axis independent count GT; this cannot be fixed by synthetic annotation or by running a model repeatedly.

## Rules for iteration

Each change is accompanied by hypothesis, numerical benchmark, new failures, rollback criterion and full regression. No per-image parameter patches. FFT-only orientation is a hypothesis, never upgraded to manual truth. Fall back to manual two-point reference if uncertain. Physical warp/weft assignment must be separately confirmed.

## Verification commands

```bash
python -m unittest discover -s experiments/v15_reflection/tests -v
python -m unittest discover -s benchmark/tests -v
python -m unittest discover -s demo/v5/tests -v
```

The V5 suite may require separately installed V5 dependencies. G1 proof is an Actions log, not prose alone.
