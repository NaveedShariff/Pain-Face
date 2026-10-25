# Pain-Face — container image.
#
# Built for Hugging Face Spaces (Docker SDK) but it is an ordinary image and
# runs anywhere Docker does. Model weights are fetched during the build, not
# on the first request, so nobody waits eighty seconds for the detector to
# appear the first time the Space wakes.

FROM python:3.11-slim

# libgomp: xgboost, which py-feat imports at load time, needs the OpenMP
# runtime. libgl/libglib: OpenCV. Everything else the wheels carry themselves.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Spaces runs the container as uid 1000; match it so the caches are writable.
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    HF_HOME=/home/user/.cache/huggingface \
    TORCH_HOME=/home/user/.cache/torch \
    PYTHONUNBUFFERED=1
WORKDIR /home/user/app

# Dependencies first, so edits to the application do not re-resolve torch.
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY --chown=user . .

# Warm the detector at build time: this downloads the Py-Feat weights (~300 MB)
# and runs one forward pass, so the image ships ready to serve.
RUN python -c "\
from painface.au import AUEngine; import numpy as np; \
e = AUEngine(device='cpu', width=480); \
assert e.warm(), e.init_error; \
e.analyze_frame(np.zeros((240,320,3), 'uint8')); \
print('detector warm:', e.status()['device'])"

# Spaces forwards to 7860. The server binds every interface inside the
# container; the platform terminates TLS in front of it, which the camera
# requires since getUserMedia refuses to run outside a secure context.
ENV PORT=7860 \
    PAINFACE_HOST=0.0.0.0 \
    PAINFACE_DEVICE=auto \
    PAINFACE_WIDTH=480 \
    PAINFACE_MAX_CLIENTS=4
EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s \
    CMD python -c "import urllib.request,sys; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:7860/api/health',timeout=4).status==200 else 1)"

CMD ["python", "-m", "painface.server"]
