# FabricNET horizontal-only twice: 0 deg horizontal, then rotated 90 deg horizontal

This calls the SAME single-direction V0.6.3 Steerable/Ridge/Density detector twice. The original photo's horizontal evidence is physical WEFT; 90CW rotated horizontal evidence is physical WARP. No GT labels enter inference; the image is only rotated by exact cv2.rotate. Physical x/y mm/px calibration values are swapped in the second pass.

| Metric | Frozen original dual-axis | HORIZONTAL-TWICE |
|---|---:|---:|
| Warp MAE yarns/cm | 7.08095 | 5.5457 |
| Weft MAE yarns/cm | 9.55654 | 7.57843 |
| Both relative errors <=10% | 43/130 | 59/130 |
| Both directions returned density | 130/130 | 130/130 |
| PASS (not same quality gate) | 18/130 | 10/130 |

The angle is fixed at 0deg for BOTH detections; these microscope pictures are broadly aligned. This initial test isolates the identical horizontal detector rather than GT-guided orientation search. Do NOT treat detection on an artificially 90deg-rotated single image as genuine R/T dual capture.

## By image label (not supplied to algorithm)
| Label | Number | Warp MAE | Weft MAE | Both<=10% |
|---|---:|---:|---:|---:|
| plain | 50 | 2.6384 | 4.52544 | 28 |
| twill | 39 | 7.78447 | 5.14986 | 11 |
| satin | 41 | 6.96164 | 13.61169 | 20 |

## Actual detector images
- Overlays_original: every W001-W130 centerline trace drawn on original pixels; red=original warp, cyan=original weft.
- priority10_horizontal_twice.jpg: 10 representative difficult cases.
- original_worst20_horizontal_twice.jpg: 20 worst under the frozen original.
- horizontal_twice_metrics.csv: all raw results including FAIL and LOW_CONFIDENCE.
- horizontal_twice_vs_original.csv: per-image baseline comparison.

Caution: no ground-truth centerline identities; picture-level density agreement cannot prove physically valid centers. Legacy keep-size internal 90deg transform may crop rectangular ROI and should be reviewed if this method fails.
