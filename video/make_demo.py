"""Cut the screen recording into a short highlight reel.

Plain text over the footage, no panels, bars or tints. Segments are chosen
from the recording's own arc and stop before the engine disconnects at 102 s.
"""
import cv2, numpy as np
from PIL import Image, ImageDraw, ImageFont

SRC = "/Users/mohammednaveedshariff/Desktop/rppg demo.mov"
OUT = "video/Pain-Face_demo.mp4"
W, H, FPS = 1456, 829, 30

PAPER = (240, 240, 238)        # RGB
INK   = (17, 17, 17)
MUTED = (110, 110, 110)
F = "/System/Library/Fonts/HelveticaNeue.ttc"
def font(sz, idx=0):
    try:    return ImageFont.truetype(F, sz, index=idx)
    except Exception: return ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", sz)

f_title, f_sub, f_cap, f_small = font(64, 1), font(24), font(26), font(18)

# (start_s, end_s, caption)
SEGMENTS = [
    (6.0,  17.0, "One ordinary webcam. Nothing is attached to the subject."),
    (52.0, 66.0, "Facial action units give PSPI on its published 0 to 16 scale."),
    (84.0, 94.0, "An episode latches when the pain units hold, and is logged."),
    (94.0, 101.0, "The same camera recovers the pulse. 72 bpm, no contact sensor."),
]

def halo_text(draw, xy, text, fnt, fill=INK, halo=(246, 246, 244), r=3, alpha=255):
    """Plain text made legible over any background by a soft outline, not a box."""
    x, y = xy
    for dx in range(-r, r + 1):
        for dy in range(-r, r + 1):
            if dx * dx + dy * dy <= r * r:
                draw.text((x + dx, y + dy), text, font=fnt, fill=halo + (alpha,))
    draw.text((x, y), text, font=fnt, fill=fill + (alpha,))

def card(lines, hold_s, fade_s=0.45):
    """A full-frame card on paper. Used only at the head and tail."""
    base = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(base)
    total = sum(h for _, _, h in lines) + 26 * (len(lines) - 1)
    y = (H - total) // 2
    for text, fnt, h in lines:
        w = d.textbbox((0, 0), text, font=fnt)[2]
        d.text(((W - w) // 2, y), text, font=fnt, fill=INK if fnt is f_title else MUTED)
        y += h + 26
    arr = np.asarray(base)
    n = int(hold_s * FPS); nf = int(fade_s * FPS)
    for i in range(n):
        k = min(i / nf, 1.0, (n - i) / nf)
        yield cv2.cvtColor((arr * k + np.array(PAPER) * (1 - k)).astype(np.uint8), cv2.COLOR_RGB2BGR)

def main():
    cap = cv2.VideoCapture(SRC)
    src_fps = cap.get(cv2.CAP_PROP_FPS)
    vw = cv2.VideoWriter(OUT, cv2.VideoWriter_fourcc(*"avc1"), FPS, (W, H))
    if not vw.isOpened():
        vw = cv2.VideoWriter(OUT, cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H))
    written = 0

    for fr in card([("Pain-Face", f_title, 70),
                    ("Facial action units and remote photoplethysmography", f_sub, 30),
                    ("recorded live, one camera", f_sub, 30)], 2.6):
        vw.write(fr); written += 1

    for si, (t0, t1, caption) in enumerate(SEGMENTS):
        n_out = int((t1 - t0) * FPS)
        fade = int(0.5 * FPS)
        for i in range(n_out):
            cap.set(cv2.CAP_PROP_POS_FRAMES, int((t0 + i / FPS) * src_fps))
            ok, fr = cap.read()
            if not ok: break
            fr = cv2.resize(fr, (W, H), interpolation=cv2.INTER_AREA)
            img = Image.fromarray(cv2.cvtColor(fr, cv2.COLOR_BGR2RGB)).convert("RGBA")
            layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
            d = ImageDraw.Draw(layer)
            a = int(255 * min(i / fade, 1.0, (n_out - i) / fade, 1.0))
            if a > 0:
                halo_text(d, (46, H - 74), caption, f_cap, alpha=a)
                halo_text(d, (46, H - 38), f"{si + 1} / {len(SEGMENTS)}", f_small,
                          fill=MUTED, alpha=a)
            out = Image.alpha_composite(img, layer).convert("RGB")
            vw.write(cv2.cvtColor(np.asarray(out), cv2.COLOR_RGB2BGR)); written += 1
        print(f"  segment {si+1}: {t1-t0:.0f}s", flush=True)

    for fr in card([("Research instrument", f_title, 70),
                    ("Not a medical device. It estimates observable pain behaviour,", f_sub, 30),
                    ("not what a person feels.", f_sub, 30)], 3.0):
        vw.write(fr); written += 1

    cap.release(); vw.release()
    print(f"\n{OUT}  {written} frames  {written/FPS:.1f} s")

main()
