#!/usr/bin/env python
"""
painface_cli.py — offline Pain-Face analysis of a recorded clip.

Examples
  python painface_cli.py clip.mp4
  python painface_cli.py clip.mp4 --every 3 --plot report.png --json report.json --csv trace.csv
  python painface_cli.py --synthetic            # self-test, no video needed

Runs the same engine the live app uses: Py-Feat action units per sampled
frame, the rPPG method bank over a sliding window, and the fusion that turns
both into a pain index — so a batch result and a live session are comparable.
"""
from __future__ import annotations

import argparse
import json
import sys

import numpy as np

from painface import fusion
from painface.au import AUEngine
from painface.pspi import AU_NAMES, PAIN_AUS
from painface.session import PainSession


def fmt(v, d=1):
    return "—" if v is None or (isinstance(v, float) and v != v) else f"{v:.{d}f}"


def synthetic_session(duration=60.0, step=0.2) -> PainSession:
    """Score a scripted pain episode without a camera, to prove the chain works."""
    import rppg_core as core

    baseline = fusion.Baseline(min_n=10)
    trigger = fusion.Trigger()
    session = PainSession(label="synthetic")
    rng = np.random.default_rng(3)

    def level(t):                       # calm, episode, calm
        return float(np.sin(np.pi * (t - 20) / 15)) if 20 <= t < 35 else 0.0

    for i in range(int(duration / step)):
        t = i * step
        p = max(level(t), 0.0)
        aus = {"AU04": 0.9 * p, "AU06": 0.3 * p, "AU07": 0.85 * p, "AU09": 0.7 * p,
               "AU10": 0.6 * p, "AU43": 0.5 * p, "AU25": 0.4 * p, "AU12": 0.02,
               "AU15": 0.2 * p, "AU17": 0.15 * p, "AU20": 0.1 * p, "AU23": 0.2 * p}
        aus = {k: float(np.clip(v + 0.01 * rng.standard_normal(), 0, 1)) for k, v in aus.items()}
        emotions = {"Neutral": 1 - p, "Sad": 0.5 * p, "Happy": 0.01}
        vit = {"hr": 70 + 26 * p, "rmssd": 45 - 26 * p, "sdnn": 55 - 24 * p,
               "lf_hf": 1.0 + 1.3 * p, "resp": 14 + 6 * p, "perfusion": 1.2 - 0.45 * p}
        if t < 18:
            baseline.add(vit)
        r = fusion.fuse(aus, vit, baseline, emotions, face_quality=0.95)
        on = trigger.update(r.intensity, t)
        session.add(t, r.as_dict(trigger, t), aus, emotions, vit, 0.95, on)
    return session


def report(session: PainSession, extra: dict | None = None) -> None:
    s = session.summary()
    print(f"\n  samples {s['samples']}   duration {fmt(s['duration_s'])} s")
    print(f"  peak pain   {fmt(s['nrs_peak'], 2)} / 10  at {fmt(s['nrs_peak_t'])} s")
    print(f"  mean pain   {fmt(s['nrs_mean'], 2)} / 10"
          f"   (while triggered {fmt(s['nrs_mean_while_triggered'], 2)})")
    print(f"  in pain     {fmt(s['time_in_pain_s'])} s  ({fmt(s['time_in_pain_pct'])} %)")
    print(f"  episodes    {s['episode_count']}")
    for e in s["episodes"]:
        print(f"    #{e['index']}  {fmt(e['start_t'])}–{fmt(e['end_t'])} s "
              f"({fmt(e['duration_s'])} s)  peak {fmt(e['peak_nrs'], 2)}  "
              f"mean {fmt(e['mean_nrs'], 2)}  [{' '.join(e['peak_aus']) or '—'}]")

    print("\n  pain AU prevalence (fraction of frames above 0.5)")
    for code in PAIN_AUS:
        v = s["pain_au_prevalence"].get(code, 0.0)
        if v:
            bar = "█" * int(round(v * 28))
            print(f"    {code}  {AU_NAMES.get(code, ''):<20} {v * 100:5.1f}%  {bar}")

    vm = s["vitals_mean"]
    if any(v is not None for v in vm.values()):
        print("\n  mean vitals")
        print(f"    HR {fmt(vm['hr'])} bpm   RMSSD {fmt(vm['rmssd'])} ms   "
              f"SDNN {fmt(vm['sdnn'])} ms   LF/HF {fmt(vm['lf_hf'], 2)}")
        print(f"    resp {fmt(vm['resp'])} br/min   perfusion {fmt(vm['perfusion'], 2)} %")
    if extra:
        for k, v in extra.items():
            print(f"  {k}: {v}")


