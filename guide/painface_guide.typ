#set document(
  title: "Pain-Face — A Visual Guide to the Multimodal Pain Assessment Platform",
  author: "Mohammed Naveed Shariff",
)
#set page(
  paper: "a4",
  margin: (x: 2.0cm, top: 2.0cm, bottom: 2.1cm),
  numbering: "1",
  footer: context [
    #set text(7.5pt, fill: rgb("#8a8880"))
    #line(length: 100%, stroke: 0.4pt + rgb("#e0dfda"))
    #v(3pt)
    #grid(columns: (1fr, auto),
      align(left)[Pain-Face — A Visual Guide],
      align(right)[#counter(page).display("1")])
  ],
)
#set text(font: ("Helvetica Neue", "Helvetica", "Arial"), size: 10.3pt, fill: rgb("#1a1a18"))
#set par(justify: true, leading: 0.74em, spacing: 1.2em)
#set heading(numbering: none)

#show heading.where(level: 1): it => block(above: 1.8em, below: 0.9em)[
  #set text(16pt, weight: 700, fill: rgb("#111111"))
  #block(stroke: (bottom: 1.2pt + rgb("#1a1a18")), inset: (bottom: 7pt), width: 100%)[#it.body]
]
#show heading.where(level: 2): it => block(above: 1.4em, below: 0.55em)[
  #set text(11.6pt, weight: 700); #it.body
]
#show heading.where(level: 3): it => block(above: 1.1em, below: 0.4em)[
  #set text(10.3pt, weight: 700, fill: rgb("#8a4a1e")); #it.body
]
#show figure.caption: it => [#set text(8.6pt, fill: rgb("#6a6862")); #it]
#set figure(gap: 0.7em)

#let shot(path, cap, w: 100%) = figure(
  block(width: w, stroke: 0.6pt + rgb("#dedcd6"), radius: 2pt, clip: true)[
    #image(path, width: 100%)
  ],
  caption: cap,
)
#let callout(title, body, color: "#8a4a1e") = block(
  width: 100%, fill: rgb("#f7f6f2"), stroke: (left: 2.6pt + rgb(color)),
  inset: (x: 13pt, y: 11pt), radius: 1pt,
)[
  #text(weight: 700, size: 10pt)[#title] \
  #v(2pt) #body
]
#let key(body) = text(weight: 700)[#body]

// ───────────────────────────────────────────────────────── cover
#align(center)[
  #v(1.1cm)
  #text(9pt, fill: rgb("#8a8880"), weight: 600)[A VISUAL GUIDE]
  #v(0.5cm)
  #text(30pt, weight: 800)[Pain-Face]
  #v(0.35cm)
  #par(justify: false)[
    #text(13.5pt, fill: rgb("#44423d"))[
      Measuring pain from a face and a pulse,\ using nothing but an ordinary camera
    ]
  ]
  #v(0.9cm)
  #line(length: 42%, stroke: 0.8pt + rgb("#1a1a18"))
  #v(0.5cm)
  #text(10.5pt)[Mohammed Naveed Shariff]
  #v(0.12cm)
  #text(8.8pt, fill: rgb("#8a8880"))[Companion to the Pain-Face Technical Report]
]

#v(1.0cm)

#callout([What this document is], [
  A walkthrough of what the system does, shown through the working application,
  written for a reader who wants to understand the idea rather than the
  equations. The companion technical report carries the formulas, the validation
  statistics and the references. Screenshots are from live sessions, not mock-ups.
])

#v(0.5cm)

#callout([An important limit, stated at the start], [
  Pain-Face estimates *observable pain behaviour*. It does not read what a person
  feels. It is a research instrument, it has not been clinically validated, and
  it must never be used to decide a patient's treatment.
], color: "#a3301f")

#pagebreak()

= The problem worth solving

Pain is measured by asking. "On a scale of nought to ten, how bad is it?" That
works well — right up until the patient cannot answer.

A sedated patient in intensive care cannot answer. Neither can someone with
advanced dementia, a newborn, a patient recovering from anaesthesia, or someone
whose stroke has taken their speech. For these people, pain is judged by a nurse
watching the face, intermittently, between other duties. It is skilled work, and
it is subjective, and it stops the moment the nurse leaves the room.

