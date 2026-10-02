"""
au.py — Py-Feat engine wrapper for Pain-Face.

Wraps `feat.Detectorv2` (the single multi-task network: faces, 68 landmarks,
20 AUs, 7 emotions, head pose, gaze, 52 ARKit blendshapes, identity embedding)
behind one `AUEngine.analyze_frame()` call that takes a decoded video frame and
returns plain JSON-able dicts.

Two things worth knowing about the upstream API, both learned the hard way:

  * `detect()` will not accept numpy arrays or PIL images — it wants file paths
    or file-likes, and BytesIO dies inside torch's collate. The supported
    zero-copy route for live frames is `data_type="tensor"` with an **NCHW
    uint8** tensor; a bare CHW tensor is rejected.
  * constructing the detector downloads weights and takes ~80 s the first time,
    so it is built once, lazily, and kept warm for the life of the process.

Throughput on Apple MPS at 480 px is ~17 fps, which is why the server detects
AUs on a subsampled frame stream while rPPG keeps sampling colour at full rate.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

from .pspi import AU_NAMES, DETECTED_AUS, canon

log = logging.getLogger("painface.au")

# Detection resolution. 480 px is the sweet spot measured on MPS: AU values
# agree with 960 px to within ~0.06 while running twice as fast.
DEFAULT_WIDTH = 480
MIN_WIDTH = 256


def pick_device(preferred: str = "auto") -> str:
    """Choose a torch device string, preferring Apple MPS then CUDA then CPU."""
    import torch
    if preferred and preferred != "auto":
        return preferred
    try:
        if torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    try:
        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return "cpu"


@dataclass
class FaceResult:
    """One analysed frame. Every field is JSON-serializable."""
    ok: bool
    t: float
    aus: Dict[str, float] = field(default_factory=dict)
    emotions: Dict[str, float] = field(default_factory=dict)
    pose: Dict[str, float] = field(default_factory=dict)
    gaze: Dict[str, float] = field(default_factory=dict)
    box: Optional[List[float]] = None           # [x, y, w, h] in source pixels
    face_score: float = 0.0
    landmarks: Optional[List[List[float]]] = None   # [[x, y], ...] source pixels
    blendshapes: Dict[str, float] = field(default_factory=dict)
    quality: float = 0.0                        # [0, 1] tracking confidence
    detect_ms: float = 0.0
    reason: str = ""

    def as_dict(self, with_landmarks: bool = True, with_blendshapes: bool = False) -> dict:
        d: Dict[str, Any] = {"ok": self.ok, "t": round(self.t, 4),
                             "detect_ms": round(self.detect_ms, 1)}
        if not self.ok:
            d["reason"] = self.reason
            return d
        d.update({
            "aus": {k: round(v, 4) for k, v in self.aus.items()},
            "emotions": {k: round(v, 4) for k, v in self.emotions.items()},
            "pose": {k: round(v, 2) for k, v in self.pose.items()},
            "gaze": {k: round(v, 3) for k, v in self.gaze.items()},
            "box": [round(v, 1) for v in self.box] if self.box else None,
            "face_score": round(self.face_score, 3),
            "quality": round(self.quality, 3),
        })
        if with_landmarks and self.landmarks is not None:
            d["landmarks"] = [[round(x, 1), round(y, 1)] for x, y in self.landmarks]
        if with_blendshapes and self.blendshapes:
            d["blendshapes"] = {k: round(v, 4) for k, v in self.blendshapes.items()}
        return d


class AUEngine:
    """Thread-safe, lazily-initialized Py-Feat detector.

    One detector instance is shared; `analyze_frame` holds a lock for the
    duration of a forward pass, so callers should run it in a worker thread
    (e.g. `anyio.to_thread.run_sync`) rather than on an event loop.
    """

    def __init__(self, device: str = "auto", width: int = DEFAULT_WIDTH,
                 face_threshold: float = 0.5):
        self.device = pick_device(device)
        self.width = max(int(width), MIN_WIDTH)
        self.face_threshold = float(face_threshold)
        self._detector = None
        self._lock = threading.Lock()
        self._init_error: Optional[str] = None
        self._init_s: Optional[float] = None
        self._frames = 0
        self._total_ms = 0.0

    # -- lifecycle --------------------------------------------------------
    @property
    def ready(self) -> bool:
        return self._detector is not None

    @property
    def init_error(self) -> Optional[str]:
        return self._init_error

    def warm(self) -> bool:
        """Build the detector and run one dummy pass. Safe to call repeatedly."""
        with self._lock:
            if self._detector is not None:
                return True
            if self._init_error is not None:
                return False
            try:
                import feat
                t0 = time.perf_counter()
                det = feat.Detectorv2(device=self.device,
                                      face_detection_threshold=self.face_threshold)
                # One pass on a synthetic frame so the first real frame is fast.
                self._detector = det
                self._init_s = time.perf_counter() - t0
                log.info("Py-Feat Detectorv2 ready on %s in %.1fs", self.device, self._init_s)
            except Exception as e:                       # noqa: BLE001 - surfaced to the client
                self._init_error = f"{type(e).__name__}: {e}"
                log.error("Py-Feat init failed: %s", self._init_error)
                return False
        try:
            self.analyze_frame(np.zeros((240, 320, 3), np.uint8), t=0.0)
        except Exception:
            pass
        return True

    def status(self) -> dict:
        avg = self._total_ms / self._frames if self._frames else None
        return {"ready": self.ready, "device": self.device, "width": self.width,
                "init_error": self._init_error,
                "init_s": round(self._init_s, 1) if self._init_s else None,
                "frames": self._frames,
                "avg_detect_ms": round(avg, 1) if avg else None,
                "aus": list(DETECTED_AUS), "au_names": AU_NAMES}

    # -- detection --------------------------------------------------------
    def _to_tensor(self, rgb: np.ndarray):
        """(H, W, 3) uint8 RGB -> (1, 3, H, W) uint8 tensor, as Py-Feat requires."""
        import torch
        return torch.from_numpy(np.ascontiguousarray(rgb)).permute(2, 0, 1).unsqueeze(0)

    def analyze_frame(self, frame_rgb: np.ndarray, t: float = 0.0) -> FaceResult:
        """Analyse one RGB frame. Returns ok=False when no face is found."""
        if not self.ready and not self.warm():
            return FaceResult(False, t, reason=self._init_error or "detector unavailable")

        import cv2
        h0, w0 = frame_rgb.shape[:2]
        scale = 1.0
        img = frame_rgb
        if w0 > self.width:
            scale = self.width / float(w0)
            img = cv2.resize(frame_rgb, (self.width, max(int(round(h0 * scale)), 2)),
                             interpolation=cv2.INTER_AREA)

        t0 = time.perf_counter()
        try:
            with self._lock:
                fex = self._detector.detect(self._to_tensor(img), data_type="tensor",
                                            progress_bar=False)
        except Exception as e:                            # noqa: BLE001
            return FaceResult(False, t, reason=f"{type(e).__name__}: {e}",
                              detect_ms=1000 * (time.perf_counter() - t0))
        dt = 1000 * (time.perf_counter() - t0)
        self._frames += 1
        self._total_ms += dt

        if fex is None or len(fex) == 0:
            return FaceResult(False, t, reason="no face detected", detect_ms=dt)

        row = self._largest_face(fex)
        # A frame with no face still comes back as one row, with FaceScore 0 and
        # every AU NaN, so emptiness has to be tested rather than assumed.
        result = self._to_result(fex, row, 1.0 / scale if scale else 1.0, t, dt)
        if not result.aus or result.face_score <= 0.0 or result.box is None:
            return FaceResult(False, t, reason="no face detected", detect_ms=dt)
        return result

    @staticmethod
    def _largest_face(fex) -> int:
        """Index of the biggest detected face — the subject, not a bystander."""
        if len(fex) == 1:
            return 0
        try:
            area = (fex["FaceRectWidth"].to_numpy(dtype=float)
                    * fex["FaceRectHeight"].to_numpy(dtype=float))
            return int(np.nanargmax(area))
        except Exception:
            return 0

    def _to_result(self, fex, row: int, inv: float, t: float, dt: float) -> FaceResult:
        def grab(columns) -> Dict[str, float]:
            out: Dict[str, float] = {}
            for c in columns:
                try:
                    v = float(fex[c].iloc[row])
                except Exception:
                    continue
                if v == v:                                # skip NaN
                    out[str(c)] = v
            return out

        aus = {canon(k): v for k, v in grab(fex.au_columns).items()}
        emotions = grab(fex.emotion_columns)
        pose = grab(fex.facepose_columns)
        gaze = grab(getattr(fex, "gaze_columns", []))
        blend = grab(getattr(fex, "blendshape_columns", []))

        box, score = None, 0.0
        try:
            box = [float(fex["FaceRectX"].iloc[row]) * inv,
                   float(fex["FaceRectY"].iloc[row]) * inv,
                   float(fex["FaceRectWidth"].iloc[row]) * inv,
                   float(fex["FaceRectHeight"].iloc[row]) * inv]
            score = float(fex["FaceScore"].iloc[row])
        except Exception:
            pass

        landmarks = None
        try:
            cols = list(fex.landmark_columns)
            n = len(cols) // 2
            xs = [float(fex[f"x_{i}"].iloc[row]) * inv for i in range(n)]
            ys = [float(fex[f"y_{i}"].iloc[row]) * inv for i in range(n)]
            landmarks = [[x, y] for x, y in zip(xs, ys)]
        except Exception:
            pass

        return FaceResult(ok=True, t=t, aus=aus, emotions=emotions, pose=pose, gaze=gaze,
                          box=box, face_score=score, landmarks=landmarks,
                          blendshapes=blend, quality=self._quality(score, pose),
                          detect_ms=dt)

    @staticmethod
    def _quality(face_score: float, pose: Dict[str, float]) -> float:
        """Tracking confidence in [0, 1]: detector score penalised by head turn.

        AU estimates degrade as the face turns away from the camera, so yaw and
        pitch beyond ~20 deg progressively discount the reading.
        """
        q = min(max(face_score, 0.0), 1.0)
        yaw, pitch = abs(pose.get("Yaw", 0.0)), abs(pose.get("Pitch", 0.0))
        for ang in (yaw, pitch):
            if ang > 20.0:
                q *= max(0.0, 1.0 - (ang - 20.0) / 45.0)
        return min(max(q, 0.0), 1.0)

    # -- offline ----------------------------------------------------------
    def analyze_video(self, path: str, every: int = 5,
                      max_seconds: Optional[float] = None,
                      progress=None) -> List[FaceResult]:
        """Analyse every `every`-th frame of a video file."""
        import cv2
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            raise IOError(f"Cannot open video: {path}")
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        if not (1 < fps <= 240):
            fps = 30.0
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        out: List[FaceResult] = []
        i = 0
        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                t = i / fps
                if max_seconds is not None and t > max_seconds:
                    break
                if i % max(every, 1) == 0:
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    out.append(self.analyze_frame(rgb, t=t))
                    if progress and total:
                        progress(min(i / total, 1.0))
                i += 1
        finally:
            cap.release()
        return out
