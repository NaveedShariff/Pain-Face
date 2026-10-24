#set document(
  title: "Pain-Face: A Multimodal Platform Combining Facial Action-Unit Analysis with Remote Photoplethysmography for Automatic Pain Assessment",
  author: "Mohammed Naveed Shariff",
)
#set page(
  paper: "a4",
  margin: (x: 2.2cm, y: 2.3cm),
  numbering: "1",
  footer: context [
    #set text(7.5pt, fill: rgb("#6b6a66"))
    #line(length: 100%, stroke: 0.4pt + rgb("#d8d7d2"))
    #v(3pt)
    #grid(columns: (1fr, auto),
      align(left)[Pain-Face — Technical Report],
      align(right)[#counter(page).display("1")])
  ],
)
#set text(font: ("Helvetica Neue", "Helvetica", "Arial"), size: 9.7pt, fill: rgb("#111111"))
#set par(justify: true, leading: 0.62em, spacing: 1.05em)
#set heading(numbering: "1.1")
#show heading.where(level: 1): it => block(above: 1.5em, below: 0.75em)[
  #set text(13pt, weight: 700); #it
]
#show heading.where(level: 2): it => block(above: 1.15em, below: 0.5em)[
  #set text(10.6pt, weight: 700); #it
]
#show heading.where(level: 3): it => block(above: 0.9em, below: 0.4em)[
  #set text(9.9pt, weight: 700, style: "italic"); #it
]
#show figure.caption: it => [#set text(8.3pt, fill: rgb("#52514e")); #it]
#set figure(gap: 0.8em)
#set table(stroke: (x, y) => (
  top: if y <= 1 { 0.7pt + rgb("#111111") } else { 0.4pt + rgb("#deddd8") },
  bottom: 0.4pt + rgb("#deddd8"),
))
#show table.cell.where(y: 0): set text(weight: 700, size: 8.4pt)
#show table: set text(8.6pt)
#let note(body) = block(
  fill: rgb("#f6f5f1"), stroke: (left: 2.2pt + rgb("#eb6834")),
  inset: (x: 11pt, y: 9pt), radius: 1pt, width: 100%,
)[#set text(9.1pt); #body]
#let kw(body) = text(weight: 700)[#body]

// ─────────────────────────────────────────────────────────── title
#align(center)[
  #v(0.3cm)
  #par(justify: false, leading: 0.48em)[
    #text(17pt, weight: 700)[
      Pain-Face: A Multimodal Platform Combining Facial\
      Action-Unit Analysis with Remote Photoplethysmography\
      for Automatic Pain Assessment
    ]
  ]
  #v(0.45cm)
  #text(10.5pt)[Mohammed Naveed Shariff]
  #v(0.15cm)
  #text(8.6pt, fill: rgb("#52514e"))[Technical Report · #datetime.today().display("[day] [month repr:long] [year]")]
  #v(0.5cm)
  #line(length: 100%, stroke: 0.7pt + rgb("#111111"))
]

#v(0.3cm)

*Abstract.* This report specifies Pain-Face, a real-time platform that estimates
observable pain behaviour by combining frame-level facial action-unit (AU)
analysis with remote photoplethysmography (rPPG) from the same camera. The work
is a direct continuation of our earlier feasibility study on YOLOv8-based pain
detection @cascella2024, and addresses the two gaps that study identified in its
own limitations: that a detector may be *misled by "pain-like" expressions*, and
that *incorporating biosignals could reinforce the model*. Pain-Face replaces
binary pain/no-pain object detection with continuous estimation of the Prkachin
and Solomon Pain Intensity (PSPI) score @prkachin2008 over its full 0–16 range,
adds a specificity correction that discounts the AUs that pain shares with
smiling, and adds an autonomic channel derived from an eight-algorithm rPPG
bank, fused so that facial evidence remains necessary.

We report validation of the facial channel on the Delaware Pain Database
@mende2020 against manual FACS coding and observer pain ratings
(#kw[n = 95] images). Our AU detection agrees with human coders better than
OpenFace on the same images (mean F1 #kw[0.629] vs 0.597; mean Cohen's
$kappa$ #kw[0.481] vs 0.381), and the resulting PSPI correlates with observer
pain ratings at #kw[r = +0.619] ($p = 2.3 times 10^(-11)$), rising to
#kw[r = +0.649] with the specificity correction applied. On images whose
dominant expression is *happy*, the correction reduces the score from 69.0% to
#kw[43.1%] of scale while pain images fall only from 89.3% to 83.9% — the
correction discriminates rather than merely attenuating. We also report, with
equal prominence, where the system fails: AU10 detection is near chance
(F1 0.464, $kappa$ 0.076), disgust and anger remain substantially confounded
with pain, and the correction slightly *reduces* categorical pain-vs-rest
separation (AUC 0.846 → 0.828) even as it improves intensity correlation.

The rPPG and fusion channels are *verified but not validated*: still images
cannot exercise them, and we state this explicitly rather than implying
otherwise. A protocol for the required video-based validation is given.

#v(0.2cm)
#note[
  *Not a medical device.* Pain-Face estimates observable pain *behaviour*, not
  what a person feels. It has not been clinically validated and must not be used
  for diagnosis, triage, or treatment decisions.
]

= Introduction

== Continuity with prior work

In @cascella2024 we demonstrated that a real-time object detector, YOLOv8, could
classify facial images as pain or no-pain using AU-derived labels. Images were
labelled by the presence of the PSPI action units (AU4, AU6, AU7, AU9, AU10,
AU43) and thresholded at PSPI > 2. Across all classes the model reached
mAP 0.893 at IoU 0.5, with precision 0.868 for *pain* and 0.919 for *no-pain*,
and a peak F1 of 0.80.

That study closed with two explicit statements of what remained undone:

#note[
  "…it will be essential to determine how the model truly works in terms of
  interpretability and explainability. This step is crucial for determining
  whether the model accurately detects genuine pain *or can be misled by
  'pain-like' expressions*. *Incorporating biosignals could help reinforce the
  model by integrating physiological data with facial expression analysis* to
  address this." — @cascella2024, Limitations
]

