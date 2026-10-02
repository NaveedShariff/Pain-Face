"""
analyze_video.py — offline rPPG analysis of a recorded video (research batch use).

Examples
  python analyze_video.py face.mp4
  python analyze_video.py face.mp4 --primary CHROM --plot report.png --json report.json
  python analyze_video.py face.mp4 --deep FacePhys.rlap      # needs: pip install open-rppg
  python analyze_video.py --synthetic                        # sanity-check without a video
"""
import argparse
import json
import sys

import numpy as np

import rppg_core as core


def fmt(v, d=1):
    return "—" if v is None else f"{v:.{d}f}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video", nargs="?", help="Path to a face video (mp4/avi/webm/mov)")
    ap.add_argument("--primary", default="POS", choices=list(core.METHODS))
    ap.add_argument("--fs", type=float, default=30.0, help="Resampling rate (Hz)")
    ap.add_argument("--max-seconds", type=float, default=None)
    ap.add_argument("--plot", help="Save a figure (PNG) with BVP, spectrum and tachogram")
    ap.add_argument("--json", help="Save full results as JSON")
    ap.add_argument("--csv", help="Save the extracted RGB trace as CSV")
    ap.add_argument("--deep", help="Also run an open-rppg deep model, e.g. FacePhys.rlap")
    ap.add_argument("--synthetic", action="store_true", help="Use a synthetic 72 bpm signal")
    a = ap.parse_args()

    if a.synthetic:
        t, rgb = core.synthetic_rgb(60, a.fs, hr=72, rr=15)
        src = "synthetic (72 bpm, 15 br/min)"
    elif a.video:
        import rppg_video
        print(f"Extracting skin RGB from {a.video} …")
        t, rgb_raw, fps = rppg_video.extract_rgb(
            a.video, max_seconds=a.max_seconds,
            progress=lambda p: print(f"\r  {p*100:5.1f}%", end="", flush=True))
        print(f"\r  done — {len(t)} face frames @ {fps:.1f} fps")
        t, rgb = core.resample_uniform(t, rgb_raw, a.fs)
        src = a.video
    else:
        ap.print_help()
        sys.exit(1)

    res = core.analyze(rgb, a.fs, primary=a.primary)
    print(f"\nSource: {src}   duration {res['duration_s']:.1f} s\n")
    print(f"{'Method':8} {'HR (FFT)':>9} {'HR (Welch)':>11} {'SNR dB':>8}")
    for m, r in res["methods"].items():
        if "error" in r:
            print(f"{m:8}  error: {r['error']}")
        else:
            print(f"{m:8} {fmt(r['hr']):>9} {fmt(r['hr_welch']):>11} {fmt(r['snr']):>8}")
    print(f"\nFused HR (SNR-weighted median): {fmt(res['fused_hr'])} bpm")
    h = res.get("hrv", {})
    print(f"HRV [{res['primary']}]: beats {h.get('n_beats')}, SDNN {fmt(h.get('sdnn_ms'))} ms, "
          f"RMSSD {fmt(h.get('rmssd_ms'))} ms, pNN50 {fmt(h.get('pnn50_pct'))}%, "
          f"LF/HF {fmt(h.get('lf_hf'), 2)}, stress index {fmt(h.get('stress_index'))}")
    rsp = res.get("respiration", {})
    print(f"Respiration: {fmt(rsp.get('fused'))} br/min  "
          f"(RIIV {fmt(rsp.get('riiv'))}, RIAV {fmt(rsp.get('riav'))}, RSA {fmt(rsp.get('rsa'))})")

    if a.deep:
        from server import run_deep
        print(f"\nRunning deep model {a.deep} …")
        res["deep"] = core._clean(run_deep(a.video, a.deep))
        print(json.dumps({k: v for k, v in res["deep"].items() if k != "hrv"}, indent=2))

    if a.csv:
        tt = np.arange(rgb.shape[1]) / a.fs
        np.savetxt(a.csv, np.column_stack([tt, rgb.T]), delimiter=",",
                   header="t_s,R,G,B", comments="", fmt="%.5f")
        print(f"Saved trace → {a.csv}")
    if a.json:
        with open(a.json, "w") as f:
            json.dump(res, f, indent=2)
        print(f"Saved results → {a.json}")
    if a.plot:
        plot(res, a.plot, a.fs)
        print(f"Saved figure → {a.plot}")


def plot(res, path, fs):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    s = res["series"]
    fig, ax = plt.subplots(3, 1, figsize=(10, 8), constrained_layout=True)
    bvp = np.array(s["bvp"])
    tb = np.arange(len(bvp)) / fs
    ax[0].plot(tb, bvp, color="#b3261e", lw=1.2)
    off = res["duration_s"] - tb[-1] - 1 / fs
    pk = [p - off for p in s["peaks_t"] if p - off >= 0]
    ax[0].plot(pk, np.interp(pk, tb, bvp), "o", ms=4, color="#1f2937")
    ax[0].set(title=f"BVP ({res['primary']}) — last 20 s", xlabel="s")
    ax[1].plot(np.array(s["welch_f"]) * 60, s["welch_p"], color="#0f766e")
    ax[1].axvline(res["fused_hr"] or 0, ls="--", color="#b3261e")
    ax[1].set(title=f"Welch spectrum — fused HR {fmt(res['fused_hr'])} bpm", xlabel="bpm")
    h = res.get("hrv", {})
    if h.get("ibi_ms"):
        ax[2].plot(h["ibi_t"], h["ibi_ms"], ".-", color="#1f2937")
    ax[2].set(title=f"Tachogram — RMSSD {fmt(h.get('rmssd_ms'))} ms", xlabel="s", ylabel="IBI ms")
    fig.savefig(path, dpi=130)


if __name__ == "__main__":
    main()
