# Analysis worker (FastAPI + the engine). Stateless: no database access.
# Runtime env vars: ANTHROPIC_API_KEY (required), VIMEO_ACCESS_TOKEN, WORKER_API_KEY (shared secret).
# Runs on any container platform (AWS App Runner/ECS, Google Cloud Run, Azure Container Apps,
# Fly.io, Railway, or internal Docker/Kubernetes).
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY engine.py service.py vimeo.py config.py ./

ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn service:app --host 0.0.0.0 --port ${PORT}"]
