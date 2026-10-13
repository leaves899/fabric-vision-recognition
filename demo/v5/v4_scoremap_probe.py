"""Read-only LightGBM probability evidence from the SHA-verified frozen V4 execution.

Opt-in sidecar: rerun frozen inference using its existing cached execution
script, capture already-computed s1/s2 after prediction and stop. Frozen
source, weights, feature extraction, V5 outputs and labels remain unchanged.
"""
from __future__ import annotations
import hashlib
import subprocess
import sys
from pathlib import Path
import cv2
import numpy as np
from v4_adapter import ROOT, FROZEN, EXPECTED, check_frozen, run_v4

MARKER="    row_profile=robust_profile_rows(s1,rot_mask)"

def _cache(roi, angle):
    h,w=roi.shape[:2]
    image_hash=hashlib.sha256(roi.tobytes()).hexdigest()
    key=hashlib.sha256(f'{EXPECTED}:{angle}:{h}:{w}:{image_hash}:v2'.encode()).hexdigest()[:28]
    return ROOT/"v4_cache"/key

def read_original_model_scores(roi, rotation_deg, *, timeout=240):
    check_frozen()
    rotation_deg=float(rotation_deg)
    v4=run_v4(roi,rotation_deg)
    directory=_cache(roi,rotation_deg)
    script=directory/"v4_temporary_execution.py"
    if not script.exists():
        raise RuntimeError("Frozen V4 execution cache is missing")
    output=directory/"frozen_v4_model_scores.npz"
    if not output.exists():
        runtime=script.read_text(encoding="utf-8")
        if runtime.count(MARKER)!=1:
            raise RuntimeError("Cannot locate frozen V4 probability instrumentation point")
        save=(f"    np.savez_compressed({str(output)!r}, "
              "s1=s1.astype(np.float16), s2=s2.astype(np.float16), "
              "M=M.astype(np.float32))\n"
              "    raise SystemExit(0)  # read-only probe, without V4 output changes\n"
              +MARKER)
        disposable=runtime.replace(MARKER,save,1)
        compile(disposable,"v4_readonly_score_probe.py","exec")
        probe=directory/"v4_readonly_score_probe.py"
        probe.write_text(disposable,encoding="utf-8")
        with (directory/"score_probe_stdout.txt").open("w",encoding="utf-8") as stdout, \
             (directory/"score_probe_stderr.txt").open("w",encoding="utf-8") as stderr:
            proc=subprocess.run([sys.executable,str(probe)],cwd=str(FROZEN),
                                stdout=stdout,stderr=stderr,timeout=timeout,check=False)
        if proc.returncode!=0 or not output.exists():
            error=(directory/"score_probe_stderr.txt").read_text(encoding="utf-8",errors="replace")[-1600:]
            raise RuntimeError("Frozen score read-only probe failed: "+error)
    with np.load(output) as data:
        first=data["s1"].astype(np.float32)
        second=data["s2"].astype(np.float32)
        M=data["M"].astype(np.float32)
    h,w=roi.shape[:2]
    if first.shape!=(h,w) or second.shape!=(h,w) or M.shape!=(2,3):
        raise RuntimeError("Score-map geometry does not match original ROI")
    if not np.isfinite(first).all() or not np.isfinite(second).all():
        raise RuntimeError("Invalid V4 model probability map")
    inverse=cv2.invertAffineTransform(M)
    validity=cv2.warpAffine(np.ones((h,w),np.uint8),inverse,(w,h),
                           flags=cv2.INTER_NEAREST,borderMode=cv2.BORDER_CONSTANT,
                           borderValue=0).astype(bool)
    def unrotate(score):
        x=cv2.warpAffine(score,inverse,(w,h),flags=cv2.INTER_LINEAR,
                         borderMode=cv2.BORDER_CONSTANT,borderValue=0)
        x[~validity]=0
        return x
    return dict(first=unrotate(first),second=unrotate(second),
                valid_mask=validity, frozen_sha256=check_frozen(),
                frozen_first_count=len(v4["first"]),frozen_second_count=len(v4["second"]),
                model_score_source="FROZEN_V4_LIGHTGBM_PROBA_READ_ONLY",
                operator_labels_used=False)
