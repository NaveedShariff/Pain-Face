"""
vitals.py — rPPG side of Pain-Face: a rolling colour buffer that yields vitals.

The browser extracts mean skin RGB per video frame (forehead + cheeks, from the
MediaPipe mesh) and streams those triples here. This module buffers them, runs
the classical method bank from `rppg_core` over a sliding window, and reduces
the result to the handful of autonomic features the fusion model consumes.

Keeping colour extraction in the browser and analysis here is deliberate: the
colour trace needs every frame at ~30 Hz for clean inter-beat intervals, while
Py-Feat only manages ~17 fps, so the two run at their own rates instead of
throttling each other.
"""
from __future__ import annotations

import math
import time
from collections import deque
from typing import Deque, Dict, List, Optional, Tuple

import numpy as np

import rppg_core as core

MIN_SECONDS = 6.0          # below this a spectrum is meaningless
# The HR band runs to 3.5 Hz, so anything sampled under ~7 Hz aliases the pulse
# straight into it and yields a confident, wrong heart rate. Browsers throttle
# hidden tabs to about 1 fps, and slow machines drop frames, so the arriving
# rate is checked rather than assumed: a refusal is better than a plausible
# number built from aliased data.
MIN_EFFECTIVE_FS = 7.7     # 2.2x the 3.5 Hz top of the HR band
HRV_SECONDS = 30.0         # RMSSD/SDNN need at least this much to be worth showing
# A sliding window selected by `t >= t[-1] - window_s` lands one sample short of
# its nominal width, so compare against the threshold with a little slack.
HRV_TOL_S = 0.5


