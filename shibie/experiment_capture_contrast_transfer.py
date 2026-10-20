"""Try the synthetic-motivated optical phase score on an existing REAL R/T pair.

No ground-truth labels, no fake density accuracy. Compare dark-vs-bright
capture modes visually; do not choose a mode using known yarn truth.
"""
from pathlib import Path
import run_capture_condition_sweep as sweep

ROOT=Path(__file__).resolve().parent.parent
sweep.OUT=ROOT/"experiments"/"shibie-phase-transfer-20261020"
sweep.VARIANTS={
    "baseline_real_rt": {},
    "assume_dark_yarns": {
        "transmission_yarn_contrast_mode": "dark",
        "transmission_center_evidence_weight": .45,
    },
    "assume_bright_yarns": {
        "transmission_yarn_contrast_mode": "bright",
        "transmission_center_evidence_weight": .45,
    },
}

if __name__=="__main__":
    sweep.main()
