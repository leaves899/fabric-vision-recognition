# V5.1 G1.2 + G1.3 five-photo real-image evidence (2026-10-13)

Baseline is frozen V4/V5; no production source changed. PR16 phone-image short strokes are DRAFT and not physically independent yarn centerline ground truth. Operator A1/A2 are distinct physical-yarn reference trajectories, potentially occluded, and A3 is a separate withheld approximate trajectory.

## G1.2: original frozen LightGBM probability and photo morphology consensus
- Experimental PR #22, run: https://github.com/leaves899/fabric-vision-recognition/actions/runs/38372942006
- Read-only probe extracts **the original** frozen V4 s1/s2 model scores in a disposable runtime copy. It leaves checksum-verified frozen V4/V5, its weights, its decisions, and the original V5 output unchanged.
- 5/5 photo matrix runs successful; original candidate counts/IDs preserved.
- 5-pixel photo-only visible short stroke coverage (01/03/06): **V5 92/150 vs G1.2 92/150**; each of 01 10/10, 03 56/85, 06 26/55 unchanged.
- This is **no measurable gain**, not a new 92/150 physical identity accuracy claim. B-family track edits on unlabelled regions are not proven non-regressive.

## G1.3: OPTIONAL second operator yarn and verified spacing
- Experimental PR #23, run: https://github.com/leaves899/fabric-vision-recognition/actions/runs/38373631734
- Inference only receives A1, A2 and their human-verified physical-yarn interval count. It never reads A3, or the image short-stroke GT, during fitting and model acceptance. This mode has **more operator inputs than original V5**.
- A3 values below are held-out MEDIAN GEOMETRY RESIDUALS from an approximate whole-yarn trajectory, NOT pixel-precise visible centerline GT. Units: pixels in interpolated 2x photo.

| Sample | nearest V5 candidate index intervals / physical operator intervals | A3 original to assisted (px) | Decision |
|---|---|---|---|
| 01 | 4 / 3 | 7.213 → 7.213 | ABSTAIN: noninteger alias ambiguity |
| 02 | 6 / 6 | 5.262 → 6.320 | Assisted 2-anchor grid accepted, A3 regressed |
| 03 | 6 / 5 | 2.278 → 2.278 | ABSTAIN: noninteger alias ambiguity |
| 05 | 1 / 2 | 3.036 → 3.036 | ABSTAIN: fewer candidate indices than verified operator intervals |
| 06 | 2 / 4 | 6.756 → 6.756 | ABSTAIN: fewer candidate indices than verified operator intervals |

No G1.3 measurable general improvement. The 05 and 06 index gap mismatch may be caused by missed candidate yarn or phase/index alias, and must NOT be represented as proven individual real-yarn misses. A model should never invent extra physical yarn lines from operator-provided counts alone.

## Gate and next move
1. **Do not promote G1.2 or G1.3 as improved accuracy**; keep V5 as the default. Keep research PRs Draft.
2. The next falsifiable experiment is local *candidate supplementation*: image-only score response and independent occlusion-window continuity evidence must BOTH support a genuinely new candidate between A1/A2 positions. Interpolating human spacings yields only a hypothesis. Keep UNKNOWN unless independent image evidence is sufficient.
3. Evaluate the A3 withheld track geometry and cross-fabric photo-only matched true/false contrast *without using withheld labels for hyperparameter selection*. No physical yarn identity, cm density, or full 10-parameter claim yet.

Evidence retained as GitHub Actions artifacts in both runs. 
