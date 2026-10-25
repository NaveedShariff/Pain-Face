"""Build the ground-truth table from a local Delaware Pain Database copy.

The database's manual FACS coding and observer ratings are not redistributed
with this repository. Point PAINFACE_DELAWARE at your own OSF download and
this writes validation/delaware_truth.csv, which the scoring script consumes.
"""
import glob, os, warnings
from pathlib import Path
import pandas as pd
warnings.filterwarnings("ignore")

ROOT = Path(os.environ.get(
    "PAINFACE_DELAWARE",
    Path.home() / "Shariff/Research/PainFace/Dataset/2x8r5-osfstorage-archive"))
XL = ROOT / "Norming Data" / "DelawarePainDatabase_StimulusCharacterization_forOSF.xlsx"
if not XL.exists():
    raise SystemExit(f"Not found: {XL}\nSet PAINFACE_DELAWARE to your copy of the database.")

raw = pd.read_excel(XL, sheet_name="RawAUData_Facs_vs_OpenFace", header=None)
au_row, lab_row = raw.iloc[1], raw.iloc[2]
names = {}
for i in range(raw.shape[1]):
    a, l = str(au_row[i]).strip(), str(lab_row[i]).strip()
    names[i] = a if a.startswith("AU") else (l if l not in ("nan", "") else f"_{i}")
df = raw.iloc[3:].rename(columns=names).reset_index(drop=True)
df = df.loc[:, ~pd.Index(df.columns).duplicated()]

man = [c for c in df.columns if isinstance(c, str) and c.endswith("_m")]
of = [c for c in df.columns if isinstance(c, str) and c.endswith("_OF")]
keep = ["Target", "Expession_Highest", "Pain_Expression"] + man + of
df = df[keep]
df = df[df["Target"].notna() & (df["Target"].astype(str) != "nan")].copy()
for c in keep:
    if c not in ("Target", "Expession_Highest"):
        df[c] = pd.to_numeric(df[c], errors="coerce")

idx = {}
for pat in ("**/*.png", "**/*.jpg"):
    for p in glob.glob(str(ROOT / "Stimuli" / pat), recursive=True):
        idx.setdefault(Path(p).stem, []).append(p)

def pick(t):
    c = idx.get(str(t).strip(), [])
    return next((q for q in c if "Cropped and Standardized" in q), c[0] if c else None)

# stored relative to the database root so the table carries no local paths
df["path"] = df["Target"].map(lambda t: (lambda q: str(Path(q).relative_to(ROOT)) if q else None)(pick(t)))
Path("validation").mkdir(exist_ok=True)
df.to_csv("validation/delaware_truth.csv", index=False)
print(f"wrote validation/delaware_truth.csv  ({len(df)} rows, "
      f"{df['path'].notna().sum()} matched to images)")
