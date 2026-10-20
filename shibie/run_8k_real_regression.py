from __future__ import annotations
"""Independent genuine-photograph audit; no synthetic truth as prior.

The new 8k branch remains opt-in. Existing true R/T is NOT 8k calibrated,
and duplicated single photos are diagnostics, never genuine paired capture.
"""
import json
from pathlib import Path
import cv2
import run_acf_holdout
import evaluate_labeled_yarn_pitch as manual
import run_capture_condition_sweep as paired

ROOT=Path("experiments/shibie-8k-capture-multiwindow/real-regression")
def main():
    ROOT.mkdir(parents=True,exist_ok=True)
    run_acf_holdout.OUT=ROOT/"phone_and_fabricnet"
    run_acf_holdout.main()
    manual.RESULTS=run_acf_holdout.OUT
    manual.main()
    paired.OUT=ROOT/"uncalibrated_genuine_rt_pair"
    paired.VARIANTS={"v063_untouched":{}}
    paired.main()
    rows=json.loads((run_acf_holdout.OUT/"comparison.json").read_text(encoding="utf-8"))
    audits=json.loads((run_acf_holdout.OUT/"manual_pitch_audit.json").read_text(encoding="utf-8"))
    full=paired.OUT/"measurements.json"
    pair=json.loads(full.read_text(encoding="utf-8"))
    # A reference truth is read only by post-inference scoring scripts above.
    real_summary={
      "new_algorithm_registered_as_default":False,
      "reason":"DO_NOT_DEPLOY_BEFORE_REAL_8K_CALIBRATED_GT",
      "phone_samples":len({r["name"] for r in rows if r["name"].startswith("U")}),
      "real_photo_modes":"SINGLE_IMAGE_DUPLICATION_FOR_LEGACY_DIAGNOSTIC_ONLY",
      "pair_input":"GENUINE_REFLECTION_TRANSMISSION_UNCALIBRATED_NOT_8K",
      "pair_engine_status":pair[0]["status"],
      "pair_measured_line_count":[pair[0]["warp_line_count"],pair[0]["weft_line_count"]],
      "new_native8k_candidate_real_photo_accuracy":None,
      "real_phone_physical_reference_audit":audits,
      "new_module_regression_status":"NOT_ELIGIBLE_FOR_8K_CAPTURE_VALIDATION",
      "known_limits":["NO_CERTIFIED_50MM_FRAME","NO_8000x6000_GENUINE_PAIRED_REAL_GT",
           "NO_TRUE_FULL_CURVE_IDENTITY_GT","NO_REAL_IMPROVEMENT_CLAIM"],
    }
    (ROOT/"real_regression_summary.json").write_text(
      json.dumps(real_summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print("REAL_REGRESSION_SUMMARY "+json.dumps({
      k:v for k,v in real_summary.items() if k!="real_phone_physical_reference_audit"
    },ensure_ascii=False),flush=True)
if __name__=="__main__":main()
