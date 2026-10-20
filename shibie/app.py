from __future__ import annotations
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from engine import run_measurement

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
app = FastAPI(title="Fabric Measurement PoC", version="0.6.3")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
EVIDENCE_DIR = BASE_DIR / "tmp" / "web_evidence"
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/evidence", StaticFiles(directory=str(EVIDENCE_DIR)), name="evidence")

@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")

@app.post("/api/measure")
async def measure(
    front_image: UploadFile = File(...),
    transmission_image: UploadFile = File(...),
    mm_per_px: float | None = Form(None),
    mm_per_px_x: float | None = Form(None),
    mm_per_px_y: float | None = Form(None),
    warp_axis_hint: str = Form("vertical"),
):
    try:
        evidence_id = uuid4().hex
        result = run_measurement(
            await front_image.read(),
            await transmission_image.read(),
            mm_per_px=mm_per_px,
            mm_per_px_x=mm_per_px_x,
            mm_per_px_y=mm_per_px_y,
            warp_axis_hint=warp_axis_hint,
            evidence_output_dir=EVIDENCE_DIR / evidence_id,
            sample_id="sample",
        )
        evidence = result.get("evidence")
        if evidence:
            result["evidence_urls"] = {
                key: f"/evidence/{evidence_id}/{Path(path).name}"
                for key, path in evidence.get("files", {}).items()
            }
        return result
    except ValueError as exc:
        return {
            "engine_version": "0.6.3",
            "algorithm_profile": "DENIM_ROUTE_V0.6.3_REAL_ROBUST",
            "status": "FAIL",
            "failure_reasons": [str(exc)],
        }