Pain-Face is the system built to answer both. The present report specifies it,
measures it, and states precisely which of its claims are now evidenced and
which are not.

== Contributions

+ *A specificity correction for PSPI.* We quantify the extent to which PSPI
  over-reads non-pain expressions, because AU6 and AU10 are shared with smiling,
  and derive a correction that discounts the shared terms in proportion to smile
  evidence. On Delaware, this moves happy faces from 69.0% to 43.1% of scale
  while leaving pain faces essentially intact (§6).
+ *A fusion model in which facial evidence is necessary.* Autonomic arousal
  modulates the facial score multiplicatively through its remaining headroom, so
  that no degree of tachycardia produces a pain reading on a neutral face, and
  the index cannot saturate (§7).
+ *Abstention as a first-class behaviour.* The system refuses to report a pulse
  rate when the arriving frame rate would alias the cardiac band, refuses HRV on
  short windows, and distinguishes "no face" from "no pain" (§8). We measure the
  abstention boundary empirically (§10.2).
+ *A dual-rate real-time architecture* carrying 30 Hz colour and ~6 Hz AU
  inference over one channel, with drop-not-queue backpressure (§4).
+ *Validation of the facial channel* against human FACS coding and observer pain
  ratings, including a three-way comparison with OpenFace, and a demographic
  breakdown (§9).

= Why this system does not use YOLO

It is worth stating plainly, because the prior work did: *Pain-Face contains no
YOLO model.* This is a deliberate methodological choice rather than an
incidental one, and the reasoning matters.

YOLO is an object detector. It localises a region and assigns it a class
confidence. Applied to pain, as in @cascella2024, this requires collapsing an
ordinal construct into a binary label — in that study, PSPI > 2 — which discards
the graded information PSPI was designed to carry. More importantly, a detection
head returns a confidence score for a box. It cannot report *which* facial
muscle group drove that score, because it never represents the AUs separately.
That is exactly the interpretability gap the prior study identified.

Pain-Face instead estimates each action unit independently, computes PSPI
analytically from those estimates over its full 0–16 range, and retains the
four-term decomposition. This permits three things a detection head cannot
offer: the continuous score, an explanation of which term produced it, and the
detection of confounds that arise from specific shared terms — which is the
mechanism of our specificity correction.

This is a change of task, not a claim that the earlier result was wrong. Binary
screening and graded estimation are different problems; the YOLOv8 result stands
for the problem it addressed. We note for completeness that YOLOv8 has since
been superseded (YOLO11, 2024; YOLO26, 2026), but no version of YOLO is used
here.

= Background

== FACS, PSPI, and the pain expression

The Facial Action Coding System decomposes facial movement into anatomically
grounded action units. The Prkachin and Solomon Pain Intensity score
@prkachin2008 is the standard frame-level facial pain metric derived from it:

$ "PSPI" = "AU4" + max("AU6", "AU7") + max("AU9", "AU10") + "AU43" $

AU4 (brow lowerer), the orbital-tightening term (AU6 cheek raiser / AU7 lid
tightener) and the levator term (AU9 nose wrinkler / AU10 upper lip raiser) each
contribute 0–5; AU43 (eye closure) contributes 0–1. The score therefore ranges
0–16. Critically, the paired terms take the *maximum*, never the sum — AU6 and
AU7 are alternative expressions of the same underlying orbital contraction.

Kunz and Lautenbacher @kunz2014 showed that pain expressions cluster into brow
lowering, orbital tightening, levator contraction and open mouth, and — of
direct relevance to this work — that what distinguishes pain from enjoyment is
partly what is *absent*: AU12, the lip corner puller.

== Remote photoplethysmography

rPPG recovers the cardiac pulse from subtle colour changes in skin caused by
blood volume variation. We implement eight published algorithms: GREEN
@verkruysse2008, ICA @poh2010, PCA @lewandowska2011, CHROM @dehaan2013, PBV
@dehaan2014, POS @wang2017, LGI @pilz2018 and OMIT @alvarez2023. Heart-rate
variability metrics follow the Task Force standard @taskforce1996, and
detrending follows Tarvainen @tarvainen2002.

= System architecture

== The dual-rate problem

The two channels have incompatible natural rates. Inter-beat interval estimation
needs every frame at ~30 Hz to resolve beat timing; the AU network sustains
roughly 9–12 frames per second on the hardware measured here (§10.5). Running
both at the slower rate would corrupt the pulse signal; running the detector at
30 Hz is not possible.

Pain-Face therefore runs them at independent rates over a single WebSocket:

- *Colour, every frame.* The browser computes mean skin RGB over forehead and
  both cheeks, taken from a MediaPipe face mesh with a YCrCb skin gate, and
  batches one second of triples per message.
- *Frames, a few times a second.* A 480 px JPEG is sent for AU inference at a
  configurable rate (default 6 Hz).

Frames arriving while an inference is in flight are #kw[dropped, not queued].
Stale action units are worse than fewer of them, and dropping provides natural
backpressure on slower hardware without unbounded latency growth.

== Components

