"""
server.py — Pain-Face backend: live multimodal pain scoring over a WebSocket.

Run:   python -m painface.server          (then open http://localhost:8000)
Docs:  http://localhost:8000/docs

Pipeline per connection
-----------------------
The browser does two things at once and the server keeps them in step:

  1. every video frame, it measures mean skin RGB from the face mesh and
     streams the triples here as JSON (`{"type": "rgb"}`). Those feed the
     rPPG method bank, which needs a steady ~30 Hz to resolve inter-beat
     intervals.
  2. every ~150 ms it sends a JPEG of the frame as a binary message. Those go
     to Py-Feat for action units at whatever rate the hardware sustains
     (~17 fps at 480 px on Apple MPS).

Each AU result is fused with the newest vitals into one pain index and pushed
back. Frames that arrive while a detection is already running are dropped
rather than queued — stale AUs are worse than fewer AUs, and dropping gives
natural backpressure on slower machines.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import anyio
import numpy as np
import uvicorn
from fastapi import (FastAPI, File, Form, HTTPException, UploadFile, WebSocket,
                     WebSocketDisconnect)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles

from . import __version__, fusion
from .au import AUEngine
from .pspi import AU_NAMES, DETECTED_AUS, PAIN_AUS, PSPI_MAX, PSPI_TERMS
from .session import PainSession
from .vitals import VitalsBuffer

log = logging.getLogger("painface.server")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"

AU_DEVICE = os.environ.get("PAINFACE_DEVICE", "auto")
AU_WIDTH = int(os.environ.get("PAINFACE_WIDTH", "480"))

engine = AUEngine(device=AU_DEVICE, width=AU_WIDTH)

# The most recent live session, so the browser's export buttons can fetch the
# engine's own full-rate record over plain HTTP. This is a single-subject
# localhost instrument; it deliberately keeps one session rather than a store.
_last_session: Optional["PainSession"] = None
app = FastAPI(title="Pain-Face", version=__version__,
              description="Multimodal pain intensity from facial action units and rPPG.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
async def _warm() -> None:
    """Build the detector off the event loop so the page can load meanwhile."""
    async def go() -> None:
        t0 = time.perf_counter()
        ok = await anyio.to_thread.run_sync(engine.warm)
        log.info("detector warm=%s in %.1fs (%s)", ok, time.perf_counter() - t0, engine.device)
    asyncio.create_task(go())


# ----------------------------------------------------------------- REST
@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "app": "Pain-Face", "version": __version__,
            "au": engine.status(),
            "pspi": {"max": PSPI_MAX,
                     "terms": [{"label": l, "aus": list(c), "points": p} for l, c, p in PSPI_TERMS]},
            "pain_aus": list(PAIN_AUS), "detected_aus": list(DETECTED_AUS),
            "au_names": AU_NAMES,
            "fusion": {"w_facial": fusion.W_FACIAL, "w_autonomic": fusion.W_AUTONOMIC,
                       "trigger_on": fusion.TRIGGER_ON, "trigger_off": fusion.TRIGGER_OFF,
                       "dwell_s": fusion.TRIGGER_DWELL_S, "release_s": fusion.TRIGGER_RELEASE_S}}


@app.post("/api/video")
async def analyze_video(file: UploadFile = File(...), au_every: int = Form(5),
                        primary: str = Form("POS"),
                        max_seconds: Optional[float] = Form(None)) -> dict:
    """Offline pass over an uploaded clip: AU timeline, vitals and pain."""
    suffix = Path(file.filename or "clip.webm").suffix or ".webm"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await file.read())
        path = tmp.name
    try:
        return await anyio.to_thread.run_sync(
            lambda: analyze_video_file(path, au_every=au_every, primary=primary,
                                       max_seconds=max_seconds))
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def analyze_video_file(path: str, au_every: int = 5, primary: str = "POS",
                       max_seconds: Optional[float] = None) -> dict:
    """JSON-able offline result. See `analyze_video_session` for the session."""
    session, out = analyze_video_session(path, au_every, primary, max_seconds)
    return out


def analyze_video_session(path: str, au_every: int = 5, primary: str = "POS",
                          max_seconds: Optional[float] = None,
                          progress=None) -> tuple["PainSession", dict]:
    """Offline pass, returning the recorded session alongside the summary dict,
    so the CLI can plot and export it rather than only print it."""
    import rppg_core as core
    import rppg_video

    out: Dict[str, Any] = {"source": os.path.basename(path)}
    baseline = fusion.Baseline(min_n=8)
    trigger = fusion.Trigger()
    session = PainSession(label=os.path.basename(path))

    # rPPG first, so the pain timeline can be scored against real vitals.
    vitals_at = None
    try:
        t, rgb, fps = rppg_video.extract_rgb(path, max_seconds=max_seconds)
        tu, rgbu = core.resample_uniform(t, rgb, 30.0)
        out["vitals"] = core._clean(core.analyze(rgbu, 30.0, primary=primary, with_series=True))
        out["video_fps"] = fps
        vitals_at = _vitals_sampler(tu, rgbu, primary)
    except Exception as e:                                # noqa: BLE001
        out["vitals_error"] = f"{type(e).__name__}: {e}"

    faces = engine.analyze_video(path, every=au_every, max_seconds=max_seconds,
                                 progress=progress)
    out["frames_analyzed"] = len(faces)
    out["frames_with_face"] = sum(1 for f in faces if f.ok)

    for f in faces:
        if not f.ok:
            continue
        v = vitals_at(f.t) if vitals_at else {}
        baseline.add(v)
        reading = fusion.fuse(f.aus, v, baseline, f.emotions, face_quality=f.quality)
        on = trigger.update(reading.intensity, f.t)
        session.add(f.t, reading.as_dict(trigger, f.t), f.aus, f.emotions, v, f.quality, on)

    out["summary"] = session.summary()
    out["timeline"] = session.timeline(("t", "nrs", "pspi", "corrected", "smile",
                                        "autonomic", "confidence", "triggered"))
    out["au_status"] = engine.status()
    _publish(session)
    return session, out


def _vitals_sampler(t: np.ndarray, rgb: np.ndarray, primary: str):
    """Build a callable giving vitals over a trailing window ending at time t.

    Offline we can afford a real sliding analysis rather than one global value,
    so pain scoring sees the vitals that were actually current at each frame.
    """
    import rppg_core as core
    cache: Dict[int, Dict[str, Optional[float]]] = {}
    fs, win = 30.0, 20.0

    def at(ti: float) -> Dict[str, Optional[float]]:
        bucket = int(ti // 2)                     # recompute at most every 2 s
        if bucket in cache:
            return cache[bucket]
        hi = float(ti)
        lo = max(hi - win, float(t[0]))
        m = (t >= lo) & (t <= hi)
        feats: Dict[str, Optional[float]] = {}
        if m.sum() > fs * 6:
            try:
                r = core.analyze(rgb[:, m], fs, primary=primary, with_series=False)
                hrv, resp = r.get("hrv") or {}, r.get("respiration") or {}
                long_enough = (hi - lo) >= 29.5
                feats = {"hr": r.get("fused_hr"),
                         "rmssd": hrv.get("rmssd_ms") if long_enough else None,
                         "sdnn": hrv.get("sdnn_ms") if long_enough else None,
                         "lf_hf": hrv.get("lf_hf") if long_enough else None,
                         "resp": resp.get("fused"),
                         "perfusion": r.get("perfusion_index_pct"),
                         "spo2_ratio": r.get("spo2_ratio_uncalibrated")}
            except Exception:
                feats = {}
        cache[bucket] = feats
        return feats

    return at


# ----------------------------------------------------------------- live
class LiveState:
    """Everything one WebSocket connection owns."""

    def __init__(self) -> None:
        self.vitals = VitalsBuffer(window_s=20.0)
        self.baseline = fusion.Baseline(min_n=15)
        self.trigger = fusion.Trigger()
        self.session = _publish(PainSession())
        self.recording = False
        self.calibrating = False
        self.t0 = time.perf_counter()
        self.busy = False
        self.frames_in = 0
        self.frames_dropped = 0
        self.last_face: Optional[dict] = None
        self.send_landmarks = True
        self.send_blendshapes = False

    @property
    def t(self) -> float:
        return time.perf_counter() - self.t0


@app.websocket("/ws/live")
async def ws_live(ws: WebSocket) -> None:
    await ws.accept()
    st = LiveState()
    await ws.send_text(json.dumps({"type": "hello", "version": __version__,
                                   "au": engine.status(),
                                   "pain_aus": list(PAIN_AUS),
                                   "au_names": AU_NAMES,
                                   "pspi_max": PSPI_MAX}))
    try:
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                break
            if (data := msg.get("bytes")) is not None:
                await _on_frame(ws, st, data)
            elif (text := msg.get("text")) is not None:
                await _on_text(ws, st, text)
    except WebSocketDisconnect:
        pass
    except Exception as e:                                # noqa: BLE001
        log.warning("live session ended: %s: %s", type(e).__name__, e)
    finally:
        log.info("live closed — frames %d (dropped %d), samples %d",
                 st.frames_in, st.frames_dropped, len(st.session.samples))


async def _on_text(ws: WebSocket, st: LiveState, text: str) -> None:
    try:
        m = json.loads(text)
    except json.JSONDecodeError:
        return
    kind = m.get("type")

    if kind == "rgb":
        n = st.vitals.extend(m.get("t") or [], m.get("rgb") or [])
        st.vitals.analyze()          # no-op until the buffer is long enough
        snap = st.vitals.snapshot()
        if st.calibrating and snap["ready"]:
            st.baseline.add(st.vitals.features())
        # Always acknowledge, even before the buffer can support a spectrum, so
        # a client can treat the protocol as strictly request/response.
        await _send(ws, {"type": "vitals", "t": round(st.t, 2), "added": n,
                         "vitals": snap, "baseline": st.baseline.as_dict()})

    elif kind == "config":
        if (w := m.get("window_s")) is not None:
            st.vitals.window_s = max(5.0, min(float(w), 60.0))
        if (p := m.get("primary")) is not None:
            st.vitals.primary = str(p)
        if (fs := m.get("fs")) is not None:
            st.vitals.fs = max(10.0, min(float(fs), 120.0))
        if (iv := m.get("analysis_interval_s")) is not None:
            st.vitals.min_interval_s = max(0.0, min(float(iv), 10.0))
        for key, attr in (("landmarks", "send_landmarks"), ("blendshapes", "send_blendshapes")):
            if key in m:
                setattr(st, attr, bool(m[key]))
        if (thr := m.get("trigger_on")) is not None:
            st.trigger.on_threshold = max(0.05, min(float(thr), 0.95))
            st.trigger.off_threshold = min(st.trigger.off_threshold, st.trigger.on_threshold * 0.8)
        await _send(ws, {"type": "config", "window_s": st.vitals.window_s,
                         "primary": st.vitals.primary, "fs": st.vitals.fs,
                         "analysis_interval_s": st.vitals.min_interval_s,
                         "trigger_on": st.trigger.on_threshold})

    elif kind == "baseline":
        action = m.get("action")
        if action == "start":
            st.calibrating = True
        elif action == "stop":
            st.calibrating = False
        elif action == "reset":
            st.baseline = fusion.Baseline(min_n=15)
            st.calibrating = False
        await _send(ws, {"type": "baseline", "calibrating": st.calibrating,
                         "baseline": st.baseline.as_dict()})

    elif kind == "session":
        action = m.get("action")
        if action == "start":
            st.session = _publish(PainSession(label=str(m.get("label") or "")))
            st.recording = True
        elif action == "stop":
            st.recording = False
        elif action == "reset":
            st.session = _publish(PainSession())
            st.recording = False
        await _send(ws, {"type": "session", "recording": st.recording,
                         "summary": st.session.summary()})

    elif kind == "aus":
        # Externally supplied action units — the browser's simulator, or a
        # replay of coded data — scored through exactly the same fusion,
        # trigger and recording path as a live detection, so the simulator
        # exercises the real pipeline rather than a parallel copy of it.
        aus = {str(k): float(v) for k, v in (m.get("aus") or {}).items()
               if isinstance(v, (int, float))}
        if aus:
            t = float(m.get("t") or st.t)
            emotions = {str(k): float(v) for k, v in (m.get("emotions") or {}).items()
                        if isinstance(v, (int, float))}
            quality = float(m.get("quality") or 1.0)
            feats = st.vitals.features()
            if st.calibrating:
                st.baseline.add(feats)
            reading = fusion.fuse(aus, feats, st.baseline, emotions, face_quality=quality)
            on = st.trigger.update(reading.intensity, t)
            pain = reading.as_dict(st.trigger, t)
            pain["triggered"] = on
            payload = {"type": "au", "t": round(t, 3), "simulated": True,
                       "face": {"ok": True, "t": round(t, 3), "aus": aus,
                                "emotions": emotions, "quality": quality,
                                "box": None, "pose": {}, "gaze": {}, "detect_ms": 0.0},
                       "pain": pain}
            if st.recording:
                st.session.add(t, pain, aus, emotions, feats, quality, on)
                payload["recorded"] = len(st.session.samples)
            await _send(ws, payload)

    elif kind == "ping":
        await _send(ws, {"type": "pong", "t": round(st.t, 3)})


def _publish(session: "PainSession") -> "PainSession":
    """Make `session` the one the REST export endpoints serve."""
    global _last_session
    _last_session = session
    return session


async def _on_frame(ws: WebSocket, st: LiveState, data: bytes) -> None:
    """Run Py-Feat on one JPEG frame, fuse with vitals, push the result."""
    st.frames_in += 1
    if st.busy:
        # A detection is already in flight. Newer frames matter more than a
        # backlog, so drop this one and let the client keep its cadence.
        st.frames_dropped += 1
        return
    st.busy = True
    try:
        t = st.t
        face = await anyio.to_thread.run_sync(lambda: _detect(data, t))
        if face is None:
            await _send(ws, {"type": "au", "ok": False, "t": round(t, 3),
                             "reason": "frame decode failed"})
            return

        payload: Dict[str, Any] = {"type": "au", "t": round(t, 3),
                                   "face": face.as_dict(st.send_landmarks, st.send_blendshapes),
                                   "frames": st.frames_in, "dropped": st.frames_dropped}
        if face.ok:
            feats = st.vitals.features()
            if st.calibrating:
                st.baseline.add(feats)
            reading = fusion.fuse(face.aus, feats, st.baseline, face.emotions,
                                  face_quality=face.quality)
            on = st.trigger.update(reading.intensity, t)
            pain = reading.as_dict(st.trigger, t)
            pain["triggered"] = on
            payload["pain"] = pain
            if st.recording:
                st.session.add(t, pain, face.aus, face.emotions, feats, face.quality, on)
                payload["recorded"] = len(st.session.samples)
            st.last_face = payload["face"]
        await _send(ws, payload)
    finally:
        st.busy = False


def _detect(jpeg: bytes, t: float):
    """Decode a JPEG and run the detector. Returns None if the bytes are junk."""
    import cv2
    buf = np.frombuffer(jpeg, np.uint8)
    bgr = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if bgr is None:
        return None
    return engine.analyze_frame(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB), t=t)


async def _send(ws: WebSocket, payload: dict) -> None:
    try:
        await ws.send_text(json.dumps(payload, allow_nan=False, default=lambda _: None))
    except (WebSocketDisconnect, RuntimeError):
        raise
    except (TypeError, ValueError) as e:
        log.debug("dropped unserializable payload: %s", e)


# ----------------------------------------------------------------- static
@app.get("/")
def index() -> FileResponse:
    page = STATIC / "painface.html"
    if not page.exists():
        raise HTTPException(404, "static/painface.html is missing")
    return FileResponse(page)


@app.get("/api/session")
def session_summary() -> dict:
    if _last_session is None:
        raise HTTPException(404, "No session recorded yet.")
    return _last_session.summary()


@app.get("/api/session.json")
def session_json() -> Response:
    if _last_session is None:
        raise HTTPException(404, "No session recorded yet.")
    return Response(_last_session.to_json(), media_type="application/json",
                    headers={"Content-Disposition": 'attachment; filename="painface-session.json"'})


@app.get("/api/session.csv")
def session_csv() -> Response:
    if _last_session is None:
        raise HTTPException(404, "No session recorded yet.")
    return Response(_last_session.to_csv(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="painface-session.csv"'})


@app.get("/api/aus", response_class=PlainTextResponse)
def au_reference() -> str:
    """Plain-text AU reference, handy from the terminal."""
    lines = [f"{c}  {AU_NAMES.get(c, '')}{'   [pain]' if c in PAIN_AUS else ''}"
             for c in DETECTED_AUS]
    return "\n".join(lines)


if STATIC.is_dir():
    app.mount("/static", StaticFiles(directory=STATIC), name="static")


def main() -> None:
    port = int(os.environ.get("PORT", 8000))
    print(f"\n  Pain-Face  →  http://localhost:{port}"
          f"\n  API docs   →  http://localhost:{port}/docs"
          f"\n  detector   →  Py-Feat Detectorv2 on {engine.device} @ {engine.width}px\n")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
