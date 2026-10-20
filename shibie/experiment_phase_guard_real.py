"""Real R/T optical phase family guard vs prior unguarded modes.

All variants compare identical verified existing image files; no labels are used.
Counts and spacing are diagnostic only without physical 5cm calibration.
"""
from pathlib import Path
import run_capture_condition_sweep as sweep

ROOT=Path(__file__).resolve().parent.parent
sweep.OUT=ROOT/"experiments"/"shibie-phase-guard-real-20261020"
sweep.VARIANTS={
 "v063_baseline": {},
 "unguarded_bright": {
     "transmission_yarn_contrast_mode": "bright",
     "transmission_center_evidence_weight": .45,
 },
 "guarded_bright": {
     "transmission_yarn_contrast_mode": "bright",
     "transmission_center_evidence_weight": .45,
     "transmission_phase_pitch_guard_ratio": .15,
 },
 "guarded_dark": {
     "transmission_yarn_contrast_mode": "dark",
     "transmission_center_evidence_weight": .45,
     "transmission_phase_pitch_guard_ratio": .15,
 },
}
if __name__=="__main__":
    sweep.main()