#table(
  columns: (auto, 1fr),
  [Module], [Responsibility],
  [`painface/pspi.py`], [AU vocabulary, PSPI terms, the published formula, FACS-coder path],
  [`painface/au.py`], [Py-Feat wrapper: lazy init, NCHW tensor path, face quality],
  [`painface/vitals.py`], [Rolling rPPG buffer, autonomic feature reduction, abstention],
  [`painface/fusion.py`], [Specificity correction, baseline, fusion, trigger hysteresis],
  [`painface/session.py`], [Recording, episode statistics, JSON/CSV export],
  [`painface/server.py`], [FastAPI, `/ws/live`, offline video endpoint],
  [`static/painface.html`], [Capture, rendering, the operator interface],
)

= The facial channel

== Detection

Action units are estimated with Py-Feat's `Detectorv2` @cheong2023, a multi-task
network returning 20 AUs, 7 emotion probabilities, 68 landmarks, head pose, gaze
and 52 blendshapes per detected face. Frames are supplied as NCHW `uint8`
tensors, which avoids file I/O in the live path.

Two implementation constraints are worth recording. First, the available AU set
does not include *AU27*; the open-mouth component must therefore rest on AU25
and AU26. Second, Py-Feat reports AU *occurrence probabilities* in $[0,1]$, not
FACS A–E *intensities* in $[0,5]$. We map probability to each term's ceiling,
which produces a score commensurate with the published 0–16 range, but a
probability of 0.8 is not equivalent to a coder scoring intensity D. This is a
documented approximation and a stated limitation (§12). Where true coder
intensities are available, `pspi_raw()` computes the literal score with no
approximation.

== The specificity problem

PSPI is a valid measure of the pain expression, but it is not pain-*specific*.
AU6 appears in the Duchenne smile; AU10 appears in both smiling and disgust.
A face expressing enjoyment therefore accumulates PSPI points through terms it
shares with pain.

This is not hypothetical. On Py-Feat's own bundled sample image — a face the
model itself classifies as 99% *happy* — raw PSPI evaluates to #kw[7.24 / 16],
or 45% of scale. Any system reporting that number as a pain intensity is
reporting a smile as moderate pain.

== The correction

Pain is separated from enjoyment by the absence of AU12 and by the brow: pain
lowers it, happiness does not @kunz2014. We define smile evidence

$ sigma = "clip"( "AU12" dot (0.55 + 0.45 dot p_("happy")) dot (1 - 0.7 dot "AU4") ) $

and discount only the terms that smiling shares with pain, in proportion:

$ "PSPI"_c = sum_(t in T) "pts"_t dot (1 - s_t dot sigma) \/ 16 $

where $s_t = 0.85$ for the orbital term, $0.65$ for the levator term, and $0$
for brow lowering and eye closure, which smiling does not produce.

The literal PSPI is retained and reported alongside the corrected score. Both
appear in the interface; neither is hidden. §9.3 measures whether the correction
does what it claims on real faces.

= The autonomic channel

Pain produces sympathetic activation, and the same camera that reads the face
can measure it. This section specifies the full signal chain from pixels to
heart rate, since that path determines what every downstream autonomic feature
is worth.

#figure(
  image("../validation/figs/f9_pipeline.svg", width: 86%),
  caption: [The rPPG chain on a synthetic trace of known rate (72.0 bpm).
  (a) spatially averaged skin colour; (b) the recovered pulse after projection,
  detrending and band-passing, with detected beats and one inter-beat interval
  marked; (c) the power spectrum, with the estimate taken from the dominant
  in-band peak at $f_0$ and the de Haan SNR bands shaded. Recovered rate
  72.07 bpm.],
)

== Stage 1: region selection and skin segmentation

Three regions are tracked from the MediaPipe 478-point face mesh: the forehead
and both cheeks, taken as convex hulls of fixed landmark sets. They are chosen
for dense superficial microvasculature and relative freedom from hair, eyebrow
and nasolabial shadow.

Within each hull, pixels are admitted only if they fall in the Chai and Ngan
chrominance range for skin,

$ 133 <= C_r <= 173, quad 77 <= C_b <= 127 $

computed per pixel from the RGB triple. Hair, lips, eyes and background are
thereby excluded; they carry no pulse and would otherwise attenuate it.

== Stage 2: spatial averaging

For frame $n$ and channel $c in {R, G, B}$, each region $k$ yields a mean over
its admitted pixel set $Omega_k (n)$, and the three regions are combined by
pixel count so that larger, better-conditioned regions dominate:

$ C_c (n) = (sum_k sum_(p in Omega_k (n)) I_c (p, n)) / (sum_k abs(Omega_k (n))) $

Spatial averaging over $10^3$–$10^4$ pixels is what makes the measurement
possible at all: the per-pixel pulsatile modulation is far below camera noise,
and averaging reduces that noise by roughly $sqrt(N)$ while the pulse, being
spatially coherent, is preserved.

== Stage 3: uniform resampling

Browser frame timestamps are irregular. The three traces are sorted, duplicate
timestamps dropped, and linearly interpolated onto a uniform grid at
$f_s = 30$ Hz. Every subsequent stage assumes uniform sampling; §8 describes
what happens when the arriving rate cannot support it.

== Stage 4: temporal normalisation

Each channel is divided by its own temporal mean over the window,

$ C_n (t) = C(t) \/ macron(C) $

which removes the dependence on absolute illumination and skin tone, leaving
the relative modulation that carries the pulse. The chrominance methods below
operate on $C_n$ in short sliding windows (1.6 s, Hann-weighted, 50 % overlap,
overlap-added), so that slow illumination drift cannot bias the projection.

== Stage 5: pulse extraction, eight algorithms

