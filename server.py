"""
server.py — Python engine for the rPPG Lab web app.

Run:   python server.py            (then open http://localhost:8000)
Docs:  http://localhost:8000/docs  (interactive API explorer)

The browser does real-time extraction (camera → face mesh → ROI RGB traces)
and streams the traces here every ~2 s. This server runs the full classical
method bank (incl. ICA and OMIT, which the browser does not), Tarvainen
detrending, Welch spectra and frequency-domain HRV. It can also analyse an
uploaded or browser-recorded video, optionally with a pretrained deep model
from the `open-rppg` package (pip install open-rppg).
"""
from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from typing import List, Optional

import numpy as np
import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import rppg_core as core

ROOT = Path(__file__).parent
STATIC = ROOT / "static"

DEEP_MODELS = [
    "FacePhys.rlap", "PhysMamba.rlap", "RhythmMamba.rlap", "PhysFormer.rlap",
    "TSCAN.rlap", "EfficientPhys.rlap", "PhysNet.rlap", "ME-chunk.rlap", "ME-flow.rlap",
]
_deep_cache: dict = {}


def deep_available() -> bool:
    try:
        import rppg  # noqa: F401  (open-rppg)
        return True
    except Exception:
        return False


app = FastAPI(title="rPPG Lab engine", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class TraceIn(BaseModel):
    t: List[float] = Field(..., description="Frame timestamps in seconds")
    rgb: List[List[float]] = Field(..., description="Per-frame mean skin [R, G, B]")
    fs: float = 30.0
    primary: str = "POS"
    methods: Optional[List[str]] = None


@app.get("/api/health")
def health():
    return {"ok": True, "methods": list(core.METHODS), "deep_available": deep_available(),
            "deep_models": DEEP_MODELS}


@app.post("/api/analyze")
def analyze(body: TraceIn):
    if len(body.t) != len(body.rgb) or len(body.t) < body.fs * 4:
        raise HTTPException(400, "Need at least 4 s of samples with matching t/rgb lengths.")
    t0 = time.perf_counter()
    _, rgb = core.resample_uniform(np.array(body.t), np.array(body.rgb), body.fs)
    res = core.analyze(rgb, body.fs, methods=body.methods, primary=body.primary)
    res["compute_ms"] = round(1000 * (time.perf_counter() - t0), 1)
    return res


@app.post("/api/video")
async def analyze_video(file: UploadFile = File(...), primary: str = Form("POS"),
                        deep_model: str = Form("")):
    import rppg_video
    suffix = Path(file.filename or "clip.webm").suffix or ".webm"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await file.read())
        path = tmp.name
    try:
        t0 = time.perf_counter()
        out = {}
        try:
            t, rgb, fps = rppg_video.extract_rgb(path)
            fs = 30.0
            _, rgbu = core.resample_uniform(t, rgb.T, fs)
            out["classical"] = core.analyze(rgbu, fs, primary=primary)
            out["video_fps"] = fps
        except Exception as e:
            out["classical_error"] = str(e)
        if deep_model:
            out["deep"] = run_deep(path, deep_model)
        out["compute_ms"] = round(1000 * (time.perf_counter() - t0), 1)
        return core._clean(out)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def run_deep(path: str, name: str) -> dict:
    if not deep_available():
        return {"error": "Deep models need the open-rppg package: pip install open-rppg"}
    import rppg
    try:
        model = _deep_cache.get(name) or rppg.Model(name)
        _deep_cache[name] = model
        res = model.process_video(path)
        return {"model": name, **{k: v for k, v in res.items()}}
    except Exception as e:
        return {"model": name, "error": f"{type(e).__name__}: {e}"}


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"\n  rPPG Lab running →  http://localhost:{port}\n  API docs         →  http://localhost:{port}/docs\n")
    uvicorn.run(app, host="127.0.0.1", port=port)
