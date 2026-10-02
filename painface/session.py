"""
session.py — recording, summarising and exporting a Pain-Face session.

A session is an append-only timeline of samples. Each sample pairs one facial
reading (AUs, emotions, PSPI, corrected pain) with whatever rPPG vitals were
current at that moment, plus the fused index and trigger state. From that we
derive per-episode statistics — a pain episode being one latched stretch of
the trigger — and export either a tidy CSV for stats packages or a single JSON
blob with the full session.
"""
from __future__ import annotations

import csv
import io
import json
import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

from .pspi import AU_NAMES, DETECTED_AUS, PAIN_AUS

VITAL_KEYS = ("hr", "hr_snr", "rmssd", "sdnn", "lf_hf", "resp", "perfusion", "spo2_ratio")
EMOTION_KEYS = ("Neutral", "Happy", "Sad", "Surprise", "Fear", "Disgust", "Anger")


@dataclass
class Episode:
    """One latched stretch of elevated pain."""
    index: int
    start_t: float
    end_t: Optional[float] = None
    peak_nrs: float = 0.0
    peak_t: float = 0.0
    sum_nrs: float = 0.0
    n: int = 0
    peak_aus: List[str] = field(default_factory=list)

    @property
    def duration_s(self) -> Optional[float]:
        return None if self.end_t is None else round(self.end_t - self.start_t, 2)

    @property
    def mean_nrs(self) -> float:
        return self.sum_nrs / self.n if self.n else 0.0

    def as_dict(self) -> dict:
        return {"index": self.index, "start_t": round(self.start_t, 2),
                "end_t": None if self.end_t is None else round(self.end_t, 2),
                "duration_s": self.duration_s, "peak_nrs": round(self.peak_nrs, 2),
                "peak_t": round(self.peak_t, 2), "mean_nrs": round(self.mean_nrs, 2),
                "samples": self.n, "peak_aus": self.peak_aus}