Each method reduces the three normalised channels to one scalar waveform. They
differ in how they suppress motion and illumination artefacts, which share the
colour subspace with the pulse.

*GREEN* @verkruysse2008 takes the green channel alone, where haemoglobin
absorption is strongest: $S = G \/ macron(G)$.

*CHROM* @dehaan2013 forms two chrominance signals from a standardised skin-tone
assumption and combines them so that the specular motion component cancels:

$ X_s = 3R_n - 2G_n, quad Y_s = 1.5 R_n + G_n - 1.5 B_n, quad
  S = X_s - (sigma(X_s) \/ sigma(Y_s)) Y_s $

*POS* @wang2017 projects onto a plane orthogonal to the specular direction and
applies the same alpha-tuning:

$ S_1 = G_n - B_n, quad S_2 = G_n + B_n - 2R_n, quad
  S = S_1 + (sigma(S_1) \/ sigma(S_2)) S_2 $

*PBV* @dehaan2014 uses the blood-volume signature $p_("bv")$, the normalised
vector of per-channel standard deviations, to find the weighting that best
explains the observed covariance:

$ W = (C_z C_z^T + epsilon I)^(-1) p_("bv"), quad S = (C_z^T W) \/ (p_("bv") dot W) $

where $C_z$ is the mean-centred normalised matrix.

*LGI* @pilz2018 removes the dominant subspace, which carries illumination
change, via the singular value decomposition $X = U Sigma V^T$:

$ S = [(I - u_1 u_1^T) X]_G, quad u_1 = "first column of" U $

*OMIT* @alvarez2023 achieves the same orthogonalisation through a QR
decomposition, which is cheaper and better conditioned:
$S = [(I - q_1 q_1^T) X]_G$.

*PCA* and *ICA* @lewandowska2011 @poh2010 are blind source separation. PCA takes
the eigenvectors of the channel covariance; ICA uses symmetric FastICA with the
logcosh contrast, whitening first by eigendecomposition. Both produce three
candidate components, and neither orders them by physiological relevance, so the
component is chosen by in-band spectral concentration,

$ rho(x) = max_(f in B) P(f) \/ sum_(f in B) P(f), quad B = [0.7, 3.5] "Hz" $

selecting the candidate whose power is most concentrated at a single plausible
cardiac frequency.

== Stage 6: detrending

Extracted waveforms carry low-frequency drift from illumination and slow head
motion. We apply smoothness-priors detrending @tarvainen2002, which removes a
trend defined by a second-difference penalty rather than a fixed polynomial:

$ z_("trend") = (I + lambda^2 D_2^T D_2)^(-1) z, quad z_("stat") = z - z_("trend") $

with $lambda = 100$ and $D_2$ the second-order difference operator. The system
is sparse and solved directly. Unlike a high-pass filter, this introduces no
phase distortion at the band edge, which matters because beat timing is
extracted downstream.

== Stage 7: band-pass filtering

A third-order Butterworth band-pass restricted to $[0.7, 3.5]$ Hz (42–210 bpm)
is applied *zero-phase*, forward and backward, in second-order-section form.
Zero-phase filtering is not a cosmetic choice: a causal filter would shift
every beat by a frequency-dependent delay and corrupt the inter-beat intervals
on which all HRV metrics depend.

== Stage 8: spectral estimation and heart rate

The heart rate is taken from the dominant spectral peak inside the cardiac
band. Two estimates are computed.

The *periodogram* estimate applies a Hann window and zero-pads to at least 4096
points. Zero-padding does not add information, but it interpolates the spectrum
so the peak can be located more precisely. The peak bin $k$ is then refined to
sub-bin resolution by fitting a parabola through the three surrounding points in
the log-power domain, which is the correct interpolant for a Gaussian-shaped
windowed peak:

$ delta = (1/2) (ln P_(k-1) - ln P_(k+1)) / (ln P_(k-1) - 2 ln P_k + ln P_(k+1)),
  quad f_0 = f_k + delta dot Delta f $

$ "HR" = 60 f_0 quad ["bpm"] $

Without this refinement the resolution would be limited to $Delta f = f_s \/ N_("fft")$;
with it, the error on a clean synthetic signal falls below 0.1 bpm (§10.3).

A *Welch* estimate (8 s segments, 50 % overlap) is computed in parallel. It
trades frequency resolution for variance reduction, and large disagreement
between the two is itself a signal-quality warning.

== Stage 9: signal quality

Each method's output is scored with the signal-to-noise ratio of de Haan and
Jeanne @dehaan2013, which treats power at the fundamental and its second
harmonic as signal and everything else in $[0.5, 4]$ Hz as noise:

$ "SNR" = 10 log_10 ( (sum_(f in cal(S)) P(f)) / (sum_(f in cal(N)) P(f)) ) $

$ cal(S) = {f : abs(f - f_0) <= 0.1 or abs(f - 2 f_0) <= 0.2}, quad
  cal(N) = [0.5, 4] without cal(S) $

The second harmonic is included because the arterial pulse is not sinusoidal:
the dicrotic notch places real physiological power at $2 f_0$, and excluding it
would penalise a good signal.

== Stage 10: fusion across methods

The eight estimates are combined by a *weighted median* rather than a mean,
with weights $w_i = max("SNR"_i, -10) + 10$. The median is chosen deliberately:
when one method locks onto a motion artefact its estimate is not merely noisy
but wrong by tens of bpm, and a mean would be dragged by it while a weighted
median is not. The weighting lets confident methods decide among themselves.

== Beat detection and inter-beat intervals

Spectral HR gives an average rate; HRV requires individual beat times.

