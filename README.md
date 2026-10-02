# rPPG Lab

A research workbench for remote photoplethysmography: measure pulse from a webcam, compare eight open-source rPPG algorithms side by side, and export everything.

## Run it (VS Code)

```bash
cd rppg-lab
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python server.py
```

Open **http://localhost:8000**, choose **Camera**, press **Start**, allow camera access.
Or press F5 in VS Code and pick *rPPG Lab: run server*.

You can also open `static/index.html` directly (or with Live Server). Everything real-time runs in the browser; the page looks for the Python engine on `localhost:8000` and uses it when it's running.

The first camera run downloads the MediaPipe face-mesh (~4 MB) from jsDelivr and Google Storage, so the first load needs internet.

## What it measures

| Metric | How |
|---|---|
| Heart rate | 8 methods on a sliding window (5–30 s), FFT peak with parabolic interpolation, SNR-weighted median fusion |
| SNR | de Haan & Jeanne 2013 definition (f0 ± 0.1 Hz and 2f0 ± 0.2 Hz vs rest of 0.5–4 Hz) |
| Beats / IBI | HR-adaptive band-pass, refractory period, spurious-beat merge, 20% artefact rule |
| HRV | Mean IBI, SDNN, RMSSD, SDSD, pNN50, pNN20, SD1/SD2 (Poincaré), Baevsky stress index, LF, HF, LF/HF, LF n.u. |
| Respiration | Median of RIIV (baseline), RIAV (pulse amplitude) and RSA (tachogram) modulations |
| Perfusion index | Green channel AC/DC |
| SpO₂ ratio | Red/blue ratio-of-ratios. **Uncalibrated index**, not an SpO₂ %; needs a pulse-oximeter calibration for your camera |
| Quality | SNR, head motion (face-mesh centroid), illumination, face presence |

## Methods

GREEN (2008), ICA (2010), PCA (2011), CHROM (2013), PBV (2014), POS (2017), LGI (2018), OMIT (2023) — implemented both in the browser (`static/index.html`, `DSP` block) and in Python (`rppg_core.py`), cross-checked to agree within ~1 bpm on synthetic data.

ROIs: forehead + both cheeks from the MediaPipe 478-point face mesh (convex hulls), with an optional YCrCb skin mask. Falls back to a fixed face guide if the mesh can't load.

## Sources

- **Camera** — live, with optional exposure/white-balance lock (strongly recommended for research; auto-exposure injects low-frequency noise).
- **Video file** — processed at the file's own timeline, so results are reproducible.
- **Simulator** — synthetic subject with a known, drifting ground-truth HR, RSA, and injected motion artefacts. Shows the live error vs truth; use it to benchmark method robustness.

## Python engine

`server.py` (FastAPI, docs at `/docs`):

- `POST /api/analyze` — `{t, rgb, fs, primary}` → all 8 methods with Tarvainen detrending, scipy Butterworth, Welch spectra, full HRV + frequency domain.
- `POST /api/video` — upload a video (or use **Record 20 s clip** in the app) for offline analysis; optional deep model.

**Deep models**: `pip install open-rppg` enables FacePhys, PhysMamba, RhythmMamba, PhysFormer, TS-CAN, EfficientPhys, PhysNet and ME-flow/ME-chunk through the *Deep model* dropdown.

## Batch / offline

```bash
python analyze_video.py face.mp4 --primary CHROM --plot report.png --json report.json --csv trace.csv
python analyze_video.py face.mp4 --deep FacePhys.rlap
python analyze_video.py --synthetic        # self-test, no video needed
```

For benchmarking on public datasets (UBFC-rPPG, PURE, MMPD) run `analyze_video.py` over the videos and compare against the dataset's ground-truth PPG.

## Tips for clean signals

Diffuse front lighting, no flicker (avoid 50 Hz LED dimmers), camera at 30 fps, subject still and ~50–80 cm away, exposure locked. Use a 60 s window or longer for HRV.

## Disclaimer

Research tool only. Not a medical device; don't use it for diagnosis or treatment.
