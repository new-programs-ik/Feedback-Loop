# Analysis worker (FastAPI + the engine).
# Runtime env vars: ANTHROPIC_API_KEY (required), VIMEO_ACCESS_TOKEN, WORKER_API_KEY (shared secret),
#   and DATABASE_URL (required for the async /analyze-async endpoint, which writes the result back).
# Runs on any container platform (Render, AWS App Runner/ECS, Google Cloud Run, Azure Container Apps,
# Fly.io, Railway, or internal Docker/Kubernetes).
FROM python:3.12-slim

# ffmpeg is REQUIRED by the video-frames stage. Install the real system binary: the pip wheel
# (imageio-ffmpeg) did not work in the container, and a missing ffmpeg silently degrades every
# analysis to transcript-only.
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Everything the worker imports at runtime: three files at the top and four folders. A module the
# worker imports that is not under one of these crashes the container on startup with "No module
# named '<x>'"; tests/test_packaging.py builds this exact layout and imports every module in it.
# Keep these lines and .dockerignore consistent: nothing copied here may be ignored there.
COPY service.py config.py store.py ./
COPY feedback/ feedback/
COPY recordings/ recordings/
COPY ratings/ ratings/
COPY reporting/ reporting/

ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn service:app --host 0.0.0.0 --port ${PORT}"]