The waveform is re-filtered into an HR-adaptive band $[0.6 f_0, 1.6 f_0]$, which
suppresses the second harmonic so the dicrotic notch is not detected as a beat.
After z-scoring, peaks are found subject to a refractory distance of
$0.6 times 60 \/ "HR"$ seconds and a prominence floor of 0.35. Any pair closer
than 70 % of the median interval is merged, keeping the taller. Each retained
peak time is then refined by the same parabolic interpolation used in the
spectrum, giving sub-sample timing.

Intervals are accepted only within physiological range, $0.28 < "IBI" < 1.6$ s,
and within 20 % of the rolling median. The rejected fraction is reported as
`artifact_pct`; it is a quality figure in its own right.

== HRV metrics

From the accepted interval series the standard time-domain measures are
computed: SDNN, RMSSD, SDSD, pNN50 and pNN20, together with the Poincaré
descriptors $"SD1" = sqrt(1\/2) sigma(Delta "RR")$ and
$"SD2" = sqrt(2 sigma^2("RR") - "SD1"^2)$, and the Baevsky stress index
$"AMo" \/ (2 "Mo" dot "MxDMn")$ on 50 ms bins.

Frequency-domain measures require an evenly sampled tachogram, so the intervals
are cubic-spline interpolated to 4 Hz and a Welch spectrum is integrated over
the Task Force bands @taskforce1996: VLF 0.0033–0.04 Hz, LF 0.04–0.15 Hz, HF
0.15–0.4 Hz, yielding LF/HF and normalised units.

== Respiration

Breathing modulates the pulse in three ways, and all three are estimated and
median-fused. *RIIV*, baseline intensity modulation, is recovered by detrending
the normalised green channel with a longer prior ($lambda = 300$) and
band-passing to 0.1–0.5 Hz. *RIAV*, pulse amplitude modulation, is taken from
the envelope of detected beat amplitudes resampled to 4 Hz. *RSA*, respiratory
sinus arrhythmia, is the dominant peak of the tachogram spectrum within the same
band. Agreement between three mechanisms is stronger evidence than any one.

== Perfusion and the SpO#sub[2] ratio

The perfusion index is the pulsatile fraction of the green channel,
$"PI" = 100 dot 2 sigma("AC") \/ "DC"$, which falls under vasoconstriction. The
ratio-of-ratios $R = ("AC"\/"DC")_R \/ ("AC"\/"DC")_B$ is computed and displayed
as an *uncalibrated index only*: without a reference oximeter to fit the
calibration curve it is not an oxygen saturation, and the interface labels it as
such.

== Autonomic features and baseline normalisation

Six features are passed to the fusion model, each scored against the subject's
own calm baseline, because absolute heart rate carries no information about pain
while a rise above *this person's* rest does.

#table(
  columns: (auto, auto, auto, 1fr),
  [Feature], [Direction], [SD floor], [Rationale],
  [Heart rate], [↑], [2.0 bpm], [tachycardia under nociception],
  [RMSSD], [↓], [5.0 ms], [parasympathetic withdrawal],
  [SDNN], [↓], [5.0 ms], [overall variability reduction],
  [LF/HF], [↑], [0.3], [sympathovagal shift],
  [Respiration rate], [↑], [1.5 br/min], [respiratory acceleration],
  [Perfusion index], [↓], [0.15 %], [peripheral vasoconstriction],
)

Each is converted to a signed z-score against the baseline, with a minimum
standard deviation (the "SD floor") so that an unusually steady rest period
cannot magnify ordinary jitter into a large deviation. Scores are saturated and
averaged to an arousal value in $[0,1]$ where 0.5 denotes "at baseline". Until
the baseline holds sufficient samples the channel reports `ready = false` and
contributes nothing.

= Multimodal fusion

== The model

Let $f$ be the corrected facial pain evidence in $[0,1]$ and $d in [-1, +1]$ the
autonomic deviation from baseline. The fused intensity is

$ I = f dot (1 + k dot d dot (1 - f)), quad k = W_a \/ W_f = 0.25 \/ 0.75 = 1\/3 $

reported on a 0–10 scale for familiarity with numeric rating scales.

== Two properties this form guarantees

*Facial evidence is necessary.* At $f = 0$ the expression evaluates to zero for
every value of $d$. No degree of autonomic arousal can produce a pain reading
from a neutral face. Measured: a neutral face at 130 bpm with suppressed HRV
yields #kw[NRS 0.2]. Arousal corroborates; it never originates.

*The index cannot saturate.* Modulation acts on the headroom $(1 - f)$ that
remains, so $I → 1$ asymptotically. A severe episode retains resolution near the
top of the scale instead of pinning flat. An earlier additive formulation
clamped a facial score of 0.76 to a maximum reading; this form returns 0.82 for
the same inputs. Figure 7 shows the full response surface.

== Episode segmentation

A latching trigger with hysteresis converts the continuous index into discrete
episodes: the index must hold above an onset threshold for a *dwell* period to
fire, and fall below a lower threshold for a *release* period to clear. A
momentary grimace therefore does not start an episode, and a blink does not end
one. Defaults: onset 0.30, release 0.18, dwell 0.6 s, release 1.5 s.

= Abstention: refusing to report

A measurement instrument that reports a plausible wrong number is more dangerous
than one that reports nothing. Three abstention rules are implemented.

*Aliasing.* The cardiac band extends to 3.5 Hz. A colour trace arriving below
approximately twice that rate folds energy into the band and yields a confident,
incorrect heart rate. Browsers throttle hidden tabs to roughly 1 fps, and loaded
machines drop frames, so the arriving rate is measured rather than assumed. Below
#kw[7.7 Hz] (2.2 × the band ceiling) heart rate and HRV are withheld with a
stated reason. This rule was added after observing the system report 52 bpm from
a 1 Hz trace. §10.2 measures the resulting boundary.

