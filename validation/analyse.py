"""Agreement with human FACS coders, and correlation with observer pain ratings."""
import json, warnings
import numpy as np, pandas as pd
from scipy import stats
from sklearn.metrics import f1_score, cohen_kappa_score, roc_auc_score
warnings.filterwarnings("ignore")

d = pd.read_csv("validation/delaware_scored.csv")
d = d[d["ok"] == True].copy()
THR = 0.5                      # the threshold the live system uses
out = {"n_images": int(len(d)), "au_threshold": THR}

# ---- 1. per-AU agreement with human coders: ours vs OpenFace -------------
common = ["01","02","04","05","06","07","09","10","12","14","15","17","20","23","25","26","28"]
rows = []
for c in common:
    m, pf, of = d[f"AU{c}_m"], d[f"AU{c}_pf"], d[f"AU{c}_OF"]
    ok = m.notna() & pf.notna()
    y, yp = m[ok].astype(int), (pf[ok] >= THR).astype(int)
    if y.nunique() < 2:
        continue
    r = {"AU": f"AU{c}", "prevalence": round(float(y.mean()), 3),
         "painface_acc": round(float((y == yp).mean()), 3),
         "painface_f1": round(float(f1_score(y, yp, zero_division=0)), 3),
         "painface_kappa": round(float(cohen_kappa_score(y, yp)), 3)}
    ok2 = m.notna() & of.notna()
    if ok2.sum() > 5:
        y2, yo = m[ok2].astype(int), (of[ok2] >= THR).astype(int)
        r.update({"openface_acc": round(float((y2 == yo).mean()), 3),
                  "openface_f1": round(float(f1_score(y2, yo, zero_division=0)), 3),
                  "openface_kappa": round(float(cohen_kappa_score(y2, yo)), 3)})
    rows.append(r)
au = pd.DataFrame(rows)
out["per_au"] = rows
pain_aus = au[au["AU"].isin(["AU04","AU06","AU07","AU09","AU10"])]
out["mean_f1_all"] = round(float(au["painface_f1"].mean()), 3)
out["mean_f1_painAUs"] = round(float(pain_aus["painface_f1"].mean()), 3)
out["mean_f1_openface_all"] = round(float(au["openface_f1"].mean()), 3)
out["mean_kappa_all"] = round(float(au["painface_kappa"].mean()), 3)
out["mean_kappa_openface_all"] = round(float(au["openface_kappa"].mean()), 3)

# ---- 2. PSPI against observer pain ratings ------------------------------
g = d[d["pain_rating"].notna()]
for name, col in (("pspi_raw", "pspi_raw"), ("corrected", "corrected")):
    r_p = stats.pearsonr(g[col], g["pain_rating"])
    r_s = stats.spearmanr(g[col], g["pain_rating"])
    out[f"{name}_vs_rating"] = {
        "pearson_r": round(float(r_p[0]), 3), "pearson_p": float(f"{r_p[1]:.3g}"),
        "spearman_rho": round(float(r_s[0]), 3), "spearman_p": float(f"{r_s[1]:.3g}"), "n": int(len(g))}

# ---- 3. does the correction suppress non-pain expressions? --------------
by = d.groupby(d["expression"].str.strip()).agg(
    n=("Target", "size"), pspi_raw=("pspi_raw", "mean"),
    pspi_frac=("pspi_frac", "mean"), corrected=("corrected", "mean"),
    smile=("smile", "mean"), rating=("pain_rating", "mean")).round(3)
out["by_expression"] = by.reset_index().to_dict("records")

ispain = (d["expression"].str.strip() == "pain").astype(int)
out["separation_auc"] = {
    "pspi_raw": round(float(roc_auc_score(ispain, d["pspi_frac"])), 3),
    "corrected": round(float(roc_auc_score(ispain, d["corrected"])), 3)}

happy = d[d["expression"].str.strip() == "happy"]
painr = d[d["expression"].str.strip() == "pain"]
out["happy_vs_pain"] = {
    "n_happy": int(len(happy)), "n_pain": int(len(painr)),
    "happy_pspi_raw": round(float(happy["pspi_raw"].mean()), 2),
    "happy_pspi_pct": round(float(happy["pspi_frac"].mean() * 100), 1),
    "happy_corrected_pct": round(float(happy["corrected"].mean() * 100), 1),
    "pain_pspi_raw": round(float(painr["pspi_raw"].mean()), 2),
    "pain_pspi_pct": round(float(painr["pspi_frac"].mean() * 100), 1),
    "pain_corrected_pct": round(float(painr["corrected"].mean() * 100), 1)}

json.dump(out, open("validation/results.json", "w"), indent=1)

# ---- report -------------------------------------------------------------
print(f"n = {out['n_images']} images, AU threshold {THR}\n")
print("=== 1. AU agreement with human FACS coders ===")
print(au.to_string(index=False))
print(f"\n  mean F1  — Pain-Face {out['mean_f1_all']:.3f}   OpenFace {out['mean_f1_openface_all']:.3f}")
print(f"  mean kappa — Pain-Face {out['mean_kappa_all']:.3f}   OpenFace {out['mean_kappa_openface_all']:.3f}")
print(f"  mean F1 on the five PSPI AUs: {out['mean_f1_painAUs']:.3f}")

print("\n=== 2. PSPI vs observer pain rating ===")
for k in ("pspi_raw_vs_rating", "corrected_vs_rating"):
    v = out[k]
    print(f"  {k:24} r = {v['pearson_r']:+.3f} (p={v['pearson_p']:.3g})   rho = {v['spearman_rho']:+.3f}  n={v['n']}")

print("\n=== 3. Specificity: mean score by expression ===")
print(by.to_string())
print(f"\n  pain-vs-rest AUC — raw PSPI {out['separation_auc']['pspi_raw']:.3f}   corrected {out['separation_auc']['corrected']:.3f}")
h = out["happy_vs_pain"]
print(f"\n  happy faces (n={h['n_happy']}): raw PSPI {h['happy_pspi_raw']}/16 = {h['happy_pspi_pct']}%  ->  corrected {h['happy_corrected_pct']}%")
print(f"  pain  faces (n={h['n_pain']}): raw PSPI {h['pain_pspi_raw']}/16 = {h['pain_pspi_pct']}%  ->  corrected {h['pain_corrected_pct']}%")
