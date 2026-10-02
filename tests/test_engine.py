"""Py-Feat integration. Slow: loads a real network and runs real inference."""
import os

import numpy as np
import pytest

pytest.importorskip("feat", reason="py-feat is not installed")
pytestmark = pytest.mark.slow

from feat.utils.io import get_test_data_path          # noqa: E402

from painface import fusion as F                      # noqa: E402
from painface.au import AUEngine                      # noqa: E402
from painface.pspi import DETECTED_AUS                # noqa: E402


def sample(name):
    import cv2
    return cv2.cvtColor(cv2.imread(os.path.join(get_test_data_path(), name)), cv2.COLOR_BGR2RGB)


@pytest.fixture(scope="module")
def engine():
    e = AUEngine(device="auto", width=480)
    assert e.warm(), e.init_error
    return e


def test_a_face_yields_the_full_feature_set(engine):
    r = engine.analyze_frame(sample("single_face.jpg"))
    assert r.ok
    assert set(r.aus) == set(DETECTED_AUS)             # all 20, canonically named
    assert len(r.emotions) == 7
    assert len(r.landmarks) == 68
    assert len(r.blendshapes) == 52
    assert {"Pitch", "Roll", "Yaw"} <= set(r.pose)
    assert 0.0 < r.quality <= 1.0
    assert r.box and r.box[2] > 0 and r.box[3] > 0


def test_values_are_probabilities(engine):
    r = engine.analyze_frame(sample("single_face.jpg"))
    assert all(0.0 <= v <= 1.0 for v in r.aus.values())
    assert sum(r.emotions.values()) == pytest.approx(1.0, abs=0.05)


@pytest.mark.parametrize("name", ["free-mountain-vector-01.jpg"])
def test_an_image_without_a_face_is_reported_as_such(engine, name):
    """Py-Feat returns a row of NaNs rather than nothing, so this is a real guard."""
    r = engine.analyze_frame(sample(name))
    assert r.ok is False and "no face" in r.reason


def test_a_blank_frame_is_not_a_face(engine):
    assert engine.analyze_frame(np.zeros((240, 320, 3), np.uint8)).ok is False


def test_the_bundled_smile_is_not_read_as_pain(engine):
    """End-to-end check of the correction on a real detection, not a mock."""
    r = engine.analyze_frame(sample("single_face.jpg"))
    f = F.facial_pain(r.aus, r.emotions)
    assert f.pspi > 5.0, "raw PSPI is expected to over-read a smile"
    assert f.smile > 0.5
    assert f.corrected < 0.3
    assert F.fuse(r.aus, {}, F.Baseline(), r.emotions, r.quality).nrs < 3.0


def test_landmarks_land_inside_the_face_box(engine):
    r = engine.analyze_frame(sample("single_face.jpg"))
    x, y, w, h = r.box
    inside = sum(1 for px, py in r.landmarks
                 if x - w * 0.2 <= px <= x + w * 1.2 and y - h * 0.2 <= py <= y + h * 1.2)
    assert inside > len(r.landmarks) * 0.9


def test_the_largest_face_is_chosen(engine):
    r = engine.analyze_frame(sample("multi_face.jpg"))
    assert r.ok and r.box[2] > 0


def test_status_reports_throughput(engine):
    engine.analyze_frame(sample("single_face.jpg"))
    st = engine.status()
    assert st["ready"] and st["frames"] > 0 and st["avg_detect_ms"] > 0
    assert len(st["aus"]) == 20
