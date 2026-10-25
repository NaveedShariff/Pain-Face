"""Characterisation experiments: how the system behaves, measured not asserted.

These are not validation against human pain. They establish the operating
envelope of the implementation: where the pulse estimator breaks, how the
method bank compares, what the fusion does across its input range, and how
fast the detector runs.
"""
import json, sys, time, warnings
from pathlib import Path
import numpy as np
warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import rppg_core as core
from painface import fusion as F
from painface.vitals import VitalsBuffer, MIN_EFFECTIVE_FS

R = {}

# ---- 1. HR error vs measurement noise -----------------------------------
print("1. noise sweep")
noises = [0.0005, 0.001, 0.002, 0.004, 0.008, 0.016, 0.032]
rows = []
for nz in noises:
    errs, snrs = [], []
    for seed, hr in enumerate((54, 72, 96, 120)):
        t, rgb = core.synthetic_rgb(40, 30.0, hr=hr, rr=15, noise=nz, seed=seed + 1)
        r = core.analyze(rgb, 30.0, primary="POS", with_series=False)
        if r.get("fused_hr"):
            errs.append(abs(r["fused_hr"] - hr))
            s = [m["snr"] for m in r["methods"].values() if "snr" in m]
            if s: snrs.append(float(np.median(s)))
    rows.append({"noise": nz, "mae_bpm": float(np.mean(errs)) if errs else None,
                 "median_snr_db": float(np.mean(snrs)) if snrs else None})
R["noise_sweep"] = rows
for r in rows: print(f"   noise {r['noise']:.4f}  MAE {r['mae_bpm']:.2f} bpm  SNR {r['median_snr_db']:.1f} dB")

# ---- 2. HR error vs sampling rate (the aliasing boundary) ---------------
print("2. sampling-rate sweep")
rows = []
for fs in (30, 25, 20, 15, 12, 10, 8, 7, 6, 5, 4, 2):
    errs, accepted = [], 0
    for hr in (54, 72, 96, 120):
        vb = VitalsBuffer(window_s=30.0, fs=30.0, min_interval_s=0.0)
        t, rgb = core.synthetic_rgb(40, float(fs), hr=hr, rr=15)
        vb.extend(t.tolist(), rgb.T.tolist()); vb.analyze(force=True)
        got = vb.features()["hr"]
        if got is not None:
            accepted += 1; errs.append(abs(got - hr))
    rows.append({"fs": fs, "accepted": accepted, "of": 4,
                 "mae_bpm": float(np.mean(errs)) if errs else None})
R["sampling_sweep"] = rows
R["alias_threshold_hz"] = MIN_EFFECTIVE_FS
for r in rows:
    m = f"{r['mae_bpm']:.2f}" if r["mae_bpm"] is not None else "refused"
    print(f"   fs {r['fs']:>2} Hz  accepted {r['accepted']}/4  MAE {m}")

# ---- 3. per-method accuracy across the physiological range --------------
print("3. method bank")
hrs = [48, 60, 72, 84, 96, 110, 126, 144]
per = {m: [] for m in core.METHODS}
for hr in hrs:
    t, rgb = core.synthetic_rgb(40, 30.0, hr=hr, rr=15)
    r = core.analyze(rgb, 30.0, primary="POS", with_series=False)
    for m, v in r["methods"].items():
        if "hr" in v and v["hr"]: per[m].append(abs(v["hr"] - hr))
R["method_bank"] = [{"method": m, "mae_bpm": round(float(np.mean(v)), 3),
                     "max_err_bpm": round(float(np.max(v)), 3), "n": len(v)}
                    for m, v in per.items()]
for r in sorted(R["method_bank"], key=lambda x: x["mae_bpm"]):
    print(f"   {r['method']:6} MAE {r['mae_bpm']:.3f}  max {r['max_err_bpm']:.3f}")

# ---- 4. fusion response surface ----------------------------------------
print("4. fusion surface")
k = F.W_AUTONOMIC / F.W_FACIAL
grid = []
for f_ in np.linspace(0, 1, 21):
    for dev in (-1.0, -0.5, 0.0, 0.5, 1.0):
        grid.append({"facial": round(float(f_), 3), "auto_dev": dev,
                     "intensity": round(float(np.clip(f_ * (1 + k * dev * (1 - f_)), 0, 1)), 4)})
R["fusion_surface"] = grid
R["fusion_k"] = round(k, 4)
R["fusion_max"] = round(max(g["intensity"] for g in grid), 4)
R["fusion_zero_facial"] = sorted({g["intensity"] for g in grid if g["facial"] == 0.0})
print(f"   k={k:.4f}  max intensity {R['fusion_max']}  at facial=0: {R['fusion_zero_facial']}")

# ---- 5. episode trigger timing -----------------------------------------
print("5. trigger timing")
rows = []
STEP, ON_AT, OFF_AT = 0.05, 10.0, 25.0
for dwell, release in ((0.3, 0.8), (0.6, 1.5), (1.0, 2.5), (2.0, 4.0)):
    tr = F.Trigger(dwell_s=dwell, release_s=release)
    onset = offset = None
    for i in range(int(40 / STEP)):
        t = i * STEP
        score = 0.72 if ON_AT <= t < OFF_AT else 0.02
        was, now = tr.active, tr.update(score, t)
        if not was and now: onset = t
        if was and not now: offset = t
    rows.append({"dwell_s": dwell, "release_s": release,
                 "onset_latency_s": round(onset - ON_AT, 3) if onset else None,
                 "release_latency_s": round(offset - OFF_AT, 3) if offset else None,
                 "episodes": tr.episodes})
R["trigger_timing"] = rows
for r in rows:
    print(f"   dwell {r['dwell_s']}s release {r['release_s']}s -> onset +{r['onset_latency_s']}s  release +{r['release_latency_s']}s")

# ---- 6. detector throughput --------------------------------------------
print("6. detector throughput")
import cv2
from feat.utils.io import get_test_data_path
from painface.au import AUEngine
import os
bgr = cv2.imread(os.path.join(get_test_data_path(), "single_face.jpg"))
rows = []
for w in (960, 640, 480, 384, 320):
    eng = AUEngine(device="auto", width=w); eng.warm()
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    eng.analyze_frame(rgb)
    ts = []
    for _ in range(12):
        t0 = time.perf_counter(); eng.analyze_frame(rgb); ts.append(time.perf_counter() - t0)
    med = float(np.median(ts))
    rows.append({"width_px": w, "median_ms": round(med * 1000, 1), "fps": round(1 / med, 1),
                 "device": eng.device})
    print(f"   {w}px  {med*1000:.1f} ms  {1/med:.1f} fps")
R["throughput"] = rows

json.dump(R, open("validation/characterisation.json", "w"), indent=1)
print("\n-> validation/characterisation.json")
