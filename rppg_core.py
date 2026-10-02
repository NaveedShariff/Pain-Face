"""
rppg_core.py — open-source remote photoplethysmography (rPPG) signal processing.

Every algorithm here is an unsupervised method from the published literature.
Input everywhere is a (3, N) array of spatially-averaged R, G, B skin traces
sampled uniformly at `fs` Hz.

Methods
-------
GREEN   Verkruysse, Svaasand & Nelson, Optics Express 2008
ICA     Poh, McDuff & Picard, Optics Express 2010 (FastICA on RGB)
PCA     Lewandowska et al., FedCSIS 2011
CHROM   de Haan & Jeanne, IEEE TBME 2013
PBV     de Haan & van Leest, Physiol. Meas. 2014
POS     Wang, den Brinker, Stuijk & de Haan, IEEE TBME 2017
LGI     Pilz, Krajewski, Zaunseder & Blazek, CVPR-W 2018
OMIT    Casado & López, Expert Systems with Applications 2023

Post-processing: smoothness-priors detrending (Tarvainen 2002), zero-phase
Butterworth band-pass, spectral HR with parabolic peak interpolation, SNR
(de Haan 2013 definition), peak-based IBI, time/frequency/non-linear HRV
(Task Force 1996), respiration from RSA / amplitude / baseline modulation.
"""
from __future__ import annotations

import numpy as np
from scipy import signal as sps
from scipy import sparse
from scipy.sparse.linalg import spsolve
from scipy.interpolate import CubicSpline

HR_BAND = (0.7, 3.5)       # 42–210 bpm
RESP_BAND = (0.1, 0.5)     # 6–30 breaths/min
EPS = 1e-9


# ---------------------------------------------------------------- utilities
def resample_uniform(t: np.ndarray, x: np.ndarray, fs: float = 30.0):
    """Resample irregular webcam timestamps (seconds) onto a uniform grid."""
    t = np.asarray(t, float)
    x = np.atleast_2d(np.asarray(x, float))
    if x.shape[0] != 3 and x.shape[1] == 3:
        x = x.T
    order = np.argsort(t)
    t, x = t[order], x[:, order]
    keep = np.concatenate([[True], np.diff(t) > 0])
    t, x = t[keep], x[:, keep]
    tu = np.arange(t[0], t[-1], 1.0 / fs)
    xu = np.vstack([np.interp(tu, t, c) for c in x])
    return tu, xu


def detrend_tarvainen(z: np.ndarray, lam: float = 100.0) -> np.ndarray:
    """Smoothness-priors detrending (Tarvainen et al., IEEE TBME 2002)."""
    z = np.asarray(z, float)
    n = len(z)
    if n < 5:
        return z - z.mean()
    I = sparse.eye(n, format="csc")
    D2 = sparse.diags([1.0, -2.0, 1.0], [0, 1, 2], shape=(n - 2, n), format="csc")
    trend = spsolve(I + lam ** 2 * (D2.T @ D2), z)
    return z - trend


def bandpass(x: np.ndarray, fs: float, lo: float, hi: float, order: int = 3):
    hi = min(hi, 0.45 * fs)
    sos = sps.butter(order, [lo, hi], btype="band", fs=fs, output="sos")
    padlen = min(len(x) - 1, 3 * (2 * len(sos) + 1) * 2)
    return sps.sosfiltfilt(sos, x, padlen=padlen)


def _normalize(rgb: np.ndarray) -> np.ndarray:
    return rgb / (rgb.mean(axis=1, keepdims=True) + EPS)


