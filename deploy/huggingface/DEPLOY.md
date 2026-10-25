# Deploying to Hugging Face Spaces

The repository is an ordinary Docker build. A Space needs two things at its
root: the `Dockerfile` and a `README.md` carrying the Space card frontmatter.

## One-time setup

1. Create a Space at https://huggingface.co/new-space
   - **SDK**: Docker, blank template
   - **Hardware**: CPU basic is enough to start; upgrade later if you want
     the detector running faster than a few frames a second
2. Clone it and copy this project in:

```bash
git clone https://huggingface.co/spaces/<you>/pain-face && cd pain-face
rsync -a --exclude .git --exclude .venv311 --exclude '*.mov' \
      /path/to/rppg-lab/ .
cp deploy/huggingface/README.md README.md      # the Space card, not the repo README
git add -A && git commit -m "Pain-Face" && git push
```

The first build takes roughly ten minutes: it installs torch and fetches the
Py-Feat weights so that the running Space starts ready rather than warming up
on somebody's first request.

## Configuration

Set these under the Space's **Settings → Variables** if the defaults do not
suit:

| Variable | Default | Meaning |
|---|---|---|
| `PAINFACE_MAX_CLIENTS` | `4` | Concurrent sessions admitted. One shared detector, so raising this spreads the same throughput more thinly. Use `2` on CPU hardware. |
| `PAINFACE_WIDTH` | `480` | Detection width in pixels. 384 or 320 is noticeably faster with little loss in agreement. |
| `PAINFACE_DEVICE` | `auto` | `cpu`, `cuda`, or `auto`. On a GPU Space leave it on `auto`. |

## What to expect on CPU

Measured on this project's own hardware, the Py-Feat forward pass takes about
**940 ms on CPU**, so action units arrive a little over once a second against
roughly ten a second on a laptop GPU. Lowering the detection width barely
helps: 320 px costs 874 ms against 944 ms at 480 px, because the cost is the
network rather than the input.

The application adapts on its own. It reads the engine's device from
`/api/health` and drops the requested action-unit rate to 2/s when that device
is a CPU, so frames are not queued only to be discarded. Frames arriving while
inference is in flight are dropped rather than buffered, so readings stay
current even when they are sparse.

Two consequences worth planning for:

- **One shared detector.** Four concurrent clients on CPU get roughly a
  quarter of one detection a second each. For a CPU Space, set
  `PAINFACE_MAX_CLIENTS` to 2.
- **A GPU Space changes the experience.** If the demo matters, the smallest
  paid GPU tier restores the laptop-like rate; CPU basic is adequate for
  showing that the system works, not for showing it working well.

The pulse side is unaffected. Colour averaging happens in the browser at the
full frame rate and the rPPG analysis is cheap numpy, so heart rate and HRV
are as accurate here as they are locally.

## Why hosting helps

`getUserMedia` refuses to run outside a secure context. Locally that works
only because `localhost` is exempt; on any other machine the camera is simply
unavailable over plain HTTP. A Space gives you HTTPS, so the application works
from a phone or from somebody else's laptop without any certificate work.

## Running the same image elsewhere

```bash
docker build -t painface .
docker run -p 8000:7860 -e PAINFACE_MAX_CLIENTS=8 painface
```

Behind a reverse proxy, forward WebSocket upgrades on `/ws/live` and terminate
TLS in front; the camera will not work otherwise.