def plot(session: PainSession, path: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    tl = session.timeline(("t", "nrs", "pspi", "corrected", "autonomic", "triggered"))
    t = tl["t"]
    fig, ax = plt.subplots(2, 1, figsize=(11, 6.4), sharex=True,
                           gridspec_kw={"height_ratios": [2, 1]})
    ax[0].fill_between(t, tl["nrs"], color="#e0566f", alpha=.18)
    ax[0].plot(t, tl["nrs"], color="#e0566f", lw=2, label="fused pain (NRS)")
    ax[0].plot(t, [(v or 0) * 10 for v in tl["corrected"]], color="#f0943c", lw=1.3,
               label="facial, smile-corrected ×10")
    ax[0].plot(t, [(v or 0) * 10 / 16 for v in tl["pspi"]], color="#9aa8bd", lw=1,
               ls="--", label="raw PSPI (0–16 on the 0–10 axis)")
    for e in session.episodes:
        ax[0].axvspan(e.start_t, e.end_t or t[-1], color="#e03a5a", alpha=.10)
    ax[0].set_ylabel("pain  0–10"); ax[0].set_ylim(0, 10.5)
    ax[0].legend(fontsize=8, loc="upper right"); ax[0].grid(alpha=.2)
    ax[0].set_title("Pain-Face — multimodal pain timeline")

    ax[1].plot(t, tl["autonomic"], color="#a07cf0", lw=1.4, label="autonomic (0.5 = baseline)")
    ax[1].axhline(.5, color="#9aa8bd", lw=.8, ls=":")
    ax[1].set_ylim(0, 1); ax[1].set_xlabel("time (s)"); ax[1].set_ylabel("arousal")
    ax[1].legend(fontsize=8); ax[1].grid(alpha=.2)
    fig.tight_layout(); fig.savefig(path, dpi=140)
    print(f"  plot  -> {path}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video", nargs="?", help="Path to a face video (mp4/mov/avi/webm)")
    ap.add_argument("--every", type=int, default=5, help="Analyse every Nth frame (default 5)")
    ap.add_argument("--primary", default="POS", help="rPPG waveform method")
    ap.add_argument("--max-seconds", type=float, default=None)
    ap.add_argument("--device", default="auto", help="auto | mps | cuda | cpu")
    ap.add_argument("--synthetic", action="store_true", help="Self-test without a video")
    ap.add_argument("--plot", help="Save a PNG timeline")
    ap.add_argument("--json", help="Save the full session as JSON")
    ap.add_argument("--csv", help="Save a tidy per-sample CSV")
    a = ap.parse_args()

    if a.synthetic:
        print("Source: synthetic (scripted 15 s pain episode)")
        session = synthetic_session()
        report(session)
    elif a.video:
        import painface.server as srv
        srv.engine = AUEngine(device=a.device)
        print(f"Analysing {a.video} … (every {a.every} frames)")
        session, out = srv.analyze_video_session(
            a.video, au_every=a.every, primary=a.primary, max_seconds=a.max_seconds,
            progress=lambda f: print(f"\r  {f * 100:5.1f}%", end="", flush=True))
        print(f"\rSource: {a.video}        ")
        print(f"  frames analysed {out['frames_analyzed']}  with a face {out['frames_with_face']}")
        if out.get("vitals_error"):
            print(f"  rPPG unavailable: {out['vitals_error']}")
        elif out.get("vitals"):
            print(f"  fused HR {fmt((out['vitals'] or {}).get('fused_hr'))} bpm over the whole clip")
        report(session)
    else:
        ap.print_help()
        sys.exit(1)

    if a.plot:
        plot(session, a.plot)
    if a.json:
        with open(a.json, "w") as f:
            f.write(session.to_json())
        print(f"  json  -> {a.json}")
    if a.csv:
        with open(a.csv, "w") as f:
            f.write(session.to_csv())
        print(f"  csv   -> {a.csv}")


if __name__ == "__main__":
    main()
