# Pain-Face

A multimodal pain-intensity workbench. It reads the face with **Py-Feat** — 20 facial
action units, 7 emotions, 68 landmarks, head pose, gaze and 52 blendshapes — measures
the pulse from the same video with an 8-method **rPPG** bank, and fuses the two into a
single pain index on the familiar 0–10 scale. The reading is gated on the pain action
units: it appears when the face shows them and latches into an episode while they hold.

> **Not a medical device.** It estimates observable pain *behaviour*, not what a person
> feels. Do not use it for diagnosis, triage or treatment. See [Limits](#limits).

---

## Run it

Python **3.11+** is required (py-feat 2.x needs it). On macOS, xgboost needs the OpenMP
runtime, which py-feat imports at load time:

```bash
brew install libomp
```

```bash
python3.11 -m venv .venv311
source .venv311/bin/activate          # Windows: .venv311\Scripts\activate
pip install -r requirements.txt
python -m painface.server
```

Open **http://localhost:8000**, press **Start**, allow camera access. The first run
downloads the Py-Feat model weights (~300 MB) from Hugging Face and takes a minute;
after that the detector warms in about two seconds.

No camera? Pick **Simulator** — it scripts a pain episode with the canonical AU pattern
and a matching autonomic response, and the engine scores it through exactly the same
pipeline as a live face.

---

## What it measures

### Facial — PSPI

**PSPI** (Prkachin & Solomon Pain Intensity) is the standard frame-level facial pain
metric, a sum of four FACS components scored 0–16:

```
PSPI = AU4 + max(AU6, AU7) + max(AU9, AU10) + AU43
```

| Term | AUs | Points | Meaning |
|---|---|---|---|
| Brow lowering | AU4 | 0–5 | brow lowerer |
| Orbital tightening | AU6, AU7 | 0–5 | cheek raiser / lid tightener |
| Levator contraction | AU9, AU10 | 0–5 | nose wrinkler / upper lip raiser |
| Eye closure | AU43 | 0–1 | eyes closed |

Py-Feat reports occurrence probabilities rather than FACS 0–5 intensities, so the 0–5
terms are rescaled. `pspi_raw()` takes true coder intensities if you have them.

### The smile problem, and what this does about it

PSPI is not pain-*specific*. AU6 and AU10 are also smile components, so **a broad grin
scores about 7/16 on raw PSPI** — on Py-Feat's own bundled sample face, a 99 %-confident
*happy* expression, raw PSPI reads 7.3.

Pain is separated from enjoyment by what is *absent* — AU12, the lip corner puller — and
by the brow: pain lowers it, happiness does not. Pain-Face keeps the literal PSPI for
comparability with the literature and derives a **corrected** score alongside it that
discounts the shared terms in proportion to smile evidence. The same face drops from
45.9 % to 13.7 %. Both numbers are shown; neither is hidden.

### Autonomic — rPPG

Pain drives sympathetic activation. Each feature is scored against a **per-subject
baseline** captured during a calm period, because absolute heart rate says nothing about
pain while a 20 bpm rise above *this person's* rest does.

| Feature | Direction under pain |
|---|---|
| Heart rate | up |
| RMSSD, SDNN | down (parasympathetic withdrawal) |
| LF/HF | up |
| Respiration rate | up |
| Perfusion index | down (vasoconstriction) |

Methods: GREEN (2008), ICA (2010), PCA (2011), CHROM (2013), PBV (2014), POS (2017),
LGI (2018), OMIT (2023), fused by SNR-weighted median, with Tarvainen detrending, Welch
spectra and full time- and frequency-domain HRV.

### Fusion

```
intensity = facial × (1 + k · autonomic_deviation · (1 − facial))
```

Two properties this buys, both covered by tests:

- **Facial evidence is necessary.** At `facial = 0` no amount of tachycardia registers
  as pain — a neutral face at 130 bpm scores 0.2/10. Arousal corroborates; it never
  creates a reading.
- **It cannot saturate.** Modulation moves through the headroom that remains, so a
  severe episode keeps its resolution near the top of the scale instead of pinning flat
  at 10.

A **trigger** latches an episode with hysteresis — it must hold above the threshold for
a dwell time to fire, and fall below a lower bound for a release time to let go — so a
momentary grimace does not start an episode and a blink does not end one.

---

## The app

| Panel | Shows |
|---|---|
| Pain intensity | 0–10 gauge, band label, trigger state, facial / autonomic / confidence split |
| PSPI | the four terms stacked out of 16, raw vs corrected, smile and open-mouth evidence |
| Action units | all 20 AUs live, the 12 pain-relevant ones highlighted as they fire |
| Capture | video with landmarks, rPPG regions and a face box tinted by pain band |
| rPPG vitals | fused HR, RMSSD, SDNN, LF/HF, Baevsky stress index, respiration, perfusion, SpO₂ ratio |
| Pain timeline | fused NRS, corrected and raw PSPI, autonomic trace, episodes shaded |
| Episodes | onset, duration, peak and mean NRS, and which AUs were firing at the peak |
| Method bank | per-method HR and SNR for all eight algorithms |

Baseline calibration, session recording, and JSON / CSV export are in **Protocol**.
Exports come from the engine's own full-rate record, not the page's display buffer.

---

## Architecture

The browser runs two streams over one WebSocket, at their own natural rates:

- **Colour, every frame (~30 Hz).** Mean skin RGB from the forehead and both cheeks,
  taken from the MediaPipe mesh with a YCrCb skin gate. Inter-beat intervals need every
  frame.
- **Frames, a few times a second.** A 480 px JPEG for Py-Feat, which sustains about
  17 fps on Apple MPS. Frames arriving while a detection is in flight are **dropped, not
  queued** — stale action units are worse than fewer of them.

```
painface/
  pspi.py      pain AU vocabulary and the PSPI score
  au.py        Py-Feat wrapper — lazy load, NCHW tensor path, face quality
  vitals.py    rolling rPPG buffer, autonomic feature reduction, Nyquist guard
  fusion.py    facial + autonomic fusion, baseline, trigger hysteresis
  session.py   recording, episode statistics, JSON/CSV export
  server.py    FastAPI + /ws/live
static/painface.html    the whole front end
painface_cli.py         offline batch analysis
```

### Refusals it makes on purpose

- **Sampling too slow.** The pulse band runs to 3.5 Hz, so a trace arriving under 7.7 Hz
  aliases into it and produces a confident, wrong heart rate. Browsers throttle hidden
  tabs to about 1 fps. Pain-Face measures the arrival rate and **withholds HR and HRV**
  with a reason rather than printing a number the data cannot support. The facial
  channel is unaffected and keeps working.
- **HRV before 30 s.** RMSSD and SDNN are noise on short windows, so they are not shown
  and not fed to the baseline until the window is long enough.
- **No face.** Py-Feat returns a row of NaNs rather than nothing when there is no face;
  that case is detected and reported instead of being scored as a neutral expression.

---

## Offline

```bash
python painface_cli.py clip.mp4 --every 3 --plot report.png --json report.json --csv trace.csv
python painface_cli.py --synthetic        # self-test, no video or camera needed
```

Prints peak and mean pain, every episode with its peak AUs, pain-AU prevalence and mean
vitals; `--plot` writes the pain timeline with episodes shaded.

`POST /api/video` does the same over HTTP. Interactive API docs at `/docs`.

---

## Tests

```bash
pytest                   # 76 tests
pytest -m "not slow"     # 58, skipping anything that loads a model
```

They pin the behaviour that matters: PSPI arithmetic against hand-worked values, the
smile correction on a real Py-Feat detection, the fusion invariants above, trigger
hysteresis including a clock that jumps backwards, heart-rate recovery at 54/72/96/120
bpm, the aliasing refusal, and the full WebSocket protocol.

---

## Limits

- **Observable behaviour, not experience.** People mask pain, and stoicism reads as
  absence. A low score is not evidence that someone is comfortable.
- **PSPI is not pain-specific.** The correction here reduces the smile false positive;
  it does not eliminate confusion with disgust, effort or concentration, which share
  AU4, AU9 and AU10.
- **Autonomic signs are not pain-specific either.** Exercise, anxiety, caffeine and
  temperature all move heart rate and HRV. That is why they only modulate.
- **No clinical validation.** The index is not calibrated against a validated
  observational pain scale on any patient population, and the 0–10 output shares the
  shape of a numeric rating scale, not its meaning.
- **rPPG is fragile.** It needs diffuse flicker-free light, a still subject and locked
  exposure. Motion and auto-exposure inject noise straight into the pulse band.
- **Demographic performance is unmeasured here.** Both the AU models and rPPG are known
  to vary with skin tone and lighting; nothing in this repo quantifies that for your
  camera or your subjects.

Measure a baseline per subject, keep sessions long enough for HRV, and treat the number
as one observation among others.

---

## Credits

[Py-Feat](https://py-feat.org/) for the facial expression models. PSPI is Prkachin &
Solomon (2008); the AU structure of pain expressions follows Kunz & Lautenbacher (2014).
The rPPG method bank implements the eight published algorithms cited above.
