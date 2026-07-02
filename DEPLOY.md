# Deployment guide

Three pieces. The database is already live; the other two need hosting.

| Piece | What | Status |
|---|---|---|
| **Database** | Supabase (Postgres + Auth + RLS) | ✅ live |
| **Web app** | Next.js (`web/`) — login, dashboard, Feedback | to deploy |
| **Worker** | Python FastAPI (`ratings_module_build_kit/`) — runs the Claude analysis | to deploy |

The web app and worker are **standard, portable web services** — they run on any mainstream cloud.

---

## 1. Worker (portable container)

The worker is **stateless** (no database) and ships as a Docker image
(`ratings_module_build_kit/Dockerfile`). Build once, deploy to whatever your company uses:

- **AWS:** App Runner (simplest), ECS/Fargate, Lightsail Containers, or Lambda (container image).
- **Google Cloud:** Cloud Run.
- **Azure:** Container Apps.
- **Other:** Fly.io, Railway, or internal Docker/Kubernetes.

Build & run locally to sanity-check:
```bash
cd ratings_module_build_kit
docker build -t ik-ratings-worker .
docker run -p 8000:8000 -e ANTHROPIC_API_KEY=... -e VIMEO_ACCESS_TOKEN=... -e WORKER_API_KEY=... ik-ratings-worker
# GET http://localhost:8000/health
```

**Worker env vars** (set in the hosting platform, never in code):
- `ANTHROPIC_API_KEY` — required.
- `VIMEO_ACCESS_TOKEN` — for Vimeo transcript fetch (optional if using upload only).
- `WORKER_API_KEY` — a shared secret; if set, callers must send `Authorization: Bearer <it>`.

Most platforms inject a `PORT`; the image already binds to it.

---

## 2. Web app (Next.js)

Recommended host: **Vercel** (built for Next.js, free tier). Alternatives: AWS Amplify Hosting,
Azure Static Web Apps, or any Node host / container (`npm run build` → `npm start`).

- **Root directory:** `web/`
- **Build:** `npm run build` · **Start:** `npm start`

**Web env vars:**
- `NEXT_PUBLIC_SUPABASE_URL` — the Supabase project URL
- `NEXT_PUBLIC_SUPABASE_ANON_KEY` — Supabase publishable/anon key
- `SUPABASE_SERVICE_ROLE_KEY` — Supabase secret key (server-only)
- `ANALYSIS_WORKER_URL` — the deployed worker's URL (e.g. `https://worker.internal…`)
- `WORKER_API_KEY` — the SAME shared secret set on the worker

---

## 3. Wiring & security
- Point the web app's `ANALYSIS_WORKER_URL` at the deployed worker.
- Set the SAME `WORKER_API_KEY` on both so only the web app can call the worker.
- Rotate the credentials that were shared during development (Supabase keys, Claude key, DB password).
- Enable the Supabase **Custom Access Token** hook (optional; see `supabase/README.md`).
