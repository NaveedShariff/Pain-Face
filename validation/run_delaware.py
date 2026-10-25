"""Score the Delaware Pain Database stills with Pain-Face's facial channel.

Ground truth: manual FACS coding by human coders (binary AU presence) and
observer pain-intensity ratings, both shipped with the database. OpenFace's
codes for the same images come with it too, so the comparison is three-way.
Still images, so only the facial channel is exercised here.
"""
import json, os, sys, warnings
from pathlib import Path
import numpy as np, pandas as pd, cv2
warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from painface.au import AUEngine
from painface import fusion as F
from painface import pspi as P

ROOT_DB = True
ROOT = os.environ.get("PAINFACE_DELAWARE",
    str(Path.home() / "Shariff/Research/PainFace/Dataset/2x8r5-osfstorage-archive"))
if not Path("validation/delaware_truth.csv").exists():
    raise SystemExit(
        "validation/delaware_truth.csv is missing. It is derived from the Delaware\n"
        "Pain Database and is not redistributed here. Build it from your own copy:\n"
        "  PAINFACE_DELAWARE=/path/to/2x8r5-osfstorage-archive python validation/build_truth.py")
df = pd.read_csv("validation/delaware_truth.csv")
df = df[df["path"].notna()].reset_index(drop=True)
eng = AUEngine(device="auto", width=480)
assert eng.warm(), eng.init_error

rows = []
for i, r in df.iterrows():
    bgr = cv2.imread(str(Path(ROOT) / r["path"]))
    if bgr is None:
        continue
    res = eng.analyze_frame(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
    if not res.ok:
        rows.append({"Target": r["Target"], "ok": False}); continue
    fp = F.facial_pain(res.aus, res.emotions)
    out = {"Target": r["Target"], "ok": True,
           "expression": str(r["Expession_Highest"]).strip(),
           "pain_rating": r["Pain_Expression"],
           "pspi_raw": fp.pspi, "pspi_frac": fp.pspi_fraction,
           "corrected": fp.corrected, "smile": fp.smile,
           "quality": res.quality}
    for code, v in res.aus.items():
        out[f"{code}_pf"] = v
    for k, v in (res.emotions or {}).items():
        out[f"emo_{k}"] = v
    rows.append(out)
    if (i + 1) % 25 == 0:
        print(f"  {i+1}/{len(df)}", flush=True)

pred = pd.DataFrame(rows)
merged = df.merge(pred, on="Target", how="inner")
merged.to_csv("validation/delaware_scored.csv", index=False)
print(f"scored {pred['ok'].sum()}/{len(df)} images -> validation/delaware_scored.csv")
print("detector:", {k: v for k, v in eng.status().items() if k in ("device", "frames", "avg_detect_ms")})