The obvious idea is to let a camera watch instead. The difficulty is that a
camera watching a face is easily fooled.

== Why the face alone is not enough

The face carries genuine pain information. Decades of research established which
muscles move during pain, and a standard score — *PSPI* — built from them. But
that score is not pain-*specific*:

- A person wincing at a bad smell activates several of the same muscles.
- So does someone straining to lift something heavy.
- So, awkwardly, does a broad smile: two of the muscles that score pain points
  are also the muscles of a genuine grin.
- And a stoic patient in real pain may show almost nothing at all.

== Why the pulse alone is worse

The body reacts to pain too. The heart speeds up, beat-to-beat variability
falls, breathing quickens, the skin's small vessels tighten. All of this is
measurable from the same camera, with no sensor touching the patient.

But none of it is specific to pain. A racing heart means someone climbed stairs,
drank coffee, is anxious about the result, or is simply warm. On its own it is
nearly useless as a pain signal.

#v(0.3cm)
#callout([The idea behind Pain-Face], [
  Neither channel is trustworthy alone — but they fail in *different* ways. The
  face says #key[what] is happening: this is the specific pattern of a pain
  expression, not a smile. The body says #key[what it is costing]: this person's
  physiology is reacting, not just their face.

  Put together, each one covers the other's blind spot.
])

#pagebreak()

= What you see on screen

== Two numbers, side by side

#shot("shots/a_two_readings.png",
  [The two readings the system produces. On the left, the dial and the *fused
  index* — everything combined, on the familiar 0–10 pain scale. Beside it the
  *PSPI*, the published facial pain score on its own 0–16 scale. The five blocks
  below step from None to Worst as the reading climbs.])

We deliberately show both rather than one. The PSPI is the established,
published measure that clinicians and researchers already know, so it stays
visible and unmodified. The fused index is our contribution: the facial evidence
after correction, adjusted by what the body is doing.

A reader who trusts only the literature can read the PSPI and ignore everything
else. Nothing is hidden behind the combined number.

== The face, read muscle by muscle

#shot("shots/b_units_firing.png",
  [The four components of the PSPI score, drawn on a face diagram rather than
  listed as numbers. The live camera inset sits in the corner, so the diagram
  can be checked against the real face at a glance. Here the levator
  contraction (the nose-and-upper-lip group) is firing strongly at 0.72, while
  the brow and eye components are quiet.], w: 78%)

This panel exists because of a criticism of our earlier work. A system that
simply announces "pain detected" cannot be checked. This one shows *which*
muscle group produced the score, so a clinician can look at the patient and
judge for themselves whether the machine is reading the face correctly.

The four rows are exactly the four terms of the PSPI formula — brow lowering,
orbital tightening, levator contraction, eye closure. Nothing else contributes
to the score.

#pagebreak()

= Reading a pulse from a face

This is the part that surprises people: the camera measures the heartbeat
without anything touching the patient.

Every time the heart beats it pushes blood into the vessels under the skin.
That changes, very slightly, how much light the skin absorbs — far too little
for the eye to notice, but enough for a camera. By watching patches of skin
across many frames and tracking the colour shift, the pulse can be recovered.
This is called *remote photoplethysmography*, or rPPG.

#shot("shots/c_capture_roi.png",
  [Three patches of skin are tracked continuously — the forehead and both
  cheeks — chosen because they are well supplied with blood and relatively free
  of hair and shadow. The dashed box is the detected face. The patches follow
  the face as it moves.])

Only skin-coloured pixels inside those outlines are used; hair, eyebrows and
background are filtered out, because they carry no pulse and would dilute the
signal.

#shot("shots/d_pulse.png",
  [The recovered pulse waveform and its frequency spectrum. The peak in the
  spectrum is the heart rate — here 72 beats per minute. This came from an
  ordinary laptop webcam, with no contact sensor of any kind.], w: 74%)

== What the body is doing