*Short windows.* RMSSD and SDNN are unstable on short records. They are withheld,
and excluded from the baseline, until the analysis window reaches 30 s.

*No face.* Py-Feat returns a populated row with `FaceScore = 0` and all AUs `NaN`
when no face is present. Treating that as a neutral expression would score it as
"no pain" rather than "no measurement". The case is detected explicitly.

= Validation: Delaware Pain Database

== Protocol

The Delaware Pain Database @mende2020 provides posed and evoked facial
expressions with two forms of ground truth distributed alongside the images:
manual FACS coding by trained human coders, and continuous observer pain
ratings. OpenFace's AU codes for the same images are also distributed, which
permits a three-way comparison without us re-running that tool.

We scored every image for which manual coding and an image file could both be
resolved: #kw[n = 95]. AU probabilities were binarised at #kw[0.5], the same
threshold the live system uses, so the reported agreement reflects deployed
behaviour rather than a tuned operating point. Expression categories in the set:
pain 45, disgusted 14, surprised 11, happy 9, sad 9, angry 6, fearful 1.

#note[
  *Scope.* These are still images. They validate the *facial channel only*. The
  rPPG channel, the autonomic features, the fusion model and the episode trigger
  are not exercised by this data and remain verified but unvalidated (§11).
]

== Agreement with human FACS coders

#figure(
  image("../validation/figs/f2_au_agreement.svg", width: 99%),
  caption: [Per-AU agreement with manual FACS coding (F1, threshold 0.5).
  Pain-Face exceeds OpenFace on 10 of 16 comparable AUs. Asterisks mark the AUs
  that enter the PSPI formula. AU10 is poor for both tools.],
)

Mean F1 across the 16 AUs with sufficient variance is #kw[0.629] for Pain-Face
against #kw[0.597] for OpenFace; mean Cohen's $kappa$ is #kw[0.481] against
#kw[0.381]. Restricted to the five AUs entering PSPI, Pain-Face mean F1 is
#kw[0.755].

#table(
  columns: (auto, auto, auto, auto, auto),
  [Action unit], [Prevalence], [F1 (ours)], [$kappa$ (ours)], [F1 (OpenFace)],
  [AU25 lips part], [0.547], [*0.961*], [0.915], [0.950],
  [AU04 brow lowerer\*], [0.853], [*0.935*], [0.661], [0.872],
  [AU09 nose wrinkler\*], [0.547], [*0.854*], [0.707], [0.793],
  [AU07 lid tightener\*], [0.768], [0.839], [0.351], [0.870],
  [AU12 lip corner puller], [0.368], [*0.818*], [0.722], [0.692],
  [AU17 chin raiser], [0.211], [*0.714*], [0.633], [0.588],
  [AU06 cheek raiser\*], [0.379], [*0.682*], [0.436], [0.643],
  [AU28 lip suck], [0.074], [*0.667*], [0.638], [0.444],
  [AU26 jaw drop], [0.221], [0.600], [0.539], [0.600],
  [AU01 inner brow raiser], [0.221], [0.545], [0.458], [0.604],
  [AU05 upper lid raiser], [0.053], [0.500], [0.479], [0.545],
  [#text(fill: rgb("#a5341f"))[AU10 upper lip raiser\*]], [0.274], [#text(fill: rgb("#a5341f"))[0.464]], [#text(fill: rgb("#a5341f"))[0.076]], [0.433],
  [#text(fill: rgb("#a5341f"))[AU23 lip tightener]], [0.158], [0.457], [0.338], [0.355],
  [AU02 outer brow raiser], [0.074], [0.400], [0.372], [0.636],
  [#text(fill: rgb("#a5341f"))[AU14 dimpler]], [0.158], [0.317], [0.101], [0.364],
  [#text(fill: rgb("#a5341f"))[AU20 lip stretcher]], [0.095], [0.308], [0.265], [0.163],
)
#text(8.3pt, fill: rgb("#52514e"))[
  \* enters the PSPI formula. Bold marks where Pain-Face exceeds OpenFace.
  Rows in red are below an F1 of 0.5 and should not be relied upon.
]

#kw[AU10 is the significant negative result.] At F1 0.464 and $kappa$ 0.076 its
detection is barely above chance, and it is one half of the PSPI levator term.
OpenFace performs no better (F1 0.433, $kappa$ 0.054), which suggests an
intrinsically difficult AU rather than a defect specific to our pipeline — but
it directly caps the reliability of that term, and by extension of PSPI itself.
Because the term takes $max("AU9", "AU10")$ and AU9 is detected well
(F1 0.854), the practical damage is limited, but it is real.

== Correlation with observer pain ratings

#figure(
  image("../validation/figs/f1_pspi_vs_rating.svg", width: 92%),
  caption: [Facial pain score against mean observer pain rating. Both raw and
  corrected scores correlate significantly; the correction improves the
  relationship modestly and consistently.],
)

#block(breakable: false)[#table(
  columns: (1fr, auto, auto, auto, auto),
  [Score], [Pearson r], [p], [Spearman ρ], [n],
  [Raw PSPI], [+0.619], [$2.3 times 10^(-11)$], [+0.650], [95],
  [Smile-corrected], [*+0.649*], [$1.2 times 10^(-12)$], [*+0.664*], [95],
)]

This is the central validation result for the facial channel: the score tracks
human judgements of pain intensity with a moderate-to-strong, highly significant
association, and the specificity correction improves rather than degrades it.

== Does the specificity correction work?

