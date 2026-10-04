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


class TestStandardFormula:
    """Pin the published definition term by term.

        Prkachin & Solomon (2008)
        PSPI = AU4 + max(AU6, AU7) + max(AU9, AU10) + AU43

    AU4, the orbital term and the levator term each contribute 0-5; AU43
    contributes 0-1; the score therefore runs 0-16. These cases are worked by
    hand so a refactor cannot quietly change the arithmetic.
    """

    def test_term_ceilings_are_five_five_five_one(self):
        assert [pts for _, _, pts in P.PSPI_TERMS] == [5.0, 5.0, 5.0, 1.0]
        assert P.PSPI_MAX == 16.0

    def test_term_membership_matches_the_definition(self):
        assert {label: list(codes) for label, codes, _ in P.PSPI_TERMS} == {
            "brow_lowering": ["AU04"],
            "orbital_tightening": ["AU06", "AU07"],
            "levator_contraction": ["AU09", "AU10"],
            "eye_closure": ["AU43"],
        }

    @pytest.mark.parametrize("aus,expected", [
        ({"AU04": 0, "AU06": 0, "AU07": 0, "AU09": 0, "AU10": 0, "AU43": 0}, 0.0),
        ({"AU04": 1, "AU06": 1, "AU07": 1, "AU09": 1, "AU10": 1, "AU43": 1}, 16.0),
        ({"AU04": 1}, 5.0),
        ({"AU43": 1}, 1.0),
        ({"AU06": 1, "AU07": 1}, 5.0),          # paired terms take the max...
        ({"AU09": 1, "AU10": 1}, 5.0),          # ...they are never summed
        ({"AU06": 0.4, "AU07": 0.9}, 4.5),      # the larger of the pair wins
        ({"AU09": 0.7, "AU10": 0.2}, 3.5),
        # 0.8*5 + max(.2,.6)*5 + max(.4,.7)*5 + 0.3*1
        ({"AU04": 0.8, "AU06": 0.2, "AU07": 0.6, "AU09": 0.4, "AU10": 0.7, "AU43": 0.3}, 10.8),
    ])
    def test_worked_cases(self, aus, expected):
        assert P.pspi(aus) == pytest.approx(expected)

    def test_aus_outside_the_definition_contribute_nothing(self):
        """AU12, AU25 and the rest are informative but are not PSPI terms."""
        assert P.pspi({"AU01": 1, "AU12": 1, "AU20": 1, "AU25": 1, "AU26": 1}) == 0.0

    def test_fraction_is_the_score_over_sixteen(self):
        aus = {"AU04": 0.8, "AU07": 0.6, "AU10": 0.7, "AU43": 0.3}
        assert P.pspi_fraction(aus) == pytest.approx(P.pspi(aus) / 16.0)
        assert 0.0 <= P.pspi_fraction(aus) <= 1.0

    def test_score_is_monotonic_in_every_term(self):
        base = {"AU04": 0.4, "AU07": 0.4, "AU10": 0.4, "AU43": 0.4}
        for code in ("AU04", "AU07", "AU10", "AU43"):
            more = dict(base, **{code: 0.9})
            assert P.pspi(more) > P.pspi(base), code

    def test_coder_intensities_use_the_same_structure(self):
        """With true FACS 0-5 intensities the arithmetic is the literal one."""
        assert P.pspi_raw({"AU04": 3, "AU07": 2, "AU10": 1, "AU43": 1}) == pytest.approx(7.0)
        assert P.pspi_raw({"AU06": 4, "AU07": 2}) == pytest.approx(4.0)   # max, not 6
        assert P.pspi_raw({"AU04": 5, "AU06": 5, "AU09": 5, "AU43": 1}) == pytest.approx(16.0)
