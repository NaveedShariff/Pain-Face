"""Figure: the rPPG signal chain, from raw skin colour to heart rate."""
import warnings, numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
warnings.filterwarnings("ignore")
import sys; sys.path.insert(0, ".")
import rppg_core as core

S1, S2, S3, S4 = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
SURFACE, INK, INK2, GRIDC = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "font.size": 8.5, "axes.titlesize": 9, "axes.labelsize": 8.5,
    "axes.edgecolor": "#c9c8c3", "axes.labelcolor": INK2, "text.color": INK,
    "xtick.color": INK2, "ytick.color": INK2, "grid.color": GRIDC,
    "axes.spines.top": False, "axes.spines.right": False, "legend.frameon": False,
    "lines.linewidth": 1.6,
})

FS, HR = 30.0, 72.0
t, rgb = core.synthetic_rgb(20.0, FS, hr=HR, rr=15, noise=0.0025, seed=4)
norm = core._normalize(rgb)
raw_pos = core.METHODS["POS"](rgb, FS)
bvp = core.bandpass(core.detrend_tarvainen(raw_pos), FS, *core.HR_BAND)
f, p = core.spectrum(bvp, FS)
hr_est, f0 = core.hr_from_spectrum(f, p)
snr = core.snr_db(f, p, f0)
pk, pt = core.detect_peaks(bvp, FS, hr_est)

fig, ax = plt.subplots(3, 1, figsize=(6.4, 6.3))

# (a) raw spatially-averaged skin colour
for c, col, lab in zip(rgb, (S1, S2, S3), ("R channel", "G channel", "B channel")):
    ax[0].plot(t, c, color=col, lw=1.3, label=lab)
    ax[0].annotate(lab.split()[0], (t[-1], c[-1]), xytext=(5, -2),
                   textcoords="offset points", fontsize=7.5, color=col, weight="600")
ax[0].set_title("(a)  Spatially averaged skin colour, three ROIs combined", loc="left", weight="600")
ax[0].set_ylim(85, 222)
ax[0].set_ylabel("intensity (0-255)"); ax[0].set_xlabel("time (s)")
ax[0].legend(fontsize=7, ncol=3, loc="upper center"); ax[0].grid(axis="y", alpha=.9)

# (b) extracted waveform + detected beats
ax[1].plot(t[:len(bvp)], bvp, color=S1, lw=1.5, label="BVP after POS, detrend, band-pass")
ax[1].plot(pt, bvp[pk], "o", ms=4.5, mfc=SURFACE, mec=S2, mew=1.5, label=f"detected beats (n={len(pk)})")
if len(pt) > 2:
    i = len(pt) // 2
    lo = float(np.min(bvp)); ax[1].set_ylim(lo * 1.45, float(np.max(bvp)) * 1.18)
    y = lo * 1.26
    ax[1].annotate("", xy=(pt[i], y), xytext=(pt[i+1], y),
                   arrowprops=dict(arrowstyle="<->", color=INK2, lw=1))
    ax[1].text((pt[i] + pt[i+1]) / 2, y * 1.22, "IBI", ha="center", fontsize=7.5, color=INK2)
ax[1].set_title("(b)  Recovered blood-volume pulse and beat detection", loc="left", weight="600")
ax[1].set_ylabel("a.u."); ax[1].set_xlabel("time (s)")
ax[1].legend(fontsize=7, loc="lower right"); ax[1].grid(axis="y", alpha=.9)

# (c) spectrum, f0 and the second harmonic
m = (f >= 0.4) & (f <= 4.2)
ax[2].fill_between(f[m], p[m] / p[m].max(), color=S1, alpha=.16)
ax[2].plot(f[m], p[m] / p[m].max(), color=S1, lw=1.5)
for x, lab, col in ((f0, f"$f_0$ = {f0:.3f} Hz\n{hr_est:.1f} bpm", S2), (2 * f0, "$2f_0$", S4)):
    ax[2].axvline(x, color=col, ls="--", lw=1.3)
    ax[2].annotate(lab, (x, 0.95), xytext=(7, 0), textcoords="offset points",
                   fontsize=7.6, color=col, va="top", weight="600")
for lo, hi in ((f0 - .1, f0 + .1), (2 * f0 - .2, 2 * f0 + .2)):
    ax[2].axvspan(lo, hi, color=S2, alpha=.10)
ax[2].text(3.0, 0.62, f"SNR = {snr:.1f} dB\n(shaded = signal bands)", fontsize=7.4, color=INK2)
ax[2].set_title("(c)  Power spectrum: heart rate from the dominant in-band peak", loc="left", weight="600")
ax[2].set_ylabel("normalised power"); ax[2].set_xlabel("frequency (Hz)")
ax[2].grid(axis="y", alpha=.9)

fig.tight_layout()
fig.savefig("validation/figs/f9_pipeline.svg", bbox_inches="tight")
fig.savefig("validation/figs/f9_pipeline.png", dpi=190, bbox_inches="tight")
print(f"ground truth {HR} bpm -> estimated {hr_est:.2f} bpm | SNR {snr:.1f} dB | beats {len(pk)}")
print("-> validation/figs/f9_pipeline.svg")
