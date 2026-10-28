"""Skin-RGB extraction from a video file.

The import at the top is half the test: `rppg_video` used to build an OpenCV
Haar cascade at module scope, which OpenCV 5 removed, so every offline and
upload path raised AttributeError before a single frame was read.
"""
import numpy as np
import pytest

import rppg_video


FPS, N_FRAMES, W, H = 10.0, 60, 320, 240       # 6 s, enough for the 5 s minimum
FACE = (90, 50, 140, 160)                      # the box the stub detector returns


def write_clip(path, frames):
    import cv2
    fourcc = cv2.VideoWriter.fourcc(*"mp4v")
    vw = cv2.VideoWriter(str(path), fourcc, FPS, (W, H))
    assert vw.isOpened(), "no mp4v writer available"
    for f in frames:
        vw.write(f)
    vw.release()


def skin_frames(n=N_FRAMES, hr_bpm=72.0):
    """Frames of skin-coloured noise whose green channel pulses at `hr_bpm`."""
    rng = np.random.default_rng(0)
    out = []
    for i in range(n):
        frame = np.zeros((H, W, 3), np.uint8)
        pulse = 4.0 * np.sin(2 * np.pi * hr_bpm / 60.0 * i / FPS)
        skin = np.array([120, 150, 200], float) + np.array([0, pulse, 0])
        frame[:, :] = np.clip(skin + rng.normal(0, 2, 3), 0, 255).astype(np.uint8)
        out.append(frame)
    return out


@pytest.fixture
def clip(tmp_path):
    p = tmp_path / "clip.mp4"
    write_clip(p, skin_frames())
    return str(p)


def test_the_module_imports_without_building_a_face_model():
    """No detector is constructed at import time — that was the regression."""
    assert callable(rppg_video.extract_rgb)
    assert callable(rppg_video.pyfeat_detector)


def test_extract_rgb_returns_a_trace_for_every_face_frame(clip):
    calls = []

    def detector(frame_bgr):
        calls.append(frame_bgr.shape)
        return [FACE]

    t, rgb, fps = rppg_video.extract_rgb(clip, face_detector=detector)

    assert fps == pytest.approx(FPS)
    assert rgb.shape == (3, len(t))               # (R, G, B) x samples
    assert len(t) == N_FRAMES                     # a box on every frame
    assert t[0] == 0.0 and t[-1] == pytest.approx((N_FRAMES - 1) / FPS)
    assert np.all(np.diff(t) > 0)
    assert np.all((rgb >= 0) & (rgb <= 255))
    assert len(calls) == N_FRAMES // 5            # detect_every=5, box smoothed
    assert calls[0] == (H, W, 3)                  # full-resolution BGR frames


def test_the_green_pulse_survives_extraction(clip):
    _, rgb, _ = rppg_video.extract_rgb(clip, face_detector=lambda f: [FACE])
    green = rgb[1]
    assert green.std() > 0.5                      # the 72 bpm modulation is there
    assert rgb[0].mean() > green.mean()           # R > G for the skin colour used


def test_a_clip_with_no_face_is_an_error(clip):
    with pytest.raises(ValueError, match="face data"):
        rppg_video.extract_rgb(clip, face_detector=lambda f: [])


def test_a_missing_file_is_an_error(tmp_path):
    with pytest.raises(IOError, match="Cannot open"):
        rppg_video.extract_rgb(str(tmp_path / "nope.mp4"),
                               face_detector=lambda f: [FACE])


# -- the real detector ----------------------------------------------------
@pytest.mark.slow
def test_the_default_detector_finds_a_real_face(tmp_path):
    """End to end on the stock face image, with no detector passed in."""
    pytest.importorskip("feat", reason="py-feat is not installed")
    import cv2
    from feat.utils.io import get_test_data_path
    import os

    face = cv2.imread(os.path.join(get_test_data_path(), "single_face.jpg"))
    face = cv2.resize(face, (W, H), interpolation=cv2.INTER_AREA)
    p = tmp_path / "face.mp4"
    write_clip(p, [face.copy() for _ in range(N_FRAMES)])

    t, rgb, fps = rppg_video.extract_rgb(str(p))
    assert len(t) >= 5 * fps
    assert rgb.shape == (3, len(t))
    assert np.all((rgb > 0) & (rgb <= 255))
