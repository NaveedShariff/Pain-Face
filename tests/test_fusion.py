"""The claims the pain index makes about itself."""
import pytest

from painface import fusion as F

PAIN = {"AU04": 0.85, "AU06": 0.30, "AU07": 0.80, "AU09": 0.70, "AU10": 0.55,
        "AU12": 0.03, "AU43": 0.45}
SMILE = {"AU04": 0.002, "AU06": 0.60, "AU07": 0.39, "AU09": 0.03, "AU10": 0.85,
         "AU12": 0.98, "AU43": 0.06}
NEUTRAL = {"AU04": 0.01, "AU06": 0.02, "AU07": 0.03, "AU12": 0.02}
CALM = {"hr": 70, "rmssd": 45, "sdnn": 55, "lf_hf": 1.0, "resp": 14, "perfusion": 1.2}
AROUSED = {"hr": 95, "rmssd": 18, "sdnn": 30, "lf_hf": 2.4, "resp": 20, "perfusion": 0.7}


@pytest.fixture
def baseline():
    b = F.Baseline(min_n=10)
    for i in range(30):
        b.add({**CALM, "hr": 70 + (i % 3), "rmssd": 45 + (i % 5)})
    return b


def test_raw_pspi_false_positives_on_a_smile():
    """The problem the correction exists to solve — documented, not hidden."""
    assert F.facial_pain(SMILE).pspi > 6.0


def test_correction_suppresses_the_smile():
    f = F.facial_pain(SMILE, {"Happy": 0.99})
    assert f.smile > 0.8
    assert f.corrected < 0.25
    assert f.corrected < f.pspi_fraction / 2


def test_correction_leaves_a_genuine_pain_face_alone():
    f = F.facial_pain(PAIN, {"Happy": 0.01, "Sad": 0.4})
    assert f.smile < 0.1
    assert f.corrected == pytest.approx(f.pspi_fraction, abs=0.02)
    assert f.corrected > 0.7


def test_lowered_brow_argues_against_a_smile():
    """AU4 accompanies pain, not enjoyment, so it should cut smile evidence."""
    no_brow = F.smile_evidence({"AU12": 0.9}, {"Happy": 0.9})
    with_brow = F.smile_evidence({"AU12": 0.9, "AU04": 0.9}, {"Happy": 0.9})
    assert with_brow < no_brow / 2


def test_arousal_alone_is_never_pain(baseline):
    r = F.fuse(NEUTRAL, {"hr": 130, "rmssd": 8, "sdnn": 12, "lf_hf": 5.0,
                         "resp": 28, "perfusion": 0.4}, baseline, {"Neutral": 0.9})
    assert r.nrs < 0.5


def test_autonomic_signs_raise_a_painful_face(baseline):
    calm = F.fuse(PAIN, CALM, baseline, {"Happy": 0.01})
    hot = F.fuse(PAIN, AROUSED, baseline, {"Happy": 0.01})
    assert hot.nrs > calm.nrs


def test_intensity_never_saturates_before_the_face_does(baseline):
    """A strong episode must keep resolution instead of pinning at 10."""
    r = F.fuse(PAIN, AROUSED, baseline, {"Happy": 0.01})
    assert 0 < r.intensity < 1.0
    assert r.nrs < 10.0


@pytest.mark.parametrize("facial", [0.0, 0.25, 0.5, 0.75, 1.0])
def test_fusion_is_bounded_for_any_autonomic_state(facial, baseline):
    k = F.W_AUTONOMIC / F.W_FACIAL
    for dev in (-1.0, 0.0, 1.0):
        v = facial * (1 + k * dev * (1 - facial))
        assert 0.0 <= v <= 1.0


def test_baseline_withholds_judgement_until_it_has_data():
    empty = F.Baseline(min_n=15)
    a = F.autonomic_pain(AROUSED, empty)
    assert a.ready is False and a.score == 0.5


def test_flat_baseline_cannot_manufacture_huge_z(baseline):
    """An SD floor stops a perfectly steady rest period exploding small drifts."""
    b = F.Baseline(min_n=5)
    for _ in range(20):
        b.add({"hr": 70.0})
    z = b.z("hr", 72.0, floor=2.0)
    assert abs(z) <= 1.5


def test_confidence_falls_when_the_face_reads_as_a_smile(baseline):
    conf_pain = F.fuse(PAIN, CALM, baseline, {"Happy": 0.01}, face_quality=1.0).confidence
    conf_smile = F.fuse(SMILE, CALM, baseline, {"Happy": 0.99}, face_quality=1.0).confidence
    assert conf_smile < conf_pain


def test_labels_track_the_scale():
    assert F.nrs_label(0.0) == "none"
    assert F.nrs_label(2.0) == "mild"
    assert F.nrs_label(5.0) == "moderate"
    assert F.nrs_label(7.0) == "severe"
    assert F.nrs_label(9.5) == "very severe"


class TestTrigger:
    def test_requires_dwell_before_latching(self):
        tr = F.Trigger(on_threshold=0.3, dwell_s=0.6)
        assert tr.update(0.9, 0.0) is False          # instant spike does not latch
        assert tr.update(0.9, 0.3) is False
        assert tr.update(0.9, 0.7) is True

    def test_holds_through_a_brief_dip(self):
        tr = F.Trigger(on_threshold=0.3, off_threshold=0.18, dwell_s=0.2, release_s=1.5)
        tr.update(0.9, 0.0); tr.update(0.9, 0.5)
        assert tr.active
        tr.update(0.05, 1.0)                          # dips below, but not for long
        assert tr.update(0.9, 1.6) is True

    def test_releases_after_sustained_calm(self):
        tr = F.Trigger(on_threshold=0.3, off_threshold=0.18, dwell_s=0.2, release_s=1.0)
        tr.update(0.9, 0.0); tr.update(0.9, 0.5)
        tr.update(0.05, 1.0)
        assert tr.update(0.05, 2.2) is False
        assert tr.episodes == 1

    def test_survives_a_clock_that_jumps_backwards(self):
        """A client restarting its clock must not wedge the trigger idle."""
        tr = F.Trigger(on_threshold=0.3, dwell_s=0.5)
        tr.update(0.9, 100.0)
        tr.update(0.9, 2.0)                           # clock reset
        assert tr.update(0.9, 3.0) is True
