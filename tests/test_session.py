"""Recording, episode detection and export."""
import csv
import io
import json

import pytest

from painface import fusion as F
from painface.session import PainSession


def run(pain_from=12.0, pain_to=24.0, duration=40.0, step=0.1):
    b = F.Baseline(min_n=10)
    for i in range(30):
        b.add({"hr": 70 + (i % 3), "rmssd": 45, "sdnn": 55, "lf_hf": 1.0,
               "resp": 14, "perfusion": 1.2})
    tr, s = F.Trigger(), PainSession(label="t")
    for i in range(int(duration / step)):
        t = i * step
        hurt = pain_from <= t < pain_to
        aus = ({"AU04": 0.8, "AU07": 0.75, "AU09": 0.6, "AU10": 0.5, "AU43": 0.4, "AU12": 0.02}
               if hurt else {"AU04": 0.03, "AU07": 0.05, "AU12": 0.05})
        vit = {"hr": 92 if hurt else 71, "rmssd": 20 if hurt else 45,
               "sdnn": 30 if hurt else 55, "lf_hf": 2.2 if hurt else 1.0,
               "resp": 19 if hurt else 14, "perfusion": 0.8 if hurt else 1.2}
        r = F.fuse(aus, vit, b, {"Neutral": 0.9}, face_quality=0.95)
        on = tr.update(r.intensity, t)
        s.add(t, r.as_dict(tr, t), aus, {"Neutral": 0.9}, vit, 0.95, on)
    return s


@pytest.fixture(scope="module")
def session():
    return run()


def test_one_episode_is_found(session):
    assert session.summary()["episode_count"] == 1


def test_episode_brackets_the_stimulus_allowing_for_hysteresis(session):
    e = session.summary()["episodes"][0]
    assert 12.0 <= e["start_t"] <= 13.5          # delayed by the dwell
    assert 24.0 <= e["end_t"] <= 26.0            # held open by the release
    assert e["peak_nrs"] > 5.0


def test_peak_aus_name_the_pain_pattern(session):
    assert set(session.summary()["episodes"][0]["peak_aus"]) >= {"AU04", "AU07", "AU09"}


def test_prevalence_matches_the_stimulus_duration(session):
    prev = session.summary()["pain_au_prevalence"]
    assert prev["AU04"] == pytest.approx(0.3, abs=0.02)      # 12 s of 40 s
    assert prev["AU12"] == 0.0


def test_calm_run_records_no_episode():
    s = run(pain_from=99, pain_to=99)
    assert s.summary()["episode_count"] == 0
    assert s.summary()["nrs_peak"] < 1.0


def test_csv_has_a_row_per_sample_and_every_au_column(session):
    rows = list(csv.reader(io.StringIO(session.to_csv())))
    header, body = rows[0], rows[1:]
    assert len(body) == len(session.samples)
    for col in ("t", "nrs", "pspi", "corrected", "AU04", "AU43", "Neutral", "hr", "rmssd"):
        assert col in header


def test_json_is_valid_and_finite(session):
    doc = json.loads(session.to_json())           # allow_nan=False: raises on NaN
    assert doc["app"] == "Pain-Face"
    assert len(doc["samples"]) == len(session.samples)
    assert doc["summary"]["episode_count"] == 1


def test_json_can_omit_samples(session):
    doc = json.loads(session.to_json(include_samples=False))
    assert "samples" not in doc and doc["summary"]["samples"] > 0


def test_empty_session_summarises_without_raising():
    assert PainSession().summary()["samples"] == 0


def test_sample_cap_is_enforced():
    s = PainSession(max_samples=5)
    for i in range(20):
        s.add(i, {"nrs": 1.0, "facial": {}, "autonomic": {}}, {"AU04": 0.1})
    assert len(s.samples) == 5 and s.dropped == 15
