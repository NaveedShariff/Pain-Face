"""Figures for the technical report. Palette validated for CVD separation."""
import json, warnings
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import stats
warnings.filterwarnings("ignore")

S1, S2, S3, S4 = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
SURFACE, INK, INK2, GRIDC = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "font.size": 9, "axes.titlesize": 10, "axes.labelsize": 9,
    "axes.edgecolor": "#c9c8c3", "axes.labelcolor": INK2, "text.color": INK,
    "xtick.color": INK2, "ytick.color": INK2, "grid.color": GRIDC, "grid.linewidth": .8,
    "axes.spines.top": False, "axes.spines.right": False, "legend.frameon": False,
    "lines.linewidth": 2, "lines.markersize": 6,
})
def finish(ax, title, xl, yl, legend=True):
    ax.set_title(title, loc="left", color=INK, pad=10, fontweight="600")
    ax.set_xlabel(xl); ax.set_ylabel(yl); ax.grid(axis="y", alpha=.9); ax.set_axisbelow(True)
    if legend and ax.get_legend_handles_labels()[0]: ax.legend(loc="best", fontsize=8)
def save(fig, name):
    fig.tight_layout(); fig.savefig(f"validation/figs/{name}.svg", bbox_inches="tight"); fig.savefig(f"validation/figs/{name}.png", dpi=190, bbox_inches="tight"); plt.close(fig)
    print("  ->", name)

C = json.load(open("validation/characterisation.json"))
V = json.load(open("validation/results.json"))
d = pd.read_csv("validation/delaware_scored.csv"); d = d[d["ok"] == True]

# F1 — PSPI vs observer pain rating
fig, ax = plt.subplots(figsize=(6.2, 3.9))
for col, c, lab in (("pspi_frac", S1, "raw PSPI"), ("corrected", S2, "smile-corrected")):
    ax.scatter(d["pain_rating"], d[col] * 100, s=26, c=c, alpha=.72,
               edgecolors=SURFACE, linewidths=.8, label=lab)
    sl, ic, r, p, _ = stats.linregress(d["pain_rating"], d[col] * 100)
    xs = np.linspace(d["pain_rating"].min(), d["pain_rating"].max(), 20)
    ax.plot(xs, sl * xs + ic, c=c, lw=2, alpha=.95)
ax.text(.02, .97, f"raw  r = {V['pspi_raw_vs_rating']['pearson_r']:+.3f}\ncorr r = {V['corrected_vs_rating']['pearson_r']:+.3f}   n = {len(d)}",
        transform=ax.transAxes, va="top", fontsize=8.5, color=INK2, family="monospace")
finish(ax, "Facial pain score vs observer pain rating (Delaware, n=95)",
       "mean observer pain rating", "score (% of scale)")
save(fig, "f1_pspi_vs_rating")

# F2 — per-AU agreement with human coders
au = pd.DataFrame(V["per_au"]).sort_values("painface_f1", ascending=False)
fig, ax = plt.subplots(figsize=(7.4, 3.9))
x = np.arange(len(au)); w = .38
ax.bar(x - w/2, au["painface_f1"], w, color=S1, label="Pain-Face (Py-Feat)")
ax.bar(x + w/2, au["openface_f1"], w, color=S2, label="OpenFace")
for i, v in enumerate(au["painface_f1"]):
    ax.text(i - w/2, v + .02, f"{v:.2f}", ha="center", fontsize=6.4, color=INK2)
pain = {"AU04","AU06","AU07","AU09","AU10"}
ax.set_xticks(x); ax.set_xticklabels(
    [f"{a}*" if a in pain else a for a in au["AU"]], rotation=45, ha="right", fontsize=7.6)
ax.set_ylim(0, 1.06)
finish(ax, "Agreement with manual FACS coding, F1 (* = PSPI term)", "", "F1")
save(fig, "f2_au_agreement")

# F3 — the specificity result
by = pd.DataFrame(V["by_expression"]).sort_values("pspi_frac", ascending=False)
by = by[by["n"] >= 5]
fig, ax = plt.subplots(figsize=(6.6, 3.9))
x = np.arange(len(by)); w = .38
ax.bar(x - w/2, by["pspi_frac"] * 100, w, color=S1, label="raw PSPI")
ax.bar(x + w/2, by["corrected"] * 100, w, color=S2, label="smile-corrected")
for i, (a, b) in enumerate(zip(by["pspi_frac"] * 100, by["corrected"] * 100)):
    ax.text(i - w/2, a + 1.2, f"{a:.0f}", ha="center", fontsize=7, color=INK2)
    ax.text(i + w/2, b + 1.2, f"{b:.0f}", ha="center", fontsize=7,
            color=S2 if b < a - 8 else INK2, fontweight="600" if b < a - 8 else "normal")
