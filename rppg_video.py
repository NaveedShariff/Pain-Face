"""
rppg_video.py — extract spatially-averaged skin RGB traces from a video file.

Face: the Py-Feat detector that Pain-Face already loads for action units,
borrowed through `painface.au.shared_engine()` and re-detected every few frames
with the box smoothed between detections. OpenCV 5 removed the Haar cascade API
this module used to call, and reusing the engine keeps one face finder in the
process rather than adding a second model and a second warm-up. ROIs: forehead
+ both cheeks, each filtered by a YCrCb skin mask so hair, eyebrows and
background pixels are excluded.

A caller with its own face finder can pass `face_detector=` to `extract_rgb`:
any callable taking a BGR frame and returning a list of (x, y, w, h) boxes.
"""
from __future__ import annotations

from typing import Callable, List, Optional, Sequence, Tuple

import cv2
import numpy as np

FaceBox = Tuple[int, int, int, int]
FaceDetector = Callable[[np.ndarray], Sequence[FaceBox]]


def pyfeat_detector(device: str = "auto") -> FaceDetector:
    """Face boxes from the shared Py-Feat engine, warmed on first use."""
    from painface.au import shared_engine

    engine = shared_engine(device=device)

    def detect(frame_bgr: np.ndarray) -> List[FaceBox]:
        if not engine.ready and not engine.warm():
            raise RuntimeError(f"Py-Feat detector unavailable: {engine.init_error}")
        r = engine.analyze_frame(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB),
                                 max_wait_s=30.0)
        if not r.ok or not r.box:
            return []
        x, y, w, h = r.box
        return [(int(round(x)), int(round(y)), int(round(w)), int(round(h)))]

    return detect


def default_detector() -> FaceDetector:
    """The face finder used when `extract_rgb` is given none."""
    try:
        return pyfeat_detector()
    except ImportError as e:                               # noqa: BLE001
        raise RuntimeError(
            "No face detector available: py-feat is not installed, and OpenCV "
            f"{cv2.__version__} has no Haar cascades. Install py-feat, or pass "
            "face_detector= to extract_rgb()."
        ) from e


def _rois(x, y, w, h):
    return {
        "forehead": (x + int(0.30 * w), y + int(0.08 * h), int(0.40 * w), int(0.15 * h)),
        "left_cheek": (x + int(0.15 * w), y + int(0.50 * h), int(0.20 * w), int(0.18 * h)),
        "right_cheek": (x + int(0.65 * w), y + int(0.50 * h), int(0.20 * w), int(0.18 * h)),
    }


def _skin_mean(frame_bgr, box):
    x, y, w, h = box
    patch = frame_bgr[max(y, 0):y + h, max(x, 0):x + w]
    if patch.size == 0:
        return None, 0
    ycc = cv2.cvtColor(patch, cv2.COLOR_BGR2YCrCb)
    mask = cv2.inRange(ycc, (0, 133, 77), (255, 173, 127)) > 0
    n = int(mask.sum())
    if n < 20:
        mask = np.ones(patch.shape[:2], bool)
        n = mask.size
    b, g, r = (patch[..., i][mask].mean() for i in range(3))
    return np.array([r, g, b]), n


def extract_rgb(path: str, detect_every: int = 5, max_seconds: float | None = None,
                progress=None, face_detector: Optional[FaceDetector] = None):
    detect = face_detector or default_detector()
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise IOError(f"Cannot open video: {path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    if fps <= 1 or fps > 240:
        fps = 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    ts, rgb, face_found = [], [], []
    box = None
    i = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        t = i / fps
        if max_seconds and t > max_seconds:
            break
        if i % detect_every == 0 or box is None:
            faces = detect(frame)
            if len(faces):
                nb = np.array(max(faces, key=lambda f: f[2] * f[3]), float)
                box = nb if box is None else 0.7 * box + 0.3 * nb
        if box is not None:
            acc, n_tot = np.zeros(3), 0
            for roi in _rois(*box.astype(int)).values():
                m, n = _skin_mean(frame, roi)
                if m is not None:
                    acc += m * n
                    n_tot += n
            if n_tot:
                ts.append(t)
                rgb.append(acc / n_tot)
                face_found.append(True)
        i += 1
        if progress and total and i % 30 == 0:
            progress(i / total)
    cap.release()
    if len(rgb) < fps * 5:
        raise ValueError("Less than 5 s of face data found in the video.")
    return np.array(ts), np.array(rgb).T, float(fps)
