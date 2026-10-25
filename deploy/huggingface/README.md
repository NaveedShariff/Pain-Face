---
title: Pain-Face
emoji: 🫀
colorFrom: gray
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: Multimodal pain intensity from facial action units and rPPG
---

# Pain-Face

Estimates observable pain behaviour from an ordinary webcam, combining facial
action units (Py-Feat) with remote photoplethysmography from the same video.
The facial score is the Prkachin and Solomon Pain Intensity on its published
0–16 scale, corrected for the action units that pain shares with smiling, and
modulated — never created — by autonomic signs recovered from the pulse.

**Not a medical device.** It estimates observable pain *behaviour*, not what a
person feels. It has not been clinically validated and must not be used for
diagnosis, triage or treatment.

## Using it

Press **Start** and allow camera access. Keep the tab in front: browsers
throttle hidden tabs below the rate a pulse can be measured at, and the app
will tell you when that happens rather than showing a wrong heart rate.

For the autonomic column, press **Calibrate baseline** and sit still for about
thirty seconds first. Every feature is scored against your own calm period,
because absolute heart rate says nothing about pain while a rise above *your*
rest does.

No camera, or just want to see it work? Choose **Simulator**.

## Privacy

Frames leave your device. The browser sends a 480 px JPEG to this Space a few
times a second for action-unit inference, and streams skin-colour averages for
the pulse. Nothing is written to disk and nothing persists past your session,
but if that is not acceptable for your subjects, run it locally instead:
everything works offline once the weights are cached.

## Performance here

This Space runs on CPU, where a detection takes about a second, against ten a
second on a laptop GPU. The page detects this and asks for action units at a
matching rate. The architecture already
accounts for that: frames arriving while inference is in flight are dropped
rather than queued, and the colour trace for the pulse runs at full rate
independently.

Source, technical report and validation: https://github.com/NaveedShariff/Pain-Face