#shot("shots/e_autonomic.png",
  [The autonomic panel. Respiration rate and perfusion are available quickly;
  the heart-rate-variability measures stay greyed out until enough signal has
  been collected, rather than showing an unreliable early estimate.])

=== Why there is a "baseline" button

A heart rate of 95 means nothing by itself. For a calm adult it is raised; for
someone who just walked upstairs it is ordinary; for an anxious patient it may
be their normal.

So the system does not use absolute values. It asks the operator to record a
short calm period first, then measures every later reading as a *deviation from
that person's own rest*. A rise of 20 beats above this patient's baseline is
information. A heart rate of 95 is not.

Until a baseline exists, the autonomic panel contributes nothing to the score
and says so.

= Why combining them is better than either alone

This is the central claim of the project, so it is worth setting out plainly.

== The rule: the face must speak first

The combination is deliberately *not* an average of the two channels. Averaging
would mean a calm face plus a racing heart produces a moderate pain score —
which would be wrong, and dangerous.

Instead, the facial evidence sets the reading, and the body is only allowed to
*adjust* it:

#v(0.25cm)
#align(center)[
  #block(fill: rgb("#f7f6f2"), inset: 14pt, radius: 2pt, width: 86%)[
    #align(center)[
      #text(11pt, weight: 700)[No pain on the face → no pain reported,] \
      #v(3pt)
      #text(11pt, weight: 700)[however fast the heart is beating.]
    ]
  ]
]
#v(0.25cm)

We tested this directly. Shown a completely neutral face together with a heart
rate of 130 and suppressed variability — physiologically, a person under
considerable stress — the system reports #key[0.2 out of 10]. It refuses to call
that pain, because the face does not support it.

When the face *does* show pain, the body then adjusts the reading by up to about
a third in either direction:

#v(0.2cm)
#table(
  columns: (auto, 1fr),
  stroke: (x, y) => (top: if y <= 1 { 0.7pt + rgb("#1a1a18") } else { 0.4pt + rgb("#e0dfda") },
                     bottom: 0.4pt + rgb("#e0dfda")),
  [Situation], [What the system does],
  [Pain face, body also reacting],
  [Reading is raised. Face and physiology agree — the strongest evidence available.],
  [Pain face, body completely calm],
  [Reading is lowered. The expression is there, but nothing else is. Worth less confidence.],
  [Neutral face, body racing],
  [Near zero. Something is happening to this person, but there is no evidence it is pain.],
  [No baseline recorded yet],
  [Facial score only, labelled "facial only" on screen so nobody mistakes it for the full reading.],
)

== The problem this solves: pain-like faces

Our earlier published study ended by warning that a facial detector "can be
misled by 'pain-like' expressions". Here is that problem, caught by the system
itself:

#shot("shots/i_disgust.png",
  [A deliberately disgusted expression — not pain. The emotion row at the bottom
  reads *disgust 62*. Several of the muscles that score PSPI points are active,
  because disgust and pain genuinely share them.], w: 82%)

The facial channel alone cannot fully resolve this, and we say so in the
technical report: disgust and anger remain the system's biggest weakness. What
the physiological channel offers is a second, independent opinion — a disgusted
face is not usually accompanied by the sustained autonomic response of real
pain.

That is the hypothesis the combination is built on. It is a reasonable one, and
it is the reason this platform exists — but it has not yet been proven on
patients, and the technical report is explicit about that.

== The smile case, which we *have* measured

One pain-like expression we can already quantify is the smile. Two of the
muscles that earn PSPI points are also the muscles of a genuine grin, so a
smiling person scores high on the raw published formula.

Tested on 95 photographs from a published research database, scored against
ratings by human observers:

#v(0.2cm)
#align(center)[
  #table(
    columns: (auto, auto, auto),
    stroke: (x, y) => (top: if y <= 1 { 0.7pt + rgb("#1a1a18") } else { 0.4pt + rgb("#e0dfda") },
                       bottom: 0.4pt + rgb("#e0dfda")),
    [Faces], [Raw PSPI score], [After our correction],
    [Happy], [69%], [#text(fill: rgb("#a3301f"), weight: 700)[43%]],
    [In pain], [89%], [#text(weight: 700)[84%]],
  )
]
#v(0.2cm)

