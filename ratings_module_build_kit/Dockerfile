# Analysis worker (FastAPI + the engine).
# Runtime env vars: ANTHROPIC_API_KEY (required), VIMEO_ACCESS_TOKEN, WORKER_API_KEY (shared secret),
#   and DATABASE_URL (required for the async /analyze-async endpoint, which writes the result back).
# Runs on any container platform (Render, AWS App Runner/ECS, Google Cloud Run, Azure Container Apps,
# Fly.io, Railway, or internal Docker/Kubernetes).
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# All modules the worker imports at runtime. store.py does the async DB write-back — it MUST be here,
# or the container crashes on startup with "No module named 'store'".
COPY engine.py service.py vimeo.py config.py store.py ./

ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn service:app --host 0.0.0.0 --port ${PORT}"]
