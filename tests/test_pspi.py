"""PSPI arithmetic and the pain-AU vocabulary."""
import pytest

from painface import pspi as P


def test_canon_accepts_every_spelling():
    for raw in ("AU4", "au04", "4", "AU04", "AU04_r", " au4 "):
        assert P.canon(raw) == "AU04"


def test_max_score_is_sixteen():
    full = {c: 1.0 for c in ("AU04", "AU06", "AU07", "AU09", "AU10", "AU43")}
    assert P.pspi(full) == pytest.approx(P.PSPI_MAX) == pytest.approx(16.0)


def test_neutral_face_scores_zero():
    assert P.pspi({c: 0.0 for c in P.DETECTED_AUS}) == pytest.approx(0.0)


def test_terms_combine_by_max_not_sum():
    """AU6 and AU7 are one orbital term, so two half-active AUs is not a full one."""
    both = P.pspi_terms({"AU06": 0.6, "AU07": 0.6})["orbital_tightening"]
    one = P.pspi_terms({"AU06": 0.6})["orbital_tightening"]
    assert both == pytest.approx(one) == pytest.approx(3.0)


def test_eye_closure_is_worth_one_point_not_five():
    assert P.pspi({"AU43": 1.0}) == pytest.approx(1.0)
    assert P.pspi({"AU04": 1.0}) == pytest.approx(5.0)


def test_missing_aus_are_treated_as_absent():
    assert P.pspi({"AU04": 0.5}) == pytest.approx(2.5)


def test_non_finite_and_junk_values_are_dropped():
    out = P.normalize_aus({"AU04": float("nan"), "AU06": "x", "AU07": 0.5, "AU09": 3.0})
    assert "AU04" not in out and "AU06" not in out
    assert out["AU07"] == 0.5
    assert out["AU09"] == 1.0          # clamped into [0, 1]


def test_pspi_raw_uses_coder_intensities():
    assert P.pspi_raw({"AU04": 3, "AU07": 2, "AU10": 1, "AU43": 1}) == pytest.approx(7.0)
    assert P.pspi_raw({"AU04": 9}) == pytest.approx(5.0)       # clipped to the term max


def test_every_pain_au_is_one_py_feat_reports():
    assert set(P.PAIN_AUS) <= set(P.DETECTED_AUS)


def test_au27_is_not_claimed():
    """Py-Feat has no AU27, so the mouth group must not depend on it."""
    assert "AU27" not in P.DETECTED_AUS
    assert "AU27" not in P.MOUTH_AUS
    assert "AU27" not in P.AU_NAMES


def test_active_pain_aus_respects_threshold_and_order():
    aus = {"AU04": 0.9, "AU07": 0.55, "AU25": 0.8, "AU12": 0.1, "AU09": 0.2}
    assert P.active_pain_aus(aus) == ["AU04", "AU07", "AU25"]
    assert P.active_pain_aus(aus, threshold=0.85) == ["AU04"]