#figure(
  image("../validation/figs/f3_specificity.svg", width: 99%),
  caption: [Mean score by dominant expression category, before and after the
  specificity correction. The correction acts almost entirely on *happy*,
  leaving pain nearly untouched — and leaving disgust and anger untouched also,
  which is the system's principal remaining confound.],
)

On the 9 images whose dominant expression is *happy*, raw PSPI reads 11.04 / 16
(69.0% of scale). The corrected score reads #kw[43.1%] — a 25.9-point reduction.
On the 45 *pain* images the same correction moves 89.3% to 83.9%, a reduction of
only 5.4 points. Mean smile evidence is 0.640 on happy faces against 0.123 on
pain faces.

The correction therefore discriminates rather than uniformly attenuating, which
is the claim it was designed to support, and it does so on real human faces
rather than on the single bundled sample that motivated it.

=== Where it does not help

Disgust (73% → 69%) and anger (73% → 71%) are barely affected, because the
correction keys on AU12 and happiness, neither of which those expressions
exhibit. They share AU4, AU9 and AU10 with pain through a different route.
Against a mean of 84% for pain, disgust at 69% is not comfortably separated.

Consequently, categorical separation of pain from all other expressions
*slightly decreases* under correction: AUC #kw[0.846 → 0.828]. The correction
improves agreement with rated intensity while marginally reducing the
pain-versus-rest decision boundary. We report both directions rather than
selecting the favourable one. For an application whose purpose is graded
intensity estimation the trade is defensible; for a binary alarm it may not be.

== Demographic breakdown

Target identifiers in the database encode self-reported race and sex, permitting
a stratified analysis — a dimension absent from our prior study.

#table(
  columns: (1fr, auto, auto, auto, auto),
  [Group], [n], [Pain-AU F1], [r (score vs rating)], [Face quality],
  [Asian], [24], [0.686], [0.577], [1.00],
  [Black], [23], [0.780], [0.550], [1.00],
  [Latinx], [23], [0.754], [0.616], [1.00],
  [White], [23], [*0.781*], [*0.736*], [1.00],
  [Female], [46], [0.783], [0.661], [1.00],
  [Male], [47], [0.733], [0.598], [1.00],
)

Face detection succeeded uniformly. AU detection quality varies by a spread of
#kw[0.095] in F1 across race groups, lowest for Asian targets; correlation with
observer ratings varies more widely, from 0.550 (Black) to 0.736 (White).
Group sizes are small (n ≈ 23–24) and these differences are not tested for
significance, so they should be read as an indication that stratified evaluation
is necessary, not as an established effect size. We report them because omitting
them would misrepresent the system's readiness.

= Characterisation of the implementation

These experiments establish the operating envelope. They are measurements of
system behaviour, not evidence about pain.

== Pulse estimation against signal quality

#figure(
  image("../validation/figs/f4_noise.svg", width: 90%),
  caption: [Fused heart-rate error against signal quality, averaged over
  54/72/96/120 bpm synthetic traces. Accurate to below 0.1 bpm while SNR exceeds
  roughly −3.5 dB; collapse is abrupt below that.],
)

Error remains under 0.05 bpm down to a median SNR of −3.5 dB, then degrades
sharply: 4.85 bpm at −5.8 dB and 28.4 bpm at −6.5 dB. The transition is a cliff
rather than a slope, which is why a reported SNR accompanies every estimate in
the interface.

== The abstention boundary

#figure(
  image("../validation/figs/f5_sampling.svg", width: 90%),
  caption: [Pulse estimation against effective frame rate. Above the 7.7 Hz
  threshold, error stays below 0.1 bpm; below it the system reports nothing
  rather than reporting an aliased value.],
)

At 8 Hz and above, all four test rates are accepted with MAE ≤ 0.07 bpm. At 7 Hz
and below, every estimate is refused. The threshold is therefore neither
over-conservative (8 Hz remains accurate) nor permissive.

== Method bank

#figure(
  image("../validation/figs/f6_methods.svg", width: 88%),
  caption: [Per-algorithm error on clean synthetic signals across 48–144 bpm.],
)

All eight algorithms resolve clean synthetic signals to better than 0.12 bpm
MAE, ranging from PBV (0.020) to LGI and OMIT (0.113). #kw[This ordering should
not be read as a general ranking]: the synthetic generator imposes a fixed
blood-volume colour direction, which structurally favours methods that estimate
that direction (PBV, PCA, ICA) over those using fixed projections tuned for real
skin under real illumination (CHROM, POS). Ranking these algorithms requires
recorded video with reference PPG.

== Fusion response

#figure(
  image("../validation/figs/f7_fusion.svg", width: 90%),
  caption: [Fused intensity as facial evidence varies, at three autonomic states.
  All three curves meet at the origin: facial evidence is necessary.],
)

Across the full input grid the maximum attainable intensity is 1.0 and the value
at zero facial evidence is exactly 0.0 for every autonomic state, confirming the
two properties claimed in §7.2.

== Detector throughput

#figure(
  image("../validation/figs/f8_throughput.svg", width: 88%),
  caption: [Action-unit inference throughput by detection width on Apple MPS,
  median of 12 runs after warm-up.],
)

Median latency at 480 px is 100.7 ms (9.9 fps), rising to 11.7 fps at 320 px.
#kw[These are medians, not best-case figures]; a best-of-N measurement on the
same hardware reports values near 17 fps, which we consider unrepresentative of
sustained operation. Throughput is the constraint that motivates the dual-rate
architecture of §4.1.

== Trigger timing

Onset and release latency equal the configured dwell and release periods exactly
across all four tested configurations (0.3/0.8, 0.6/1.5, 1.0/2.5, 2.0/4.0 s),
confirming deterministic behaviour with no additional lag.

