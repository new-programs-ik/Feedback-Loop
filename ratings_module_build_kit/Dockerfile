# Analysis worker (FastAPI + the engine).
# Runtime env vars: ANTHROPIC_API_KEY (required), VIMEO_ACCESS_TOKEN, WORKER_API_KEY (shared secret),
#   and DATABASE_URL (required for the async /analyze-async endpoint, which writes the result back).
# Runs on any container platform (Render, AWS App Runner/ECS, Google Cloud Run, Azure Container Apps,
# Fly.io, Railway, or internal Docker/Kubernetes).
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# All modules the worker imports at runtime. Every local import in service.py must be listed here, or
# the container crashes on startup with "No module named '<x>'" (store.py = async DB write-back;
# materials_fetch.py = fetch materials from a link).
COPY engine.py service.py vimeo.py config.py store.py materials_fetch.py ./

ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn service:app --host 0.0.0.0 --port ${PORT}"]
