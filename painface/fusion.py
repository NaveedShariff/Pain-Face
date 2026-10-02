"""
fusion.py — multimodal pain intensity from facial AUs plus rPPG autonomic signs.

Two channels, deliberately unequal:

  Facial (primary).  PSPI is the validated frame-level pain metric, but it is
  not pain-*specific*: AU6 (cheek raiser) and AU10 (upper lip raiser) are also
  smile and disgust components, so a broad grin scores ~7/16 on raw PSPI. Pain
  expressions are distinguished from smiles by what is absent — AU12 (lip
  corner puller) — and by the brow: pain shows AU4 lowering, happiness does
  not (Kunz & Lautenbacher 2014). `facial_pain()` therefore keeps the literal
  PSPI for comparability and derives a separate specificity-corrected score
  that discounts the shared AUs when smile evidence is present.

  Autonomic (corroborating).  Pain triggers sympathetic activation: heart rate
  rises, short-term HRV (RMSSD/SDNN) falls, LF/HF shifts up, respiration
  quickens and peripheral perfusion drops with vasoconstriction. None of these
  is pain-specific on its own — exercise, stress and caffeine all move them —
  so the autonomic channel can only corroborate or temper the facial reading,
  never create a pain score by itself.

Each autonomic feature is scored against a per-subject baseline captured
during a calm period, because absolute HR says nothing about pain while a
20 bpm rise above *this person's* rest does.

The output is an 0-10 index on the familiar numeric-rating-scale shape. It is
an observational estimate, not a measurement of what someone feels, and it is
not a medical device — see DISCLAIMER in the README.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, Mapping, Optional

from .pspi import (MOUTH_AUS, PSPI_MAX, active_pain_aus, mouth_activity,
                   normalize_aus, pspi, pspi_fraction, pspi_terms)

# Facial channel -----------------------------------------------------------
SMILE_AU = "AU12"
BROW_AU = "AU04"
# AUs that PSPI shares with smiling, and how much of each term we are willing
# to discount when smile evidence is strong.
SHARED_WITH_SMILE = {"orbital_tightening": 0.85, "levator_contraction": 0.65}

# Fusion weights (facial dominant; they need not sum to 1 — see fuse()).
W_FACIAL = 0.75
W_AUTONOMIC = 0.25

# Trigger hysteresis: pain must be this strong to latch on, and fall below the
# lower bound (for `release_s`) before it lets go. Prevents flicker.
TRIGGER_ON = 0.30
TRIGGER_OFF = 0.18
TRIGGER_DWELL_S = 0.6
TRIGGER_RELEASE_S = 1.5

NRS_MAX = 10.0


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if x < lo else hi if x > hi else x


def smile_evidence(aus: Mapping[str, float], emotions: Optional[Mapping[str, float]] = None) -> float:
    """How strongly the face reads as a smile rather than pain, in [0, 1].

    AU12 is the structural cue. A high 'Happy' emotion probability reinforces
    it, and a lowered brow (AU4) argues against it, since pain lowers the brow
    and enjoyment does not.
    """
    a = normalize_aus(aus)
    au12 = a.get(SMILE_AU, 0.0)
    brow = a.get(BROW_AU, 0.0)
    happy = 0.0
    if emotions:
        happy = _clamp(float(emotions.get("Happy", emotions.get("happy", 0.0)) or 0.0))
    ev = au12 * (0.55 + 0.45 * happy)
    return _clamp(ev * (1.0 - 0.7 * brow))


@dataclass
class FacialPain:
    pspi: float                  # literal PSPI, 0-16
    pspi_fraction: float         # PSPI / 16
    corrected: float             # specificity-corrected pain, [0, 1]
    smile: float                 # smile evidence, [0, 1]
    terms: Dict[str, float]      # the four PSPI terms, in points
    mouth: float                 # AU25/26 open-mouth component, [0, 1]
    active: list[str]            # pain AUs currently above threshold

    def as_dict(self) -> dict:
        return {"pspi": round(self.pspi, 3), "pspi_fraction": round(self.pspi_fraction, 4),
                "corrected": round(self.corrected, 4), "smile": round(self.smile, 4),
                "terms": {k: round(v, 3) for k, v in self.terms.items()},
                "mouth": round(self.mouth, 4), "active_aus": self.active}


def facial_pain(aus: Mapping[str, float],
                emotions: Optional[Mapping[str, float]] = None) -> FacialPain:
    """Facial pain channel: literal PSPI plus a smile-corrected score."""
    terms = pspi_terms(aus)
    raw = float(sum(terms.values()))
    smile = smile_evidence(aus, emotions)

    # Discount only the terms that smiling shares with pain, in proportion to
    # how much of each term is smile-explainable.
    corrected_points = 0.0
    for label, pts in terms.items():
        share = SHARED_WITH_SMILE.get(label, 0.0)
        corrected_points += pts * (1.0 - share * smile)
    corrected = _clamp(corrected_points / PSPI_MAX)

    return FacialPain(pspi=raw, pspi_fraction=raw / PSPI_MAX, corrected=corrected,
                      smile=smile, terms=terms, mouth=mouth_activity(aus),
                      active=active_pain_aus(aus))


# Autonomic channel --------------------------------------------------------
@dataclass
class Baseline:
    """Rolling calm-period reference for the autonomic features.

    Feed it samples while the subject is at rest; `ready` turns true once it
    holds `min_n` of them, after which `z()` reports signed deviations.
    """
    min_n: int = 20
    maxlen: int = 600
    _store: Dict[str, Deque[float]] = field(default_factory=dict)

    def add(self, feats: Mapping[str, Optional[float]]) -> None:
        for k, v in feats.items():
            if v is None or not math.isfinite(float(v)):
                continue
            self._store.setdefault(k, deque(maxlen=self.maxlen)).append(float(v))

    def n(self, key: str) -> int:
        return len(self._store.get(key, ()))

    @property
    def ready(self) -> bool:
        return bool(self._store) and max((len(v) for v in self._store.values()), default=0) >= self.min_n

    def stats(self, key: str) -> Optional[tuple[float, float]]:
        d = self._store.get(key)
        if not d or len(d) < max(4, self.min_n // 4):
            return None
        vals = list(d)
        mu = sum(vals) / len(vals)
        var = sum((v - mu) ** 2 for v in vals) / max(len(vals) - 1, 1)
        return mu, math.sqrt(var)

    def z(self, key: str, value: Optional[float], floor: float) -> Optional[float]:
        """Signed z-score, with `floor` as a minimum SD so a flat baseline
        cannot turn ordinary jitter into a huge deviation."""
        if value is None or not math.isfinite(float(value)):
            return None
        st = self.stats(key)
        if st is None:
            return None
        mu, sd = st
        return (float(value) - mu) / max(sd, floor)

    def as_dict(self) -> dict:
        return {"ready": self.ready,
                "n": {k: len(v) for k, v in self._store.items()},
                "mean": {k: round(s[0], 3) for k in self._store if (s := self.stats(k))}}


# feature -> (baseline SD floor, direction, saturating z). direction +1 means
# "higher than baseline indicates pain".
AUTONOMIC_FEATURES: Dict[str, tuple[float, float, float]] = {
    "hr":        (2.0,  +1.0, 3.0),   # tachycardia
    "rmssd":     (5.0,  -1.0, 2.5),   # parasympathetic withdrawal
    "sdnn":      (5.0,  -1.0, 2.5),
    "lf_hf":     (0.3,  +1.0, 2.5),   # sympathetic shift
    "resp":      (1.5,  +1.0, 2.5),   # faster breathing
    "perfusion": (0.15, -1.0, 2.5),   # vasoconstriction
}


@dataclass
class AutonomicPain:
    score: float                       # [0, 1]; 0.5 means "at baseline"
    contributions: Dict[str, float]    # per-feature [0, 1] after direction
    z: Dict[str, float]
    ready: bool

    def as_dict(self) -> dict:
        return {"score": round(self.score, 4), "ready": self.ready,
                "contributions": {k: round(v, 4) for k, v in self.contributions.items()},
                "z": {k: round(v, 3) for k, v in self.z.items()}}


def autonomic_pain(vitals: Mapping[str, Optional[float]], baseline: Baseline) -> AutonomicPain:
    """Arousal score in [0, 1] from rPPG features relative to a calm baseline.

    0.5 is "exactly at baseline"; 1.0 is every feature saturated in the
    pain-consistent direction. Returns ready=False (and a neutral 0.5) until
    the baseline holds enough calm samples to compare against.
    """
    zs: Dict[str, float] = {}
    contrib: Dict[str, float] = {}
    for key, (floor, direction, sat) in AUTONOMIC_FEATURES.items():
        z = baseline.z(key, vitals.get(key), floor)
        if z is None:
            continue
        zs[key] = z
        # Signed, saturating map to [0, 1] with 0.5 at baseline.
        contrib[key] = _clamp(0.5 + 0.5 * _clamp(direction * z / sat, -1.0, 1.0))

    if not contrib or not baseline.ready:
        return AutonomicPain(score=0.5, contributions=contrib, z=zs, ready=False)
    score = sum(contrib.values()) / len(contrib)
    return AutonomicPain(score=_clamp(score), contributions=contrib, z=zs, ready=True)


# Trigger ------------------------------------------------------------------
@dataclass
class Trigger:
    """Latching pain-onset detector with hysteresis and dwell times."""
    on_threshold: float = TRIGGER_ON
    off_threshold: float = TRIGGER_OFF
    dwell_s: float = TRIGGER_DWELL_S
    release_s: float = TRIGGER_RELEASE_S
    active: bool = False
    _above_since: Optional[float] = None
    _below_since: Optional[float] = None
    onset_t: Optional[float] = None
    episodes: int = 0

    def update(self, score: float, t: float) -> bool:
        # Time can jump backwards when a client restarts its clock mid-stream.
        # Without this the pending dwell would never elapse and the trigger
        # would sit idle through an obvious episode.
        for mark in ("_above_since", "_below_since"):
            since = getattr(self, mark)
            if since is not None and t < since:
                setattr(self, mark, t)
        if self.onset_t is not None and t < self.onset_t:
            self.onset_t = t
        if not self.active:
            if score >= self.on_threshold:
                self._above_since = t if self._above_since is None else self._above_since
                if t - self._above_since >= self.dwell_s:
                    self.active, self.onset_t, self._below_since = True, t, None
                    self.episodes += 1
            else:
                self._above_since = None
        else:
            if score <= self.off_threshold:
                self._below_since = t if self._below_since is None else self._below_since
                if t - self._below_since >= self.release_s:
                    self.active, self.onset_t, self._above_since = False, None, None
            else:
                self._below_since = None
        return self.active

    def as_dict(self, now: Optional[float] = None) -> dict:
        held = None
        if self.active and self.onset_t is not None and now is not None:
            held = round(now - self.onset_t, 2)
        return {"active": self.active, "episodes": self.episodes,
                "onset_t": self.onset_t, "held_s": held,
                "on_threshold": self.on_threshold, "off_threshold": self.off_threshold}


@dataclass
class PainReading:
    intensity: float            # [0, 1]
    nrs: float                  # 0-10
    facial: FacialPain
    autonomic: AutonomicPain
    confidence: float           # [0, 1]
    triggered: bool
    label: str

    def as_dict(self, trigger: Optional[Trigger] = None, now: Optional[float] = None) -> dict:
        out = {"intensity": round(self.intensity, 4), "nrs": round(self.nrs, 2),
               "label": self.label, "confidence": round(self.confidence, 3),
               "triggered": self.triggered,
               "facial": self.facial.as_dict(), "autonomic": self.autonomic.as_dict()}
        if trigger is not None:
            out["trigger"] = trigger.as_dict(now)
        return out


def nrs_label(nrs: float) -> str:
    if nrs < 0.5:
        return "none"
    if nrs < 3.0:
        return "mild"
    if nrs < 6.0:
        return "moderate"
    if nrs < 8.0:
        return "severe"
    return "very severe"


def fuse(aus: Mapping[str, float],
         vitals: Mapping[str, Optional[float]],
         baseline: Baseline,
         emotions: Optional[Mapping[str, float]] = None,
         face_quality: float = 1.0) -> PainReading:
    """Combine the facial and autonomic channels into one pain index.

    The autonomic channel is applied as a *modulation* around baseline rather
    than an additive score: with no facial pain evidence a racing heart alone
    must not read as pain, so the autonomic term scales what the face reports
    and can push it up by at most W_AUTONOMIC/W_FACIAL.
    """
    face = facial_pain(aus, emotions)
    auto = autonomic_pain(vitals, baseline)

    # Autonomic deviation from baseline in [-1, +1]. It modulates the facial
    # score through the headroom still available, f * (1 + k*d*(1-f)), which
    # has two properties the plain multiplier lacked: at f = 0 no amount of
    # tachycardia registers as pain, and the result approaches 1 without ever
    # clamping, so a strong episode keeps its resolution near the top of the
    # scale instead of flattening against the ceiling.
    auto_dev = (auto.score - 0.5) * 2.0 if auto.ready else 0.0
    f = face.corrected
    intensity = _clamp(f * (1.0 + (W_AUTONOMIC / W_FACIAL) * auto_dev * (1.0 - f)))

    # Confidence: how much we trust this reading. Good face tracking and a
    # settled baseline raise it; strong smile evidence lowers it, because that
    # is exactly where PSPI is least reliable.
    conf = _clamp(0.35 + 0.4 * _clamp(face_quality) + (0.25 if auto.ready else 0.0))
    conf = _clamp(conf * (1.0 - 0.5 * face.smile))

    nrs = intensity * NRS_MAX
    return PainReading(intensity=intensity, nrs=nrs, facial=face, autonomic=auto,
                       confidence=conf, triggered=False, label=nrs_label(nrs))