Smiling faces drop by 26 points; genuinely painful faces barely move. The
correction targets the confusion rather than just lowering everything.

= Catching pain as it happens

A single frame is a snapshot. Pain is an event, with a beginning and an end.

#shot("shots/j_timeline.png",
  [The timeline. The shaded band marks a detected pain episode — the moment the
  reading rose above threshold and stayed there.])

The system does not raise an episode the instant the number crosses a line. A
grimace lasting a fraction of a second is not an episode, and a blink should not
end one. So the reading must stay high for a short *dwell* period before an
episode opens, and must stay low for a longer period before it closes.

#shot("shots/f_episodes.png",
  [Each episode is logged with when it began, how long it lasted, its peak and
  mean, and — most usefully for a clinician — exactly which facial muscles were
  firing at its worst moment.], w: 88%)

That last column is what makes the log worth keeping. "Episode at 69.5 seconds,
peak 8.7, driven by AU4, AU6, AU7, AU9, AU10 and AU25" is a reviewable clinical
observation. "Pain detected" is not.

= When the system refuses to answer

A measuring instrument that quietly reports a wrong number is more dangerous
than one that reports nothing. Pain-Face is built to abstain.

#shot("shots/o_abstain_banner.png",
  [The camera was delivering frames too slowly for a pulse to be measured
  honestly. Rather than printing a plausible-looking heart rate, the system
  explains why it is withholding one.], w: 62%)

#shot("shots/n_chip_tooslow.png",
  [The same condition in the status bar. The heart rate simply disappears until
  the frame rate recovers.], w: 56%)

This matters more than it sounds. A pulse cannot be measured reliably below a
certain frame rate — below it, the maths produces a confident number that is
simply wrong. We found this the hard way: an early version happily reported
52 beats per minute from a stream far too slow to support it. The system now
measures its own frame rate and refuses below the limit.

It abstains in two other places as well: heart-rate variability is withheld
until there is enough recording to compute it properly, and "no face in frame"
is reported as *no measurement* rather than silently scored as "no pain".

#pagebreak()

= Not one algorithm, but eight

There is no single agreed-best way to extract a pulse from skin colour.
Published methods each make different assumptions, and each fails differently
under motion, lighting shifts and skin tone.

#grid(columns: (1.45fr, 1fr), column-gutter: 14pt,
  shot("shots/g_method_bank.png",
    [All eight algorithms run simultaneously on the same signal, each reporting
    its own heart rate and its own signal quality.]),
  shot("shots/h_method_picker.png",
    [Any method can be selected as the displayed waveform.]),
)

Running them together serves two purposes. The final heart rate is a
quality-weighted combination rather than one algorithm's opinion, which makes it
more robust. And when the eight disagree strongly, that disagreement is itself a
warning that the signal is poor.

#shot("shots/k_au_bank.png",
  [All twenty facial action units the system tracks, shown as a single strip.
  The pain-relevant units are highlighted when they fire, so the shape of a pain
  expression becomes recognisable at a glance rather than needing to be read
  number by number.])

#pagebreak()

= Where something like this could be used

#v(0.2cm)

== Patients who cannot report pain themselves
The clearest case. Sedated intensive-care patients, advanced dementia, neonates
and infants, recovery from anaesthesia, and patients whose stroke has affected
speech. These groups are consistently under-treated for pain precisely because
the standard tool — asking — does not work.

== Continuous monitoring on a ward
A nurse checks a post-operative patient every few hours. A camera could watch
between those checks and flag episodes for review. Not to replace the nurse's
judgement, but to make sure that what happened at three in the morning is not
lost by the time of the next round.

== Remote and tele-medicine consultations
The consultation already happens over a camera. Nothing extra needs to be worn,
attached, or shipped to the patient.

== Clinical trials of analgesics
Trials rest heavily on self-reported pain scores, which are subjective and
collected only at intervals. A continuous, objective behavioural measure
alongside self-report would strengthen that evidence — and because the system
logs which muscles fired, the measure is auditable rather than a black box.