def _overlap_add(rgb: np.ndarray, fs: float, win_sec: float, fn) -> np.ndarray:
    """Run `fn` on sliding windows of temporally-normalized RGB and overlap-add."""
    n = rgb.shape[1]
    L = max(int(round(win_sec * fs)), 8)
    if n <= L:
        return fn(_normalize(rgb))
    h = np.zeros(n)
    w = np.hanning(L)
    step = max(L // 2, 1)
    for s in range(0, n - L + 1, step):
        seg = fn(_normalize(rgb[:, s:s + L]))
        seg = seg - seg.mean()
        h[s:s + L] += seg * w
    return h


def _peak_ratio(x: np.ndarray, fs: float) -> float:
    f, p = sps.periodogram(x - x.mean(), fs, nfft=max(4096, len(x)))
    band = (f >= HR_BAND[0]) & (f <= HR_BAND[1])
    return p[band].max() / (p[band].sum() + EPS) if band.any() else 0.0


# ---------------------------------------------------------------- methods
def m_green(rgb, fs):
    return rgb[1] / (rgb[1].mean() + EPS)


def m_chrom(rgb, fs):
    def f(c):
        xs = 3 * c[0] - 2 * c[1]
        ys = 1.5 * c[0] + c[1] - 1.5 * c[2]
        return xs - (xs.std() / (ys.std() + EPS)) * ys
    return _overlap_add(rgb, fs, 1.6, f)


def m_pos(rgb, fs):
    def f(c):
        s1 = c[1] - c[2]
        s2 = c[1] + c[2] - 2 * c[0]
        return s1 + (s1.std() / (s2.std() + EPS)) * s2
    return _overlap_add(rgb, fs, 1.6, f)


def m_lgi(rgb, fs):
    X = _normalize(rgb)
    U, _, _ = np.linalg.svd(X, full_matrices=False)
    u = U[:, :1]
    return ((np.eye(3) - u @ u.T) @ X)[1]


def m_omit(rgb, fs):
    X = _normalize(rgb)
    Q, _ = np.linalg.qr(X)
    q = Q[:, :1]
    return ((np.eye(3) - q @ q.T) @ X)[1]


def m_pbv(rgb, fs):
    C = _normalize(rgb)
    pbv = C.std(axis=1)
    pbv = pbv / (np.sqrt((pbv ** 2).sum()) + EPS)
    Cz = C - C.mean(axis=1, keepdims=True)
    Q = Cz @ Cz.T
    W = np.linalg.solve(Q + EPS * np.eye(3), pbv)
    return (Cz.T @ W) / (pbv @ W + EPS)


def m_pca(rgb, fs):
    X = _normalize(rgb)
    X = X - X.mean(axis=1, keepdims=True)
    _, vecs = np.linalg.eigh(np.cov(X))
    comps = [vecs[:, i] @ X for i in range(3)]
    return max(comps, key=lambda c: _peak_ratio(c, fs))


def _fastica(X: np.ndarray, n_iter: int = 400, seed: int = 0) -> np.ndarray:
    """Symmetric FastICA (logcosh) — numpy only, deterministic."""
    X = X - X.mean(axis=1, keepdims=True)
    d, E = np.linalg.eigh(np.cov(X))
    K = E @ np.diag(1.0 / np.sqrt(np.maximum(d, EPS))) @ E.T
    Z = K @ X
    rng = np.random.default_rng(seed)
    W = np.linalg.qr(rng.standard_normal((3, 3)))[0]
    for _ in range(n_iter):
        WX = W @ Z
        g, gp = np.tanh(WX), 1 - np.tanh(WX) ** 2
        W1 = (g @ Z.T) / Z.shape[1] - np.diag(gp.mean(axis=1)) @ W
        s, u = np.linalg.eigh(W1 @ W1.T)
        W1 = u @ np.diag(1.0 / np.sqrt(np.maximum(s, EPS))) @ u.T @ W1
        if np.max(np.abs(np.abs(np.diag(W1 @ W.T)) - 1)) < 1e-6:
            W = W1
            break
        W = W1
    return W @ Z


def m_ica(rgb, fs):
    X = _normalize(rgb)
    X = np.vstack([detrend_tarvainen(c) for c in X])
    S = _fastica(X)
    return max(S, key=lambda c: _peak_ratio(c, fs))


METHODS = {
    "GREEN": m_green, "ICA": m_ica, "PCA": m_pca, "CHROM": m_chrom,
    "PBV": m_pbv, "POS": m_pos, "LGI": m_lgi, "OMIT": m_omit,
}


# ---------------------------------------------------------------- estimators
def spectrum(x: np.ndarray, fs: float, nfft: int = 4096):
    x = x - x.mean()
    f, p = sps.periodogram(x * np.hanning(len(x)), fs, nfft=max(nfft, len(x)))
    return f, p


def welch_spectrum(x: np.ndarray, fs: float):
    nper = min(len(x), int(fs * 8))
    return sps.welch(x - x.mean(), fs, nperseg=nper, noverlap=nper // 2,
                     nfft=max(2048, nper))


def hr_from_spectrum(f, p, band=HR_BAND):
    m = (f >= band[0]) & (f <= band[1])
    if not m.any():
        return float("nan"), float("nan")
    idx = np.flatnonzero(m)
    k = idx[np.argmax(p[m])]
    # parabolic interpolation for sub-bin resolution
    if 0 < k < len(p) - 1:
        a, b, c = np.log(p[k - 1] + EPS), np.log(p[k] + EPS), np.log(p[k + 1] + EPS)
        delta = 0.5 * (a - c) / (a - 2 * b + c + EPS)
        f0 = f[k] + delta * (f[1] - f[0])
    else:
        f0 = f[k]
    return float(f0 * 60.0), float(f0)


def snr_db(f, p, f0):
    """de Haan & Jeanne 2013: power in f0±0.1 Hz and 2f0±0.2 Hz vs rest of 0.5–4 Hz."""
    if not np.isfinite(f0):
        return float("nan")
    band = (f >= 0.5) & (f <= 4.0)
    sig = band & ((np.abs(f - f0) <= 0.1) | (np.abs(f - 2 * f0) <= 0.2))
    noise = band & ~sig
    return float(10 * np.log10((p[sig].sum() + EPS) / (p[noise].sum() + EPS)))


def detect_peaks(bvp: np.ndarray, fs: float, hr_bpm: float | None = None):
    """Beat detection on an HR-adaptive band (removes the dicrotic 2nd harmonic)."""
    x = bvp
    if hr_bpm and np.isfinite(hr_bpm):
        f0 = hr_bpm / 60.0
        try:
            x = bandpass(bvp, fs, max(0.5, 0.6 * f0), min(1.6 * f0, 0.45 * fs), order=2)
        except ValueError:
            pass
        min_dist = 0.6 * 60.0 / hr_bpm
    else:
        min_dist = 0.33
    x = (x - x.mean()) / (x.std() + EPS)
    pk, _ = sps.find_peaks(x, distance=max(int(min_dist * fs), 1), prominence=0.35)
    # drop spurious beats: any pair closer than 70% of the median IBI keeps the taller one
    if len(pk) > 4:
        med = np.median(np.diff(pk))
        keep = [pk[0]]
        for k in pk[1:]:
            if k - keep[-1] < 0.7 * med:
                if x[k] > x[keep[-1]]:
                    keep[-1] = k
            else:
                keep.append(k)
        pk = np.array(keep)
    # parabolic refinement of each peak time
    t = pk.astype(float)
    for i, k in enumerate(pk):
        if 0 < k < len(x) - 1:
            a, b, c = x[k - 1], x[k], x[k + 1]
            t[i] = k + 0.5 * (a - c) / (a - 2 * b + c + EPS)
    return pk, t / fs


def clean_ibi(ibi_s: np.ndarray):
    """Physiological range + 20% deviation from rolling median (standard artefact rule)."""
    ibi = np.asarray(ibi_s, float)
    ok = (ibi > 0.28) & (ibi < 1.6)
    if ok.sum() >= 3:
        med = np.median(ibi[ok])
        ok &= np.abs(ibi - med) < 0.2 * med
    return ibi, ok


def hrv_metrics(peak_t: np.ndarray):
    out = {"n_beats": int(len(peak_t))}
    if len(peak_t) < 4:
        return out
    ibi, ok = clean_ibi(np.diff(peak_t))
    tt = peak_t[1:][ok]
    rr = ibi[ok] * 1000.0
    out["artifact_pct"] = float(100 * (1 - ok.mean()))
    if len(rr) < 3:
        return out
    d = np.diff(rr)
    out.update({
        "mean_ibi_ms": float(rr.mean()),
        "hr_from_ibi": float(60000.0 / rr.mean()),
        "sdnn_ms": float(rr.std(ddof=1)),
        "rmssd_ms": float(np.sqrt(np.mean(d ** 2))),
        "sdsd_ms": float(d.std(ddof=1)) if len(d) > 1 else float("nan"),
        "pnn50_pct": float(100 * np.mean(np.abs(d) > 50)),
        "pnn20_pct": float(100 * np.mean(np.abs(d) > 20)),
    })
    sd1 = np.sqrt(0.5) * d.std(ddof=1) if len(d) > 1 else float("nan")
    sd2 = np.sqrt(max(2 * rr.var(ddof=1) - sd1 ** 2, 0)) if np.isfinite(sd1) else float("nan")
    out.update({"sd1_ms": float(sd1), "sd2_ms": float(sd2),
                "sd1_sd2": float(sd1 / sd2) if sd2 else float("nan")})
    # Baevsky stress index: AMo / (2 * Mo * MxDMn), 50 ms bins, seconds
    bins = np.arange(rr.min(), rr.max() + 50, 50)
    if len(bins) > 1:
        hist, edges = np.histogram(rr, bins)
        mo = (edges[hist.argmax()] + 25) / 1000.0
        amo = 100.0 * hist.max() / len(rr)
        mxdmn = (rr.max() - rr.min()) / 1000.0
        out["stress_index"] = float(amo / (2 * mo * mxdmn)) if mxdmn > 0 else float("nan")
    # frequency domain on 4 Hz resampled tachogram (needs ~60 s to be meaningful)
    if len(rr) >= 8 and tt[-1] - tt[0] >= 20:
        fs_i = 4.0
        ti = np.arange(tt[0], tt[-1], 1 / fs_i)
        ri = CubicSpline(tt, rr)(ti)
        f, p = sps.welch(ri - ri.mean(), fs_i, nperseg=min(len(ri), 256), nfft=1024)
        def bp(a, b):
            m = (f >= a) & (f < b)
            return float(np.trapezoid(p[m], f[m])) if m.sum() > 1 else 0.0
        vlf, lf, hf = bp(0.0033, 0.04), bp(0.04, 0.15), bp(0.15, 0.4)
        out.update({"vlf_ms2": vlf, "lf_ms2": lf, "hf_ms2": hf,
                    "lf_hf": float(lf / hf) if hf > 0 else float("nan"),
                    "lf_nu": float(100 * lf / (lf + hf)) if lf + hf > 0 else float("nan"),
                    "hf_nu": float(100 * hf / (lf + hf)) if lf + hf > 0 else float("nan")})
        m = (f >= RESP_BAND[0]) & (f <= RESP_BAND[1])
        if m.any():
            out["resp_rsa_bpm"] = float(f[m][p[m].argmax()] * 60)
    out["ibi_ms"] = [float(v) for v in rr]
    out["ibi_t"] = [float(v) for v in tt]
    return out


def respiration(bvp: np.ndarray, raw_green: np.ndarray, fs: float, peak_idx):
    """Three respiratory-induced modulations of the rPPG signal; median-fused."""
    est = {}
    dur = len(bvp) / fs
    if dur < 15:
        return est
    # RIIV: baseline (intensity) modulation
    g = detrend_tarvainen(raw_green / (raw_green.mean() + EPS), lam=300)
    try:
        riiv = bandpass(g, fs, *RESP_BAND, order=2)
        f, p = welch_spectrum(riiv, fs)
        est["riiv"], _ = hr_from_spectrum(f, p, RESP_BAND)
    except ValueError:
        pass
    # RIAV: pulse amplitude modulation
    if len(peak_idx) >= 8:
        tp = peak_idx / fs
        amp = bvp[peak_idx]
        ti = np.arange(tp[0], tp[-1], 0.25)
        if len(ti) > 16:
            ai = np.interp(ti, tp, amp)
            f, p = sps.welch(ai - ai.mean(), 4.0, nperseg=min(len(ai), 128), nfft=1024)
            m = (f >= RESP_BAND[0]) & (f <= RESP_BAND[1])
            est["riav"] = float(f[m][p[m].argmax()] * 60)
    vals = [v for v in est.values() if np.isfinite(v)]
    if vals:
        est["fused"] = float(np.median(vals))
    return est


def spo2_ratio(rgb: np.ndarray, fs: float):
    """Ratio-of-ratios (AC/DC red)/(AC/DC blue). Uncalibrated research index only."""
    ac = []
    for c in (rgb[0], rgb[2]):
        dc = c.mean()
        try:
            a = bandpass(c / (dc + EPS), fs, *HR_BAND).std()
        except ValueError:
            a = np.nan
        ac.append(a)
    return float(ac[0] / (ac[1] + EPS))


def fuse_hr(results: dict):
    """SNR-weighted median across methods."""
    pts = [(r["hr"], max(r["snr"], -10) + 10) for r in results.values()
           if np.isfinite(r.get("hr", np.nan)) and np.isfinite(r.get("snr", np.nan))]
    if not pts:
        return float("nan")
    pts.sort()
    w = np.array([p[1] for p in pts]) + 1e-3
    cw = np.cumsum(w) / w.sum()
    return float(pts[int(np.searchsorted(cw, 0.5))][0])


# ---------------------------------------------------------------- pipeline
def _require_finite(x: np.ndarray, what: str) -> np.ndarray:
    """Reject a non-finite signal with a message naming the culprit."""
    if not np.isfinite(x).all():
        bad = int((~np.isfinite(x)).sum())
        raise ValueError(f"{what} has {bad}/{x.size} non-finite samples")
    return x


def _eval_method(name: str, rgb: np.ndarray, fs: float) -> np.ndarray:
    """Run one extraction method and validate its output.

    Flags, not values, are ignored here: some BLAS backends (notably Apple
    Accelerate on arm64) leave the divide/overflow/invalid status flags set
    after a matmul even when every element of the result is finite, and NumPy
    then surfaces that as a RuntimeWarning. Trusting those flags made ICA,
    PCA, PBV, LGI and OMIT report errors on perfectly good signals, so we
    silence them and judge the result on its actual values instead.
    """
    with np.errstate(all="ignore"):
        raw = np.asarray(METHODS[name](rgb, fs), dtype=float)
    if raw.ndim != 1 or raw.size == 0:
        raise ValueError(f"expected a 1-D signal, got shape {raw.shape}")
    return _require_finite(raw, "extracted signal")


def analyze(rgb: np.ndarray, fs: float, methods=None, primary: str = "POS",
            with_series: bool = True) -> dict:
    """Full analysis of a uniformly-sampled (3, N) RGB window."""
    rgb = np.asarray(rgb, float)
    methods = methods or list(METHODS)
    per = {}
    series = {}
    for name in methods:
        try:
            raw = _eval_method(name, rgb, fs)
            with np.errstate(all="ignore"):  # see _eval_method
                bvp = _require_finite(bandpass(detrend_tarvainen(raw), fs, *HR_BAND),
                                      "band-passed signal")
                f, p = spectrum(bvp, fs)
                hr, f0 = hr_from_spectrum(f, p)
                fw, pw = welch_spectrum(bvp, fs)
                hr_w, _ = hr_from_spectrum(fw, pw)
            per[name] = {"hr": hr, "hr_welch": hr_w, "snr": snr_db(f, p, f0)}
            series[name] = (bvp, f, p)
        except Exception as e:  # keep the other methods alive
            per[name] = {"error": str(e)}
    fused = fuse_hr(per)
    prim = primary if primary in series else next(iter(series), None)
    out = {"fs": fs, "duration_s": rgb.shape[1] / fs, "methods": per,
           "fused_hr": fused, "primary": prim}
    if prim:
        bvp, f, p = series[prim]
        pk, pt = detect_peaks(bvp, fs, per[prim]["hr"])
        out["hrv"] = hrv_metrics(pt)
        out["respiration"] = respiration(bvp, rgb[1], fs, pk)
        rsa = out["hrv"].get("resp_rsa_bpm")
        if rsa is not None and np.isfinite(rsa):
            out["respiration"]["rsa"] = rsa
        vals = [v for k, v in out["respiration"].items() if k != "fused" and np.isfinite(v)]
        if vals:
            out["respiration"]["fused"] = float(np.median(vals))
        out["spo2_ratio_uncalibrated"] = spo2_ratio(rgb, fs)
        g = rgb[1]
        try:
            out["perfusion_index_pct"] = float(100 * bandpass(g / g.mean(), fs, *HR_BAND).std() * 2)
        except ValueError:
            pass
        if with_series:
            fw, pw = welch_spectrum(bvp, fs)
            m = (fw >= 0.5) & (fw <= 4.0)
            out["series"] = {
                "bvp": bvp[-int(fs * 20):].round(5).tolist(),
                "welch_f": fw[m].round(4).tolist(),
                "welch_p": (pw[m] / (pw[m].max() + EPS)).round(5).tolist(),
                "peaks_t": pt.round(4).tolist(),
            }
    return _clean(out)


def _clean(o):
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, np.ndarray):
        return _clean(o.tolist())
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (float, np.floating)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, np.integer):
        return int(o)
    return o


# ---------------------------------------------------------------- synthetic
def synthetic_rgb(duration=60.0, fs=30.0, hr=72.0, rr=15.0, noise=0.002, seed=1):
    """Synthetic skin trace with RSA, respiration baseline and pulse in the
    physiologically correct colour direction (strongest in green)."""
    rng = np.random.default_rng(seed)
    t = np.arange(0, duration, 1 / fs)
    resp = np.sin(2 * np.pi * rr / 60 * t)
    inst_hr = hr / 60 * (1 + 0.05 * resp)            # RSA
    phase = 2 * np.pi * np.cumsum(inst_hr) / fs
    pulse = np.sin(phase) + 0.35 * np.sin(2 * phase - 0.8)
    direction = np.array([0.33, 0.77, 0.53])          # normalized PBV signature
    base = np.array([180.0, 120.0, 95.0])
    illum = 1 + 0.004 * resp + 0.003 * np.sin(2 * np.pi * 0.05 * t)
    rgb = base[:, None] * illum * (1 + 0.004 * direction[:, None] * pulse)
    rgb += rng.normal(0, noise, rgb.shape) * base[:, None]
    return t, rgb
