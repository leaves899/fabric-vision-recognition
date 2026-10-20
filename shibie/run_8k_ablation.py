from __future__ import annotations
"""Frozen A/B/C/D on identical native-resolution R/T bytes.

A/B/C share the original ROI, full-frame curve scoring and independently
post-loaded truth. D is a local-window-only prototype and its local F1 proxy
is explicitly NOT directly comparable to the A/B/C global F1.
"""
import dataclasses
import json
import os
from pathlib import Path
import cv2
import numpy as np
from engine import pipeline
from engine.config import EngineConfig
from run_native8k_smoke import run as run_frozen
ROOT=Path("experiments/shibie-8k-capture-multiwindow/smoke")
CONFIGS={
 "A_v063":{},
 "B_acf_candidate":{
   "density_min_per_cm":10.,
   "steerable_quality_close_margin":.22,
   "steerable_periodicity_tiebreak_floor":.08
 },
 "C_guard_dark":{
   "transmission_yarn_contrast_mode":"dark",
   "transmission_center_evidence_weight":.45,
   "transmission_phase_pitch_guard_ratio":.15
 },
}
def main():
    truth=json.loads((ROOT/"truth.json").read_text(encoding="utf-8"))
    rows=[]
    for name,settings in CONFIGS.items():
        if name=="A_v063":
            rec=json.loads((ROOT/"baseline_metrics.json").read_text(encoding="utf-8"))
            directory=ROOT
        else:
            directory=ROOT/"variants"/name
            directory.mkdir(parents=True,exist_ok=True)
            for f in ("truth.json","reflection_8000x6000.jpg","transmission_8000x6000.jpg"):
                dest=directory/f
                if not dest.exists():os.link(ROOT/f,dest)
            pipeline.DEFAULT_CONFIG=dataclasses.replace(EngineConfig(),**settings)
            try:rec=run_frozen(directory)
            finally:pipeline.DEFAULT_CONFIG=EngineConfig()
        rows.append({"variant":name,"physical_source_sha256":truth["sha256"],
          "warp_f1_global_proxy":rec["warp"]["f1_proxy"],
          "weft_f1_global_proxy":rec["weft"]["f1_proxy"],
          "warp_half_pitch_fraction":rec["warp"].get("half_pitch_candidate_fraction"),
          "weft_half_pitch_fraction":rec["weft"].get("half_pitch_candidate_fraction"),
          "warp_angle_error_deg":rec["warp"]["angle_error_deg"],
          "weft_angle_error_deg":rec["weft"]["angle_error_deg"],
          "warp_density":rec["density"]["warp"],"weft_density":rec["density"]["weft"],
          "runtime_seconds":rec["runtime_seconds"],"peak_rss_mib":rec["peak_rss_mib"]})
    new=json.loads((ROOT/"multiwindow_metrics.json").read_text(encoding="utf-8"))
    rows.append({"variant":"D_native8k_multiwindow",
      "physical_source_sha256":truth["sha256"],
      "warp_f1_local_proxy":new.get("warp_local_f1_proxy"),
      "weft_f1_local_proxy":new.get("weft_local_f1_proxy"),
      "warp_pitch_px":(new.get("warp_pitch_candidate") or {}).get("pitch_px"),
      "weft_pitch_px":(new.get("weft_pitch_candidate") or {}).get("pitch_px"),
      "runtime_seconds":new.get("runtime_seconds"),
      "peak_rss_mib":new.get("peak_rss_mib"),
      "scoring_warning":"local-only, not comparable to original global ROI F1"})
    out=ROOT/"ablation_4way.json"
    out.write_text(json.dumps({"scoring_warning":"A/B/C GLOBAL vs D LOCAL F1 not commensurate",
       "shared_source":truth["sha256"],"variants":rows},ensure_ascii=False,indent=2),encoding="utf-8")
    paths=[
      ROOT/"baseline_overlay_crop.jpg",
      ROOT/"variants"/"B_acf_candidate"/"baseline_overlay_crop.jpg",
      ROOT/"variants"/"C_guard_dark"/"baseline_overlay_crop.jpg",
      ROOT/"physical_truth_overlay_crop.jpg"
    ]
    cells=[]
    for p in paths:
        img=cv2.imread(str(p))
        assert img is not None,str(p)
        cells.append(cv2.resize(img,(400,400),interpolation=cv2.INTER_AREA))
    sheet=np.vstack([np.hstack(cells[:2]),np.hstack(cells[2:])])
    cv2.imwrite(str(ROOT/"ablation_visual_compare.jpg"),sheet,
                [cv2.IMWRITE_JPEG_QUALITY,82])
    print("ABCD_ABLATION "+json.dumps(rows,ensure_ascii=False),flush=True)
if __name__=="__main__":main()