== Research into pain expression itself
The platform records every action unit, every physiological feature, and the
full timeline, exportable as data. That is useful to anyone studying how pain
expression varies between people, conditions, or cultures.

#v(0.4cm)
#callout([Where it should *not* be used], [
  Anywhere the person being measured has an interest in the result being
  different. Pain assessment is not lie detection, and this system must not be
  repurposed to judge whether someone is "really" in pain for the benefit of an
  insurer, an employer, or a court. It is a clinical aid for people who cannot
  speak for themselves — not an instrument of suspicion against people who can.
], color: "#a3301f")

#pagebreak()

= What is proven, and what is not

Being clear about this is the difference between a research tool and a claim.

#table(
  columns: (1.3fr, auto, 1fr),
  stroke: (x, y) => (top: if y <= 1 { 0.7pt + rgb("#1a1a18") } else { 0.4pt + rgb("#e0dfda") },
                     bottom: 0.4pt + rgb("#e0dfda")),
  [Claim], [Status], [Evidence],
  [The system reads facial muscles accurately],
  [#text(fill: rgb("#1f6b3f"), weight: 700)[Tested]],
  [Agrees with human expert coders better than the standard comparison tool],
  [The facial score tracks human judgements of pain],
  [#text(fill: rgb("#1f6b3f"), weight: 700)[Tested]],
  [Correlation of 0.65 against observer ratings on 95 photographs],
  [The smile correction works],
  [#text(fill: rgb("#1f6b3f"), weight: 700)[Tested]],
  [Smiling faces drop 26 points, painful faces 5],
  [The pulse measurement is accurate],
  [#text(fill: rgb("#8a6a14"), weight: 700)[Partly]],
  [Verified against synthetic signals of known rate; never against a real heart monitor],
  [Combining face and body beats face alone],
  [#text(fill: rgb("#a3301f"), weight: 700)[Not yet]],
  [The central claim, and the next thing to test],
  [It works on real patients],
  [#text(fill: rgb("#a3301f"), weight: 700)[Not yet]],
  [All testing so far is on photographs and healthy volunteers],
)

#v(0.3cm)

The honest summary: the *facial* half of this platform has been measured against
human experts and performs well. The *physiological* half works in the
engineering sense but has never been checked against a real heart monitor. And
the claim that joining them beats either alone — the reason the project exists —
is a well-motivated hypothesis that has not yet been tested on people in genuine
pain.

= What comes next

== 1. Validate on patient video
Move from photographs to the standard clinical video archive, in which real
patients with shoulder injuries were recorded during painful movement and every
frame was scored by certified experts. This measures the facial channel against
genuine clinical pain rather than posed expressions.

== 2. Check the pulse against a real sensor
Record volunteers with both the camera and a proper contact heart monitor, at
rest and under a controlled, ethically approved painful stimulus. This is what
would turn "the pulse feature works" into "the pulse feature is accurate".

== 3. Prove the combination earns its place
With the first two done, test directly whether face-plus-body outperforms face
alone. If it does not, that is a result worth publishing too.

== 4. Solve the disgust and anger problem
The current correction handles smiles. Disgust and anger remain confused with
pain. The physiological channel is the most promising route — those expressions
should not carry the same sustained bodily response — but it must be shown, not
assumed.

== 5. Test fairly across skin tones
Both facial analysis and camera-based pulse measurement are known to vary with
skin tone and lighting. Early results show measurable differences between
groups. Any system intended for clinical use must be tested on the full range of
patients it will meet, and that testing must be published whatever it shows.

#v(0.6cm)
#line(length: 100%, stroke: 0.4pt + rgb("#e0dfda"))
#v(0.3cm)
#text(9pt, fill: rgb("#6a6862"))[
  Pain-Face is a research instrument and not a medical device. It estimates
  observable pain behaviour, not subjective experience, and must not be used for
  diagnosis, triage, or treatment. Formulas, statistics, methodology and
  references are in the companion technical report. Source code and the scripts
  that reproduce every figure are available at
  `github.com/NaveedShariff/Pain-Face`.
]