class VitalsBuffer:
    """Sliding RGB buffer with cached analysis."""

    def __init__(self, window_s: float = 20.0, fs: float = 30.0, primary: str = "POS",
                 min_interval_s: float = 1.0):
        self.window_s = float(window_s)
        self.fs = float(fs)
        self.primary = primary
        # Wall-clock floor between re-analyses. Right for live capture, where
        # frames arrive in real time; set to 0 to replay a trace as fast as it
        # can be fed (offline analysis, tests, benchmarking).
        self.min_interval_s = float(min_interval_s)
        cap = int(self.fs * max(self.window_s, 60.0) * 1.5) + 64
        self._t: Deque[float] = deque(maxlen=cap)
        self._rgb: Deque[Tuple[float, float, float]] = deque(maxlen=cap)
        self.last: Optional[dict] = None
        self.last_at: float = 0.0
        self.analyses = 0
        self.last_error: Optional[str] = None

    # -- ingest -----------------------------------------------------------
    def extend(self, t: List[float], rgb: List[List[float]]) -> int:
        """Append samples, ignoring malformed or non-finite entries."""
        added = 0
        for ti, tri in zip(t, rgb):
            if tri is None or len(tri) < 3:
                continue
            try:
                ti = float(ti)
                r, g, b = (float(tri[0]), float(tri[1]), float(tri[2]))
            except (TypeError, ValueError):
                continue
            if not all(math.isfinite(v) for v in (ti, r, g, b)):
                continue
            self._t.append(ti)
            self._rgb.append((r, g, b))
            added += 1
        return added

    def clear(self) -> None:
        self._t.clear()
        self._rgb.clear()
        self.last = None

    @property
    def seconds(self) -> float:
        return (self._t[-1] - self._t[0]) if len(self._t) > 1 else 0.0

    @property
    def n(self) -> int:
        return len(self._t)

    @property
    def effective_fs(self) -> Optional[float]:
        """Median arrival rate of the incoming samples, in Hz."""
        if len(self._t) < 8:
            return None
        t = np.fromiter(self._t, float, len(self._t))
        d = np.diff(t[-min(len(t), 240):])
        d = d[d > 0]
        if d.size < 4:
            return None
        step = float(np.median(d))
        return 1.0 / step if step > 0 else None

    def window(self) -> Optional[Tuple[np.ndarray, np.ndarray]]:
        """The most recent `window_s` of samples as (t, (3, N) rgb)."""
        if len(self._t) < 8:
            return None
        t = np.fromiter(self._t, float, len(self._t))
        rgb = np.array(self._rgb, float).T
        keep = t >= (t[-1] - self.window_s)
        return t[keep], rgb[:, keep]

    # -- analysis ---------------------------------------------------------
    def analyze(self, force: bool = False,
                min_interval_s: Optional[float] = None) -> Optional[dict]:
        """Run the method bank if enough new data has arrived. Cached otherwise."""
        now = time.perf_counter()
        gap = self.min_interval_s if min_interval_s is None else float(min_interval_s)
        if not force and self.last is not None and (now - self.last_at) < gap:
            return self.last
        win = self.window()
        if win is None:
            return self.last
        t, rgb = win
        if (t[-1] - t[0]) < MIN_SECONDS:
            return self.last
        eff = self.effective_fs
        if eff is not None and eff < MIN_EFFECTIVE_FS:
            self.last = None
            self.last_error = (f"frames arriving at {eff:.1f} Hz — below the "
                               f"{MIN_EFFECTIVE_FS:.1f} Hz needed to measure a pulse "
                               f"without aliasing")
            return None
        try:
            tu, rgbu = core.resample_uniform(t, rgb, self.fs)
            res = core.analyze(rgbu, self.fs, primary=self.primary, with_series=True)
        except Exception as e:                            # noqa: BLE001
            self.last_error = f"{type(e).__name__}: {e}"
            return self.last
        res["window_s"] = round(float(t[-1] - t[0]), 2)
        res["samples"] = int(rgb.shape[1])
        self.last, self.last_at = core._clean(res), now
        self.analyses += 1
        self.last_error = None
        return self.last

    # -- reduction --------------------------------------------------------
    def features(self) -> Dict[str, Optional[float]]:
        """The autonomic features the fusion model scores against baseline."""
        r = self.last
        if not r:
            return {k: None for k in ("hr", "hr_snr", "rmssd", "sdnn", "lf_hf",
                                      "resp", "perfusion", "spo2_ratio")}
        hrv = r.get("hrv") or {}
        resp = r.get("respiration") or {}
        prim = (r.get("methods") or {}).get(r.get("primary") or "", {})
        long_enough = float(r.get("window_s") or 0.0) >= HRV_SECONDS - HRV_TOL_S
        return {
            "hr": _num(r.get("fused_hr")),
            "hr_snr": _num(prim.get("snr")),
            # Short-term HRV is noise below ~30 s, so withhold it rather than
            # feeding the baseline a figure that will drift as the window fills.
            "rmssd": _num(hrv.get("rmssd_ms")) if long_enough else None,
            "sdnn": _num(hrv.get("sdnn_ms")) if long_enough else None,
            "lf_hf": _num(hrv.get("lf_hf")) if long_enough else None,
            "resp": _num(resp.get("fused")),
            "perfusion": _num(r.get("perfusion_index_pct")),
            "spo2_ratio": _num(r.get("spo2_ratio_uncalibrated")),
        }

    def snapshot(self) -> dict:
        """Compact payload for the UI."""
        r = self.last or {}
        hrv = r.get("hrv") or {}
        feats = self.features()
        eff = self.effective_fs
        return {
            "ready": self.last is not None,
            "effective_fs": round(eff, 1) if eff else None,
            "sampling_ok": eff is None or eff >= MIN_EFFECTIVE_FS,
            "min_fs": MIN_EFFECTIVE_FS,
            "window_s": r.get("window_s"),
            "buffer_s": round(self.seconds, 1),
            "samples": self.n,
            "fused_hr": feats["hr"],
            "primary": r.get("primary"),
            "methods": r.get("methods") or {},
            "features": feats,
            "hrv": {k: _num(hrv.get(k)) for k in
                    ("rmssd_ms", "sdnn_ms", "sdsd_ms", "pnn50_pct", "pnn20_pct",
                     "mean_ibi_ms", "sd1_ms", "sd2_ms", "sd1_sd2", "stress_index",
                     "lf_hf", "lf_nu", "hf_nu", "n_beats", "artifact_pct",
                     "hr_from_ibi")},
            "respiration": r.get("respiration") or {},
            "perfusion_index_pct": _num(r.get("perfusion_index_pct")),
            "spo2_ratio": _num(r.get("spo2_ratio_uncalibrated")),
            "series": r.get("series") or {},
            "hrv_ready": float(r.get("window_s") or 0) >= HRV_SECONDS - HRV_TOL_S,
            "analyses": self.analyses,
            "error": self.last_error,
        }


def _num(v) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None