ax.set_xticks(x); ax.set_xticklabels([f"{e}\nn={n}" for e, n in zip(by["expression"], by["n"])], fontsize=8)
ax.set_ylim(0, 100)
finish(ax, "Specificity: score by expression category", "", "score (% of scale)")
save(fig, "f3_specificity")

# F4 — noise
ns = pd.DataFrame(C["noise_sweep"])
fig, ax = plt.subplots(figsize=(6.2, 3.6))
ax.plot(ns["median_snr_db"], ns["mae_bpm"], "o-", color=S1, label="fused HR error")
for sn, mae in zip(ns["median_snr_db"], ns["mae_bpm"]):
    if mae > .5: ax.annotate(f"{mae:.1f}", (sn, mae), textcoords="offset points",
                             xytext=(0, 8), ha="center", fontsize=7.5, color=INK2)
ax.axhline(1.0, color=INK2, lw=1, ls=":"); ax.text(ns["median_snr_db"].min(), 1.4, "1 bpm", fontsize=7.5, color=INK2)
ax.invert_xaxis()
finish(ax, "Pulse-rate error against signal quality", "median SNR (dB)  → worse", "MAE (bpm)", legend=False)
save(fig, "f4_noise")

# F5 — sampling rate and the refusal boundary
ss = pd.DataFrame(C["sampling_sweep"]).sort_values("fs")
fig, ax = plt.subplots(figsize=(6.2, 3.6))
acc = ss[ss["mae_bpm"].notna()]; ref = ss[ss["mae_bpm"].isna()]
ax.axvspan(ss["fs"].min() - .5, C["alias_threshold_hz"], color=S2, alpha=.10)
ax.plot(acc["fs"], acc["mae_bpm"], "o-", color=S1, label="reported (MAE)")
ax.scatter(ref["fs"], [0] * len(ref), marker="x", s=46, c=S2, label="refused — no value reported")
ax.axvline(C["alias_threshold_hz"], color=S2, lw=1.6, ls="--")
ax.text(C["alias_threshold_hz"] + .4, ax.get_ylim()[1] * .72,
        f"abstention\nthreshold\n{C['alias_threshold_hz']} Hz", fontsize=7.6, color=S2)
finish(ax, "Pulse estimation against frame rate, with the abstention boundary",
       "effective sampling rate (Hz)", "MAE (bpm)")
save(fig, "f5_sampling")

# F6 — method bank
mb = pd.DataFrame(C["method_bank"]).sort_values("mae_bpm")
fig, ax = plt.subplots(figsize=(6.2, 3.3))
ax.barh(mb["method"], mb["mae_bpm"], color=S1, height=.62)
for i, v in enumerate(mb["mae_bpm"]): ax.text(v + .003, i, f"{v:.3f}", va="center", fontsize=7.6, color=INK2)
ax.invert_yaxis(); ax.grid(axis="x", alpha=.9); ax.grid(axis="y", alpha=0)
finish(ax, "Method bank on synthetic signals, 48–144 bpm", "MAE (bpm)", "", legend=False)
save(fig, "f6_methods")

# F7 — fusion response
fs_ = pd.DataFrame(C["fusion_surface"])
fig, ax = plt.subplots(figsize=(6.2, 3.6))
for dev, c, lab in ((-1.0, S3, "autonomic −1 (calm)"), (0.0, INK2, "at baseline"), (1.0, S2, "autonomic +1 (aroused)")):
    g = fs_[fs_["auto_dev"] == dev]
    ax.plot(g["facial"] * 100, g["intensity"] * 100, color=c, label=lab,
            lw=2.4 if dev == 0 else 2, ls="--" if dev == 0 else "-")
ax.scatter([0], [0], s=70, facecolor=SURFACE, edgecolor=S2, zorder=5, linewidths=2)
ax.annotate("facial evidence is necessary:\nall curves meet at zero", (0, 0),
            textcoords="offset points", xytext=(16, 24), fontsize=7.8, color=INK2)
finish(ax, "Fusion response — autonomic state modulates, never originates",
       "facial pain evidence (%)", "fused intensity (%)")
save(fig, "f7_fusion")

# F8 — throughput
tp = pd.DataFrame(C["throughput"]).sort_values("width_px")
fig, ax = plt.subplots(figsize=(6.2, 3.3))
ax.bar(tp["width_px"].astype(str), tp["fps"], color=S1, width=.6)
for i, (f_, ms) in enumerate(zip(tp["fps"], tp["median_ms"])):
    ax.text(i, f_ + .18, f"{f_:.1f} fps\n{ms:.0f} ms", ha="center", fontsize=7.4, color=INK2)
ax.set_ylim(0, max(tp["fps"]) * 1.28)
finish(ax, f"Action-unit detector throughput ({tp['device'].iloc[0]}, median of 12)",
       "detection width (px)", "frames per second", legend=False)
save(fig, "f8_throughput")
print("done")
