"""
pspi.py — pain-relevant facial action units and the PSPI score.

PSPI (Prkachin & Solomon Pain Intensity, Prkachin & Solomon 2008) is the
standard frame-level facial pain metric. It is a sum of four FACS components:

    PSPI = AU4 + max(AU6, AU7) + max(AU9, AU10) + AU43

  AU4   brow lowerer        0-5
  AU6   cheek raiser        0-5  }  orbital tightening, scored as the max
  AU7   lid tightener       0-5  }
  AU9   nose wrinkler       0-5  }  levator contraction, scored as the max
  AU10  upper lip raiser    0-5  }
  AU43  eye closure         0-1  (present / absent in the original scale)

so the score runs 0-16. Py-Feat reports each AU as an occurrence probability
in [0, 1] rather than an A-E intensity, so `pspi()` rescales: the 0-5 terms
are multiplied by 5 and AU43 is used directly. That makes our PSPI
commensurate with the published 0-16 range but it is a probability-derived
estimate, not a certified FACS coder's intensity score — see `pspi_raw()` if
you have true 0-5 intensities from a human coder.

Beyond PSPI we expose the wider pain-AU set reported by Kunz & Lautenbacher
(2014), who found pain expressions cluster into brow lowering, orbital
tightening, levator contraction and open mouth. The mouth group (AU25/26/27)
is informative but also moves with speech, so it is reported separately and
is deliberately not part of PSPI.
"""
from __future__ import annotations

from typing import Dict, Iterable, Mapping

# PSPI components. Each entry: (label, AU codes combined by max, max points)
PSPI_TERMS: tuple[tuple[str, tuple[str, ...], float], ...] = (
    ("brow_lowering",       ("AU04",),          5.0),
    ("orbital_tightening",  ("AU06", "AU07"),   5.0),
    ("levator_contraction", ("AU09", "AU10"),   5.0),
    ("eye_closure",         ("AU43",),          1.0),
)

PSPI_MAX = sum(term[2] for term in PSPI_TERMS)          # 16.0

# The 20 AUs Py-Feat 2.x actually reports. Note AU27 (mouth stretch) is NOT in
# the set, so the open-mouth pain component rests on AU25/AU26 alone.
DETECTED_AUS = ("AU01", "AU02", "AU04", "AU05", "AU06", "AU07", "AU09", "AU10",
                "AU11", "AU12", "AU14", "AU15", "AU17", "AU20", "AU23", "AU24",
                "AU25", "AU26", "AU28", "AU43")

# AUs that carry pain information but sit outside PSPI.
MOUTH_AUS = ("AU25", "AU26")                             # lips part / jaw drop
ADJUNCT_AUS = ("AU12", "AU20", "AU23", "AU24")           # lip corner pull, stretch, tightener, pressor

# Every AU in the pain literature we surface in the UI, in FACS order.
PAIN_AUS = ("AU04", "AU06", "AU07", "AU09", "AU10", "AU43") + MOUTH_AUS + ADJUNCT_AUS

AU_NAMES: Dict[str, str] = {
    "AU01": "Inner brow raiser",   "AU02": "Outer brow raiser",
    "AU04": "Brow lowerer",        "AU05": "Upper lid raiser",
    "AU06": "Cheek raiser",        "AU07": "Lid tightener",
    "AU09": "Nose wrinkler",       "AU10": "Upper lip raiser",
    "AU11": "Nasolabial deepener", "AU12": "Lip corner puller",
    "AU14": "Dimpler",             "AU15": "Lip corner depressor",
    "AU17": "Chin raiser",         "AU20": "Lip stretcher",
    "AU23": "Lip tightener",       "AU24": "Lip pressor",
    "AU25": "Lips part",           "AU26": "Jaw drop",
    "AU28": "Lip suck",
    "AU43": "Eye closure",
}


def canon(au: str) -> str:
    """Normalize an AU label to zero-padded form: 'AU4', 'au04', '4' -> 'AU04'."""
    s = str(au).strip().upper()
    if s.startswith("AU"):
        s = s[2:]
    s = s.split("_")[0]           # tolerate py-feat's 'AU04_r' style suffixes
    return f"AU{int(s):02d}" if s.isdigit() else f"AU{s}"


def normalize_aus(aus: Mapping[str, float]) -> Dict[str, float]:
    """Canonicalize keys and clamp probabilities into [0, 1], dropping NaNs."""
    out: Dict[str, float] = {}
    for k, v in aus.items():
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if f != f:                                    # NaN
            continue
        out[canon(k)] = min(max(f, 0.0), 1.0)
    return out


def _term_value(aus: Mapping[str, float], codes: Iterable[str]) -> float:
    """Max probability across the AUs of one PSPI term; 0 if none were detected."""
    vals = [aus[c] for c in codes if c in aus]
    return max(vals) if vals else 0.0


def pspi_terms(aus: Mapping[str, float]) -> Dict[str, float]:
    """The four PSPI terms in score points, keyed by label."""
    a = normalize_aus(aus)
    return {label: _term_value(a, codes) * points for label, codes, points in PSPI_TERMS}


def pspi(aus: Mapping[str, float]) -> float:
    """PSPI in [0, 16] from Py-Feat AU probabilities."""
    return float(sum(pspi_terms(aus).values()))


def pspi_raw(intensities: Mapping[str, float]) -> float:
    """PSPI from true FACS 0-5 intensities (AU43 as 0-1), for coded datasets."""
    a = {canon(k): float(v) for k, v in intensities.items()}
    total = 0.0
    for _, codes, points in PSPI_TERMS:
        vals = [a[c] for c in codes if c in a]
        if vals:
            total += min(max(max(vals), 0.0), points)
    return float(total)


def pspi_fraction(aus: Mapping[str, float]) -> float:
    """PSPI expressed in [0, 1] — the facial channel of the fusion model."""
    return pspi(aus) / PSPI_MAX


def mouth_activity(aus: Mapping[str, float]) -> float:
    """Open-mouth pain component in [0, 1]; moves with speech, so kept separate."""
    return _term_value(normalize_aus(aus), MOUTH_AUS)


def active_pain_aus(aus: Mapping[str, float], threshold: float = 0.5) -> list[str]:
    """Which pain AUs are currently above `threshold`, in FACS order."""
    a = normalize_aus(aus)
    return [c for c in PAIN_AUS if a.get(c, 0.0) >= threshold]
