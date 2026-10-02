"""rPPG buffer: recovery of a known pulse, and refusal when it cannot be measured."""
import pytest

import rppg_core as core
from painface.vitals import MIN_EFFECTIVE_FS, VitalsBuffer


def feed(buf, duration=40.0, fs=30.0, hr=72.0, rr=15.0):
    t, rgb = core.synthetic_rgb(duration, fs, hr=hr, rr=rr)
    buf.extend(t.tolist(), rgb.T.tolist())
    buf.analyze(force=True)
    return buf


@pytest.mark.parametrize("hr", [54.0, 72.0, 96.0, 120.0])
def test_recovers_a_known_heart_rate(hr):
    b = feed(VitalsBuffer(window_s=30.0), hr=hr)
    assert b.features()["hr"] == pytest.approx(hr, abs=1.5)


@pytest.mark.parametrize("fs", [30.0, 15.0, 8.0])
def test_adequate_sampling_rates_are_accepted(fs):
    b = feed(VitalsBuffer(window_s=30.0), fs=fs)
    assert b.snapshot()["sampling_ok"] is True
    assert b.features()["hr"] == pytest.approx(72.0, abs=1.5)


@pytest.mark.parametrize("fs", [5.0, 2.0, 1.1])
def test_aliased_sampling_is_refused_not_guessed(fs):
    """Below Nyquist for the pulse band, a confident HR would be a fabrication."""
    b = feed(VitalsBuffer(window_s=30.0), fs=fs)
    snap = b.snapshot()
    assert snap["sampling_ok"] is False
    assert snap["fused_hr"] is None
    assert "aliasing" in (b.last_error or "")


def test_effective_rate_is_measured_from_arrivals():
    b = feed(VitalsBuffer(window_s=30.0), fs=15.0)
    assert b.effective_fs == pytest.approx(15.0, rel=0.05)


def test_hrv_is_withheld_until_the_window_is_long_enough():
    short = feed(VitalsBuffer(window_s=15.0), duration=20.0)
    assert short.snapshot()["hrv_ready"] is False
    assert short.features()["rmssd"] is None

    long = feed(VitalsBuffer(window_s=30.0), duration=40.0)
    assert long.snapshot()["hrv_ready"] is True
    assert long.features()["rmssd"] is not None


def test_malformed_samples_are_skipped_without_raising():
    b = VitalsBuffer()
    added = b.extend([0.0, 0.1, 0.2, float("nan")],
                     [[1, 2], None, [1, 2, 3], [1, 2, 3]])
    assert added == 1


def test_respiration_is_recovered():
    b = feed(VitalsBuffer(window_s=30.0), rr=15.0)
    assert b.features()["resp"] == pytest.approx(15.0, abs=3.0)


def test_analysis_is_rate_limited_but_overridable():
    b = VitalsBuffer(window_s=30.0, min_interval_s=1000.0)
    feed(b)                                   # force=True gets through
    first = b.analyses
    b.analyze()                               # rate-limited, returns the cache
    assert b.analyses == first
    b.min_interval_s = 0.0
    b.analyze()
    assert b.analyses == first + 1


def test_all_eight_methods_survive_the_blas_flag_bug():
    """Regression guard: spurious Accelerate FP flags once failed 5 of 8."""
    t, rgb = core.synthetic_rgb(30.0, 30.0, hr=72, rr=15)
    res = core.analyze(rgb, 30.0, primary="POS", with_series=False)
    failed = {m: r["error"] for m, r in res["methods"].items() if "error" in r}
    assert not failed, f"methods reported errors on clean input: {failed}"
    assert res["fused_hr"] == pytest.approx(72.0, abs=1.0)


def test_genuinely_broken_input_still_errors():
    import numpy as np
    t, rgb = core.synthetic_rgb(20.0, 30.0)
    rgb[1, 50:60] = np.nan
    res = core.analyze(rgb, 30.0, primary="POS", with_series=False)
    assert any("error" in r for r in res["methods"].values())
