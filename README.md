# NP-Team — Feedback & Analytics Platform

Interview Kickstart · New Programs. A secure web app where PMs turn a low-rated class
recording into reviewed, ready-to-store instructor feedback — with a long-term vision for
learner / instructor / course / cohort analytics and a Learner Health Score.

## Structure
| Folder | What |
|---|---|
| `web/` | Next.js app (App Router, TS) — login, dashboard, Feedback module. Deploys to Vercel (root dir `web/`). |
| `ratings_module_build_kit/` | Python analysis worker (FastAPI + the Claude engine + Vimeo transcript fetch). Ships as a Docker container. |
| `supabase/` | Postgres schema (migrations) + Row-Level Security policies. |
| `DEPLOY.md` | How to deploy the web app + worker. |
| `BUILD_SPEC.md` | The original build brief. |

## Architecture
Supabase (Postgres + Auth + RLS) is the single source of truth. The Next.js app owns all
reads/writes through RLS. The Python worker is stateless — given a Vimeo link or transcript, it
fetches captions + runs the engine and returns the analysis; the app persists it.

## Local dev
```bash
# Worker
cd ratings_module_build_kit && ./.venv/Scripts/python -m uvicorn service:app --port 8000
# Web
cd web && npm install && npm run dev
```
Secrets live in `.env` / `.env.local` (gitignored). See each folder's `.env*.example`.

## Status
Feedback module: **done** (analyze → review → edit → approve, with audit + RLS).
Next: deploy, accuracy eval harness, then the analytics modules.
