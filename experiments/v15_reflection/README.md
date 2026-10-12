# Fabric Measurement Engine V1.5 — Reflectance-only Experiment

**Independent branch:** experiment/v15-reflectance-engine. No edits or imports to `demo/v5` or frozen V4.

This is a repeatable **algorithmic candidate**, not a measurement instrument and not a demonstrated true-yarn detector. The original V1.5 proposal uses front reflection + transmission and Camera Profile; this variant intentionally supports ordinary phone front/back reflection and a physically coplanar **50 mm × 50 mm inner frame**. No transmission is presumed.

## Trial run

```bash
python -m pip install numpy Pillow
python -m unittest discover -s experiments/v15_reflection/tests -v
python -m experiments.v15_reflection.engine \
  --image demo/v5/samples/有标定框_示例.jpg \
  --reference "x1,y1,x2,y2" --confirm-reference \
  --corners '[[tlx,tly],[trx,try],[brx,bry],[blx,bly]]' \
  --confirm-corners --warp-family A \
  --out experiments/v15_reflection/output/example.json
```

Replace **all placeholders with observed, human-confirmed actual image coordinates**. Do not infer operator clicks from the filename. When you have no confirmed 50 mm frame, omit corners and `--confirm-corners`; density remains null. When you have no real-yarn reference, omit the reference; FFT yields only unvalidated angle candidates and may abstain.

## Independent pipeline

1. Gate 2 image contrast, exposure and focus-gradient screening (heuristic; thresholds not certified).
2. Optional verified inner-square quadrilateral rectification at native-equivalent scale with a 1792 px memory cap; original image and source-coordinate manual reference retained.
3. Manual confirmed reference axis, or an **unverified** local 2D FFT auto proposal. B is a 90° geometry hypothesis, not a confirmed physical family.
4. Rotate to reference axis; in five long-direction strips, compare 1D projection FFT peaks and autocorrelation lags, reject strip disagreement and suspected octave harmonic ambiguity.
5. Independently compare median pitch vs counted projection peaks / scanned physical length. If no 50 mm frame, no physical result.
6. Return all 10 keys, Gate 2 / Gate 3 reasons, provenance, and candidate-only status. Width and weave remain UNAVAILABLE; A/B requires separately confirmed warp family.

## Limitations

- Projection peaks are **not** identified physical yarn centerlines, especially on denim with twill, hairy fibers, phase offsets, camouflage stripes or uneven lighting.
- Even when `gate3=PASS`, output is **CANDIDATE** only; it must pass blinded, fabric-separated real ground truth before release.
- The original V1.5 target `mm_per_px <= 0.015` is reported as a separate advisory, **not** assumed true for phone capture. Downsampling never increases true spatial resolution.
- Centerline evidence can be visualized from projected peak positions, but is not proof that one line equals one real yarn.
- Front/back are not automatically registered; run each image independently. No RK3576 timing or certified ten-parameter accuracy is claimed.
- For real benchmarking use existing `benchmark.dataset` split and real `CONFIRMED` GT only.

See `docs/benchmarks/V15_REFLECTION_GOALS.md` for stop conditions.