= Verified versus validated

We separate these deliberately.

#table(
  columns: (1fr, auto, auto),
  [Component], [Verified], [Validated],
  [PSPI arithmetic], [Yes — hand-worked cases], [n/a (definition)],
  [AU detection], [Yes], [*Yes* — vs human FACS, n=95],
  [Specificity correction], [Yes], [*Yes* — vs expression category],
  [Facial score vs pain], [Yes], [*Yes* — r = 0.649 vs observer ratings],
  [rPPG algorithms], [Yes — synthetic], [#text(fill: rgb("#a5341f"))[No]],
  [HRV / autonomic features], [Yes — synthetic], [#text(fill: rgb("#a5341f"))[No]],
  [Baseline normalisation], [Yes — unit tests], [#text(fill: rgb("#a5341f"))[No]],
  [Fusion model], [Yes — properties proven], [#text(fill: rgb("#a5341f"))[No]],
  [Episode trigger], [Yes — timing exact], [#text(fill: rgb("#a5341f"))[No]],
  [Abstention rules], [Yes — boundary measured], [n/a],
)

*No claim is made that the fused multimodal index measures pain.* The facial
component correlates with human pain judgements on still images. The autonomic
component and the fusion that combines them have never been tested against any
ground truth, because doing so requires synchronised video, reference
physiology, and pain labels — data we do not yet have.

The implementation is covered by #kw[91 automated tests] across 4,749 lines of
code, pinning the PSPI formula term by term, the fusion invariants, trigger
hysteresis under a non-monotonic clock, heart-rate recovery at four rates, the
abstention boundary, and the full WebSocket protocol.

= Limitations

+ *Observable behaviour, not experience.* People mask pain; stoicism reads as
  absence. A low score is not evidence of comfort.
+ *Probabilities are not intensities.* Py-Feat reports occurrence probability;
  PSPI is defined on A–E intensities. Our mapping preserves the scale's range
  and ordering but not its coder-equivalent semantics.
+ *AU10 is unreliable* (F1 0.464), weakening one half of the levator term.
+ *Disgust and anger are confounded with pain* and the present correction does
  not address them. This is the most important open problem.
+ *The specificity correction trades categorical separation for intensity
  correlation* (AUC 0.846 → 0.828).
+ *Still images only.* All validation here is on posed and evoked stills from one
  database. Nothing establishes behaviour on continuous video, spontaneous
  clinical pain, or patients.
+ *Demographic performance varies* across the groups measured, with small n.
+ *The autonomic channel is unvalidated*, and its features are not pain-specific:
  exercise, anxiety, caffeine and ambient temperature all move them. This is why
  the fusion lets them modulate but never originate a reading.
+ *rPPG is fragile*: it requires diffuse flicker-free illumination, a reasonably
  still subject, and locked exposure. Auto-exposure injects noise directly into
  the cardiac band.
+ *Fusion weights are reasoned, not fitted.* $W_f = 0.75$, $W_a = 0.25$, the
  discount factors and the trigger thresholds derive from the structure of the
  literature, not from optimisation against labelled data. Their *form* is
  defended in §7.2 and verified; their *values* are a starting point.

= Proposed validation protocol

The following would convert the unvalidated rows of §11 into measured ones.

*Stage 1 — Video facial validation (UNBC-McMaster).* The UNBC-McMaster Shoulder
Pain Expression Archive @lucey2011 provides 200 sequences from 25 patients with
frame-level PSPI coded by certified FACS coders and self-report. Required
outputs: per-frame MAE and RMSE against coder PSPI; Pearson and Spearman
correlation; trigger ROC against sequence-level pain; per-patient breakdown.
Requires a signed academic data agreement.

*Stage 2 — Autonomic validation.* Synchronised recording of face video with a
reference contact PPG or ECG, under rest and a controlled nociceptive stimulus
(for example cold-pressor or pressure algometry, with ethical approval).
Required outputs: Bland–Altman agreement of rPPG heart rate against reference;
RMSSD and LF/HF agreement; sensitivity of each autonomic feature to the
stimulus.

*Stage 3 — Fusion validation.* With Stages 1 and 2 in place, test whether the
fused index outperforms the facial channel alone against self-reported pain —
the central unproven claim of this work. An ablation (facial only, autonomic
only, fused) is the minimum required analysis.

*Stage 4 — Fitting and fairness.* Replace the reasoned constants with values
fitted on held-out data, and report performance stratified by skin tone under
the Monk or Fitzpatrick scale, which the present data does not support.

= Reproducibility

Source: `https://github.com/NaveedShariff/Pain-Face`.

#table(
  columns: (auto, 1fr),
  [Component], [Version],
  [Python], [3.11.16],
  [py-feat], [2.1.3 (`Detectorv2`, device `mps`)],
  [PyTorch], [2.14.1],
  [NumPy / SciPy], [2.4.6 / 1.17.1],
  [OpenCV], [5.0.0],
)

Every number in this report regenerates from the repository:

```
python -m pytest                      # 91 tests
python validation/run_delaware.py     # score the database
python validation/analyse.py          # agreement, correlation, specificity
python validation/characterise.py     # the six characterisation experiments
python validation/figures.py          # all figures
```

Ground truth is read directly from the Delaware distribution's
`DelawarePainDatabase_StimulusCharacterization_forOSF.xlsx`; no labels were
re-derived or hand-adjusted.

#v(0.5cm)
#line(length: 100%, stroke: 0.4pt + rgb("#d8d7d2"))
#v(0.2cm)

#bibliography("refs.yml", title: "References", style: "ieee")
