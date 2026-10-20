from __future__ import annotations
"""Frozen per-scene 8k batch runner; labels are used only in post-inference scorer."""
import argparse
import json
import time
from pathlib import Path
import run_native8k_smoke
import run_native8k_multiwindow
from synthetic_capture_8k import CaptureScene,generate

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--case",required=True)
    p.add_argument("--weave",required=True,choices=["plain","twill_2_1","twill_3_1","satin_5_2"])
    p.add_argument("--warp",required=True,type=float)
    p.add_argument("--weft",required=True,type=float)
    p.add_argument("--polarity",required=True,choices=["dark","bright","mixed"])
    p.add_argument("--rotation",required=True,type=float)
    p.add_argument("--seed",required=True,type=int)
    a=p.parse_args()
    out=Path("experiments/shibie-8k-capture-multiwindow/stress")/a.case
    scene=CaptureScene(name=a.case,weave=a.weave,warp_density_cm=a.warp,
         weft_density_cm=a.weft,contrast_polarity=a.polarity,rotation_deg=a.rotation,
         diagonal_decoy=14. if "twill" in a.weave else 8.,
         noise_sigma=5. if a.polarity=="mixed" else 3.,seed=a.seed)
    t=time.perf_counter()
    synth=generate(scene,out)
    baseline=run_native8k_smoke.run(out)
    run_native8k_multiwindow.OUT=out
    run_native8k_multiwindow.main()
    m=json.loads((out/"multiwindow_metrics.json").read_text(encoding="utf-8"))
    report={
        "case":a.case,"split":"STRESS_FROZEN", "source_shape":[scene.height,scene.width],
        "weave_label_only_for_scoring":a.weave,"optical_model":a.polarity,
        "density_truth_cm":{"warp":a.warp,"weft":a.weft},
        "input_hash":synth["sha256"],
        "width_p10_px":synth["physical_width_p10_px"],
        "passes_capture_p10_gate":synth["passes_capture_p10_gate"],
        "baseline":{"warp_f1_proxy":baseline["warp"]["f1_proxy"],
                    "weft_f1_proxy":baseline["weft"]["f1_proxy"],
                    "warp_angle_error":baseline["warp"]["angle_error_deg"],
                    "weft_angle_error":baseline["weft"]["angle_error_deg"],
                    "warp_density":baseline["density"]["warp"],
                    "weft_density":baseline["density"]["weft"],
                    "runtime_seconds":baseline["runtime_seconds"],
                    "peak_rss_mib":baseline["peak_rss_mib"]},
        "new":{"frame_status":m["frame"]["status"],
               "warp_f1_proxy":m.get("warp_local_f1_proxy"),
               "weft_f1_proxy":m.get("weft_local_f1_proxy"),
               "warp_passed_windows":m.get("warp_passed_windows"),
               "weft_passed_windows":m.get("weft_passed_windows"),
               "warp_pitch":m.get("warp_pitch_candidate"),
               "weft_pitch":m.get("weft_pitch_candidate"),
               "runtime_seconds":m.get("runtime_seconds"),
               "peak_rss_mib":m.get("peak_rss_mib")},
        "total_wall_seconds":round(time.perf_counter()-t,1),
        "limitations":["PROXY_F1_NOT_CROSS_OCCLUSION_TRACKING",
                       "OLD_GLOBAL_VS_NEW_LOCAL_DIFFERENT_SCORING_REGIONS",
                       "THIS_IS_SYNTHETIC_NOT_REAL_CAMERA"]
    }
    (out/"stress_summary.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("FINAL_STRESS_CASE_REPORT "+json.dumps(report,ensure_ascii=False),flush=True)
if __name__=="__main__":main()
