# Claude Code — Kickoff Prompt

Paste this into Claude Code at the root of the project (with the provided files present).

---

You are building the **Ratings & Feedback module** for Interview Kickstart's New Programs team — a
production system that finds low-rated classes each Monday, uses an LLM to draft instructor feedback plus a
PM-only "re-class?" call, lets a PM review/approve, and delivers it with a full audit trail.

**Read `BUILD_SPEC.md` in full before writing anything — it is the complete brief.** Then build the system
exactly as specified.

**Start from the provided, working files — reuse them, don't rewrite them:**
- `engine.py` — the analysis engine (parse → chunk → extract → synthesise + validate; returns flags,
  instructor feedback, and a PM-only re-class recommendation). 16 tests pass.
- `service.py` — FastAPI wrapper (`/health`, `/dry-run`, `/analyze`).
- `schema.sql` — the Postgres store. `test_engine.py`, `requirements.txt`, `README.md`.

**Build in the milestone order in §9 of the spec.** Specifically:
1. **`db.py`** — Postgres data-access layer (§6.2) + unit tests.
2. **`metabase.py`** — read low-rated classes for assigned courses directly from Metabase (§6.1).
   And **`uplevel.py`** — auto-fetch each class's transcript from the IK **uplevel** LMS (§6.6); authenticate with a
   durable credential at runtime (platform service token, or a stored Cognito refresh token) — **never captured browser cookies**.
3. Extend **`service.py`** — add `/ingest`, and make `/analyze` persist to Postgres (§6.3).
4. **The n8n workflows — build them yourself, properly** (§7): WF1 (Monday ingest → Slack), WF3 (approve →
   Discord DM), then WF2/WF4. Wire the nodes, add error branches, and **export each workflow as JSON into an
   `/n8n` folder**. Use n8n credentials for all secrets.
5. **The PM UI** (§6.4) — Next.js + Supabase on Vercel (or Streamlit/Retool if faster): queue, upload
   transcript + agenda, review draft + flags + re-class call, edit, approve.
6. **The eval harness** in `eval/` (§6.5).

**Notifications (§8):** PM alerts → **Slack** group channel (Monday summary, drafts ready, errors,
reminders). Instructor feedback delivery → **Discord DM**, after PM approval only. Keep both configurable.

**Conventions (non-negotiable):**
- Secrets only from env vars / n8n credentials — **never hardcode**. Retries + timeouts + input validation
  on every external call. Idempotency via DB unique constraints. Structured logging. Errors must post a
  Slack alert and leave state recoverable. Write tests for each module and keep the engine tests green.
- The LLM only reads and drafts — **a PM approves every send**. The re-class call is PM-only; it must never
  appear in the instructor's message.

**Before wiring any external service, ask me for the credentials in §10 of the spec** (Anthropic key,
Metabase URL + how to query + columns, **uplevel base URL + a durable API/refresh-token credential**, `DATABASE_URL`, Slack token + channel, Discord token, `UI_URL`).
Also ask me where the **class agenda** comes from and for **1–2 real "good feedback" examples** for few-shot.

**Way of working:** go milestone by milestone. After each, run the tests and show me what you built and how
to verify it. If anything in the spec is ambiguous, ask before guessing. Don't fake external services in the
final build — write the code so it's testable, and use the real services once I provide credentials.

**Start now with M1: apply `schema.sql`, build `db.py` with the functions in §6.2, and write its unit tests.**
