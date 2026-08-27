# Deployment guide

Three pieces. **All three are live today** — this guide covers how they're deployed, and how to move
them to another cloud if IK ever wants to.

| Piece | What | Status |
|---|---|---|
| **Database** | Supabase (Postgres + Auth + RLS) | ✅ live |
| **Web app** | Next.js (`web/`) — login, dashboard, Feedback | ✅ live on **Vercel** → https://feedback-loop-ten.vercel.app |
| **Worker** | Python FastAPI (`ratings_module_build_kit/`) — runs the Claude analysis | ✅ live on **Render** (auto-deploys on push to `main`) |

The web app and worker are **standard, portable web services** — they run on any mainstream cloud.

> 🧑‍💻 **Setting the worker up from scratch, click by click (non-technical):**
> [docs/RENDER_SETUP.md](docs/RENDER_SETUP.md).

---

## 1. Worker (portable container)

The worker ships as a Docker image (`ratings_module_build_kit/Dockerfile`) — which also installs
**ffmpeg**, needed for video analysis. It keeps no state of its own: it holds nothing between requests
and stores no files; for background ("async") analyses it writes the finished result straight into the
same Supabase database, which is why it needs `DATABASE_URL`. Build once, deploy to whatever your
company uses:

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

| Variable | Required? | What it's for |
|---|---|---|
| `ANTHROPIC_API_KEY` | **yes** | The Claude API key that runs the analysis. |
| `DATABASE_URL` | **yes** | So background analyses can save their result. Without it, an analysis runs but is never stored and the class stays "analyzing". |
| `VIMEO_ACCESS_TOKEN` | recommended | Fetching transcripts (and video) from Vimeo. Optional if you only upload transcript files. See [docs/VIMEO_VIDEO_ACCESS.md](docs/VIMEO_VIDEO_ACCESS.md). |
| `WORKER_API_KEY` | recommended | Shared secret; if set, callers must send `Authorization: Bearer <it>`. Set the same value on the web app. |
| `VIDEO_MAX_FRAMES` | optional | How many frames a video analysis samples (default 60; **40** is the safe value on Render's free tier). |
| `VIDEO_DISABLED` | optional | Set to `1` as a kill-switch — analyses then run transcript-only. |

Most platforms inject a `PORT`; the image already binds to it.

Check it came up correctly with `GET /health` — it reports the model, whether the keys are present,
whether **ffmpeg** was found, and whether video analysis and the self-check pass are enabled.

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