class PainSession:
    """Append-only recorder for one measurement run."""

    def __init__(self, label: str = "", max_samples: int = 200_000):
        self.label = label
        self.started_at = time.time()
        self.started_mono = time.perf_counter()
        self.max_samples = max_samples
        self.samples: List[Dict[str, Any]] = []
        self.episodes: List[Episode] = []
        self._open: Optional[Episode] = None
        self.dropped = 0

    # -- recording --------------------------------------------------------
    def add(self, t: float, pain: Dict[str, Any], aus: Dict[str, float],
            emotions: Optional[Dict[str, float]] = None,
            vitals: Optional[Dict[str, Optional[float]]] = None,
            quality: float = 0.0, triggered: bool = False) -> None:
        if len(self.samples) >= self.max_samples:
            self.dropped += 1
            return
        nrs = float(pain.get("nrs", 0.0) or 0.0)
        sample = {"t": round(float(t), 3), "nrs": round(nrs, 3),
                  "intensity": pain.get("intensity"),
                  "pspi": (pain.get("facial") or {}).get("pspi"),
                  "corrected": (pain.get("facial") or {}).get("corrected"),
                  "smile": (pain.get("facial") or {}).get("smile"),
                  "autonomic": (pain.get("autonomic") or {}).get("score"),
                  "confidence": pain.get("confidence"),
                  "label": pain.get("label"), "triggered": bool(triggered),
                  "quality": round(float(quality), 3),
                  "aus": {k: round(float(v), 4) for k, v in (aus or {}).items()},
                  "emotions": {k: round(float(v), 4) for k, v in (emotions or {}).items()},
                  "vitals": {k: vitals.get(k) for k in VITAL_KEYS} if vitals else {}}
        self.samples.append(sample)
        self._track_episode(t, nrs, triggered, (pain.get("facial") or {}).get("active_aus") or [])

    def _track_episode(self, t: float, nrs: float, triggered: bool, active: List[str]) -> None:
        if triggered:
            if self._open is None:
                self._open = Episode(index=len(self.episodes) + 1, start_t=t)
                self.episodes.append(self._open)
            ep = self._open
            ep.n += 1
            ep.sum_nrs += nrs
            ep.end_t = t
            if nrs > ep.peak_nrs:
                ep.peak_nrs, ep.peak_t, ep.peak_aus = nrs, t, list(active)
        elif self._open is not None:
            self._open.end_t = t
            self._open = None

    # -- summary ----------------------------------------------------------
    def summary(self) -> dict:
        n = len(self.samples)
        if not n:
            return {"samples": 0, "label": self.label, "episodes": []}
        nrs = [s["nrs"] for s in self.samples]
        trig = [s for s in self.samples if s["triggered"]]
        duration = self.samples[-1]["t"] - self.samples[0]["t"]
        peak_i = max(range(n), key=lambda i: nrs[i])

        au_prev: Dict[str, float] = {}
        for code in PAIN_AUS:
            hits = sum(1 for s in self.samples if float(s["aus"].get(code, 0.0)) >= 0.5)
            au_prev[code] = round(hits / n, 4)

        vit_mean: Dict[str, Optional[float]] = {}
        for k in VITAL_KEYS:
            vals = [float(s["vitals"][k]) for s in self.samples
                    if s["vitals"].get(k) is not None and math.isfinite(float(s["vitals"][k]))]
            vit_mean[k] = round(sum(vals) / len(vals), 2) if vals else None

        return {
            "label": self.label,
            "started_at": self.started_at,
            "samples": n,
            "dropped": self.dropped,
            "duration_s": round(duration, 2),
            "nrs_peak": round(max(nrs), 2),
            "nrs_peak_t": round(self.samples[peak_i]["t"], 2),
            "nrs_mean": round(sum(nrs) / n, 2),
            "nrs_mean_while_triggered": round(sum(s["nrs"] for s in trig) / len(trig), 2) if trig else None,
            "time_in_pain_s": round(duration * len(trig) / n, 2) if duration else 0.0,
            "time_in_pain_pct": round(100 * len(trig) / n, 1),
            "episode_count": len(self.episodes),
            "episodes": [e.as_dict() for e in self.episodes],
            "pain_au_prevalence": au_prev,
            "vitals_mean": vit_mean,
        }

    # -- export -----------------------------------------------------------
    def to_json(self, include_samples: bool = True) -> str:
        doc: Dict[str, Any] = {"app": "Pain-Face", "summary": self.summary(),
                               "au_names": {k: AU_NAMES.get(k, k) for k in DETECTED_AUS}}
        if include_samples:
            doc["samples"] = self.samples
        return json.dumps(doc, indent=1, allow_nan=False, default=_jsonable)

    def to_csv(self) -> str:
        """One tidy row per sample: time, pain, AUs, emotions, vitals."""
        cols = (["t", "nrs", "intensity", "pspi", "corrected", "smile", "autonomic",
                 "confidence", "label", "triggered", "quality"]
                + list(DETECTED_AUS) + list(EMOTION_KEYS) + list(VITAL_KEYS))
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(cols)
        for s in self.samples:
            row = [s.get(c) for c in cols[:11]]
            row += [s["aus"].get(c) for c in DETECTED_AUS]
            row += [s["emotions"].get(c) for c in EMOTION_KEYS]
            row += [s["vitals"].get(c) for c in VITAL_KEYS]
            w.writerow(["" if v is None else v for v in row])
        return buf.getvalue()

    def timeline(self, keys: Iterable[str] = ("t", "nrs", "pspi", "corrected", "triggered")) -> dict:
        """Column-oriented view, for plotting."""
        return {k: [s.get(k) for s in self.samples] for k in keys}


def _jsonable(o):
    if isinstance(o, float) and not math.isfinite(o):
        return None
    raise TypeError(f"not JSON serializable: {type(o).__name__}")
