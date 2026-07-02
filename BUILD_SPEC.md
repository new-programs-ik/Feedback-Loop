# Ratings & Feedback Module — Build Specification

**For:** Claude Code · **Owner:** Interview Kickstart, New Programs (NP) team · **Status:** ready to build

---

## 0. How to use this document

This is the complete brief. You are building a production system that, every Monday, finds the classes
that were rated poorly, uses an LLM to draft instructor feedback (and a PM-only "re-class?" call), lets a
PM review/approve, and delivers the feedback — with a full audit trail.

- **Start from the provided files** (already written and tested): `engine.py`, `service.py`, `schema.sql`,
  `test_engine.py`, `requirements.txt`, `README.md`.
- **Build in the milestone order in §9.** After each milestone, run the tests and show your work.
- **You build the n8n workflows yourself** (§7) — create them properly and export each as JSON.
- **Before wiring any external service, ask the human for the credentials in §10.** Never hardcode secrets.
- If anything here is ambiguous, ask before guessing.

> **Security — secrets & auth.** Several integrations (uplevel, Metabase, Anthropic, Slack, Discord) need
> live credentials. Supply them **only at runtime via environment variables / n8n credentials** — never in
> the repo, this spec, or a workflow body. A captured browser session or copied tokens are short-lived and
> tied to one person's login; **do not use them in code** (see §6.6 and §10).

---

## 1. What we're building

A 4-hour live class produces a learner rating. When a class is rated **below 4.5**, a PM has to figure out
what went wrong and give the instructor feedback — today that means watching the recording by hand. This
system automates the analysis and the first draft, keeping the PM as the approver.

**Scale (as of 25 Jun 2026):** ~72 classes/week (peak ~85). ~6–7/week rated low across all IK (peak ~15);
the NP team's slice is ~1–2 (max 3–4). Per low class, manual review is ~2–4 hours; the engine does it in
minutes for ~$0.26. Build for NP first; the design must scale to all of IK.

**Hard rule (human-in-the-loop):** the LLM only *reads* and *drafts*. It never decides what happens and
never sends anything. A PM approves every piece of feedback before it reaches an instructor.

---

## 2. The end-to-end process (the lifecycle of one low-rated class)

```
Metabase ratings ──(Mon 9am, n8n → engine /ingest)──▶ queue row in Postgres  [needs_transcript]
        │
        ▼  transcript auto-fetched from uplevel (fallback: PM uploads .srt/.vtt) + agenda in the UI
   engine /analyze ───────────────────────────────────▶ analysis + draft saved  [draft_ready]
        │                                                 (+ Slack: "drafts ready")
        ▼  PM reviews flags + draft + re-class call, edits, approves
   feedback approved ─────────────────────────────────▶                          [approved]
        │
        ▼  n8n DMs the instructor on Discord (approved/edited text)
   delivered ─────────────────────────────────────────▶                          [sent] + audit
```

Every transition is written to `audit_log`. Notifications to PMs go to a **Slack** group channel;
instructor feedback is delivered by **Discord DM**.

### Status state machine (the `classes.status` column)
```
needs_transcript ──(analysis ok)──▶ draft_ready ──(PM approves)──▶ approved ──(n8n sends)──▶ sent
        │                                │
        │                                └──(PM discards)──▶ no_action
        └──(PM marks not worth it)──▶ no_action
analysis error → stays needs_transcript/analyzing, Slack alert raised (see §11)
```

### Rules & edge cases (must be handled)
- **Assigned courses only.** Each PM owns specific courses; the Metabase pull is filtered to them.
- **Per-class, not per-instructor.** If the same instructor has two low classes, each is its own row/draft;
  a well-rated class by that instructor is ignored.
- **No transcript yet?** If a class sits in `needs_transcript` past a threshold (e.g. 24h), Slack-remind the PM.
- **Idempotent.** The same class must not be queued twice (DB unique constraint) and the same
  transcript+context must not be analysed twice (engine already hashes this; the DB also guards it).
- **No free-text rating comments exist** — the transcript is the only signal. The engine already accounts
  for the transcript being instructor-voice-only (see its rubric); do not change that.
- **Re-class call is PM-only** — surface it in the UI and Slack, never in the instructor's message.

---

## 3. Architecture & components

```
                 ┌─────────────────────────────────────────────┐
   Mon 9am  ───▶ │ n8n  (orchestrator: schedule, Slack, Discord) │
                 └───────┬──────────────────────────────┬──────┘
                         │ HTTP                          │ HTTP (on approve)
                         ▼                               ▼
              ┌────────────────────┐            ┌────────────────────┐
  Metabase ◀──┤ engine service     │            │ Discord (DM         │
  (ratings)   │ (FastAPI, free host)│            │  instructor)        │
  uplevel  ◀──┤ reads both sources  │            └────────────────────┘
  (transcripts)
              │  /ingest /analyze  │            └────────────────────┘
              └─────────┬──────────┘
                        │ read/write
                        ▼
                 ┌──────────────┐        read/write       ┌──────────────────┐
                 │ Postgres     │ ◀──────────────────────▶│ PM UI (free host) │
                 │ (Supabase/   │                         │  queue · upload   │
                 │  Neon)       │                         │  review · approve │
                 └──────────────┘                         └──────────────────┘
                        │ alerts (via n8n)
                        ▼
                 ┌──────────────┐
                 │ Slack (PM    │
                 │ group channel)│
                 └──────────────┘
```

| Component | Status | Tech | Notes |
|---|---|---|---|
| Analysis engine | **provided** | Python | `engine.py` — works, 16 tests pass |
| HTTP service | **provided (extend)** | FastAPI | `service.py` — add `/ingest`, wire `/analyze` to DB |
| Store schema | **provided** | Postgres | `schema.sql` — apply as-is |
| Metabase ingest | build | Python | §6.1 |
| Uplevel integration | build | Python | §6.6 — fetch transcripts from the IK LMS |
| DB access layer | build | Python | §6.2 |
| n8n workflows | **build (yourself)** | n8n | §7 — export JSON |
| Slack alerts | build | n8n Slack node | §8 |
| Discord delivery | build | n8n Discord node | §8 |
| PM UI | build | Next.js + Supabase (rec.) | §6.4 |
| Eval harness | build | Python | §6.5 |

---

## 4. The provided foundation

- **`engine.py`** — `parse_cues(text)` / `parse_transcript(path)`, `chunk_by_time`, `analyse_text(raw, ctx)`
  / `analyse(path, ctx)`, the rubric + the two prompts, schema validation with a self-repair retry, real
  cost/latency tracking, a CLI. Returns `{overall, flags[], feedback, reclass{recommended,reason,deciding_flags}}`.
  Model pinned in `Config`. **Reuse it; don't rewrite it.** You may extend `Config` and add few-shot examples
  to the synthesis prompt (§6.5).
- **`service.py`** — FastAPI with `GET /health`, `POST /dry-run`, `POST /analyze`. Extend per §6.3.
- **`schema.sql`** — `classes`, `analyses`, `feedback`, `audit_log`. Apply to Postgres.

---

## 5. Data model

Use `schema.sql` exactly. Key points:
- `classes` — one row per low-rated class (unique on course+cohort+instructor+topic+class_date), with `status`.
- `analyses` — one row per engine run; the **full engine JSON** goes in `result jsonb`; `reclass` is denormalised
  for easy querying; `cost_usd`, `tokens_in/out` recorded.
- `feedback` — `draft_text` (engine) and `edited_text` (PM). **The diff between these two is the ongoing
  accuracy signal** — preserve both, never overwrite the draft.
- `audit_log` — append-only; write a row on every meaningful action (`pulled`, `analyzed`, `edited`,
  `approved`, `sent`, `error`, `reminded`).

---

## 6. Components to build

### 6.1 Metabase ingest — `metabase.py`
- Read low-rated classes for the PM's assigned courses for the past week, **directly from Metabase**.
- Prefer the **Metabase REST API**: authenticate, run a saved question/card (or a dataset query), return rows.
- Output a normalised list of dicts: `course, cohort, instructor, topic, class_date, rating, num_ratings, vimeo_link`.
- Config-driven: Metabase base URL, API key/session, the card ID(s) or SQL, and the assigned-courses filter.
- Validate the response shape; on auth/network failure, retry then raise a clear error (n8n will Slack-alert).
- **Ask the human** for: Metabase URL, how to query (saved card ID vs SQL), and the exact column names (§10).

### 6.2 Postgres data-access layer — `db.py`
- Thin layer (psycopg or SQLAlchemy Core) with functions:
  `upsert_class(...) -> id`, `set_status(class_id, status)`, `save_analysis(class_id, result, meta)`,
  `save_draft(class_id, analysis_id, draft_text)`, `update_feedback(...)`, `approve(class_id, pm)`,
  `mark_sent(class_id)`, `log(class_id, actor, action, detail)`, plus read helpers for the UI
  (`list_queue`, `get_class`).
- Connection string from `DATABASE_URL`. Use transactions; rely on the unique constraint for idempotency.
- Unit-test against a local/throwaway Postgres (or SQLite for logic tests).

### 6.3 Extend the service — `service.py`
- `POST /ingest` — calls `metabase.py` for the week's low classes, upserts each into `classes`
  (status `needs_transcript`), logs `pulled`, returns the list/count. (n8n's Monday trigger calls this.)
- Wire `POST /analyze` to **persist**: after `analyse_text`, write `analyses` + `feedback(draft)`,
  set status `draft_ready`, log `analyzed`. Accept a `class_id` so it attaches to the queued row.
- Add `POST /approve` (or let the UI write directly to Postgres) to set `approved` + return the text n8n
  should send. Keep all endpoints validated and error-handled (422 vs 500 as in the current file).

### 6.4 PM UI
- **Recommended stack:** Next.js (App Router) + the Supabase JS client, deployed free on Vercel.
  (Acceptable alternative if you want speed: Streamlit, or Retool over the same Postgres.)
- **Screens / actions:**
  1. **Queue** — table of this week's flagged classes with status, rating, course, instructor, the
     **re-class flag** (yes/no/maybe badge), and a filter to "my courses".
  2. **Upload** — for a `needs_transcript` row, upload the `.srt/.vtt` and paste/upload the **class agenda**;
     submitting triggers analysis (calls `/analyze` with the transcript text + context + `class_id`).
  3. **Review** — show the draft feedback (editable), the flags (each with timestamp + verbatim quote),
     the overall summary, and the **re-class recommendation + reason (PM-only)**. Buttons: **Save edits**,
     **Approve & send**, **Discard**.
  4. On **Approve**, persist `edited_text` + status `approved`; n8n picks it up to DM the instructor.
- Auth: Supabase Auth (email) is fine. Show only assigned courses per PM.

### 6.5 Eval harness — `eval/`
- `score.py` — load a labelled set (15–20 past classes: transcript + agenda + the issues a PM marked +
  the actual rating), run the engine on each, and report **precision, recall, and the correlation between
  the engine's severity and the actual rating**. Output a small summary table.
- Add a `--self-consistency N` mode (run each class N times, keep stable flags).
- **Few-shot calibration:** once the human supplies 1–2 real "good feedback" examples, insert them into the
  synthesis prompt (in `engine.py`) and re-run the eval to confirm it helped. This is how the system "gets
  better over time" — improve the prompt/rubric/examples from logged PM edits, not by retraining.

### 6.6 Uplevel integration — `uplevel.py`
**Uplevel** (`https://uplevel.interviewkickstart.com`) is IK's learning portal where class recordings and
captions live. This module fetches a class's **transcript** (and recording link) automatically so the PM
doesn't have to upload it by hand. Manual upload (§6.4) stays as the fallback.

- **Base URL / surface:** `https://uplevel.interviewkickstart.com` (pages: `/cohorts/`, `/videos/`). It is a
  Django app; those pages are backed by data endpoints — **discover the JSON/API endpoints** they call
  (browser network tab) for (a) listing a cohort's classes and (b) fetching a given class's caption file
  (.srt/.vtt). If the IK platform team can provide API docs or a service token, use that — it's the clean path.
- **Auth model:** AWS Cognito (an `access_token` + `id_token` from the IK Cognito user pool, region
  `us-west-2`) **plus** a Django `sessionid` + `csrftoken` for the uplevel host.
- **Credentials — read carefully:** do **not** hardcode, commit, or use a captured browser session — those
  cookies expire within ~an hour and are tied to one person. Instead, in priority order:
  1. **Preferred:** get a service account / long-lived API token from the IK platform team; store it as a secret.
  2. **Fallback:** implement the Cognito **refresh-token flow** — store the `refresh_token` + Cognito
     `client_id` as secrets, exchange them for fresh `access_token`/`id_token` each run, then call uplevel with
     a fresh session. Handle expiry/refresh and auth failures (Slack-alert on failure).
  All of these are read from env / a secret store at runtime (§10).
- **Function:** `fetch_transcript(class_ref) -> str` returning the `.srt/.vtt` text for a class (plus the
  recording URL), which then feeds `/analyze`. Map a queued `classes` row (cohort + date + instructor/topic)
  to the right uplevel video.
- **Robustness:** token refresh, retries, timeouts; when a class has no caption yet, fall back to
  "needs manual upload" and post a Slack note rather than failing the run.

---

## 7. n8n workflows — **build these yourself, properly**

Create each workflow in n8n, wire the nodes, handle errors, and **export each as JSON into an `/n8n` folder**
in the repo so it's version-controlled and importable. Use n8n credentials for all secrets.

**WF1 — Monday ingest & notify**
- Trigger: Schedule (Mon ~09:00 IST).
- Node: HTTP Request → engine `POST /ingest`.
- Node: IF count > 0 → Slack node → post to the PM group channel:
  `":mag: {count} classes flagged this week, awaiting transcripts → {UI_URL}"` plus a short list.
- Error branch: on non-2xx, Slack-alert the channel with the error.

**WF2 — Analyse on upload** *(only if the UI delegates analysis to n8n; otherwise the UI calls `/analyze` directly)*
- Trigger: Webhook (the UI calls it after an upload) **or** skip if the UI calls `/analyze` itself.
- Node: HTTP Request → engine `POST /analyze` (transcript + context + class_id).
- Node: Slack → "Draft ready for {course} / {instructor} ({class_date}). Re-class: {yes/no/maybe}."
- Error branch: Slack-alert "Analysis failed for {class}: {reason}".

**WF3 — Approve & deliver**
- Trigger: Webhook from the UI on "Approve & send" (carries class_id + the approved text + instructor handle),
  **or** a Postgres-poll for rows newly in `approved`.
- Node: Discord node → DM the instructor the approved/edited feedback.
- Node: HTTP/DB → set status `sent`, write `sent_at`, log `sent`.
- Node: Slack (optional) → "Sent feedback to {instructor} for {class}."
- Error branch: Slack-alert on delivery failure; do **not** mark `sent`.

**WF4 — Reminders & health**
- Trigger: Schedule (e.g. daily).
- Node: query classes stuck in `needs_transcript` > 24h → Slack-remind the PM.
- (Optional) ping engine `/health`; Slack-alert if down.

> Build WF1 and WF3 first (the core loop). WF2 is optional depending on whether the UI calls `/analyze`
> directly. Keep business rules out of n8n where possible — n8n triggers and reaches out; the engine and
> the DB hold the logic.

---

## 8. Notifications

**Slack (PM group channel) — all PM-facing alerts:**
- Monday: classes flagged + link to the UI.
- Drafts ready for review (with the re-class flag inline).
- Errors (ingest failed, analysis failed, delivery failed).
- Reminders (transcript not uploaded).
- Keep messages short, scannable, and linked to the exact class in the UI.

**Discord (DM) — instructor delivery only:** the approved/edited feedback text, after PM approval. Never
include the rating or the re-class call.

> Both channels are config (tokens + channel/guild IDs in n8n credentials). If the team later wants
> instructor delivery on Slack too, it's a one-node swap — keep it configurable.

---

## 9. Build order (milestones) + acceptance criteria

| # | Milestone | Done when… |
|---|---|---|
| M1 | Postgres + `db.py` + tests | schema applied; CRUD + audit functions pass unit tests |
| M2 | Metabase ingest (`metabase.py`) + `/ingest` | a real Monday pull writes correct `classes` rows for assigned courses |
| M3 | Persist analysis | `/analyze` writes `analyses` + `feedback(draft)` and sets `draft_ready`; idempotent |
| M4 | n8n **WF1** | Monday trigger pulls + posts the Slack summary |
| M5 | UI: queue + upload + trigger analysis | PM can see the queue, upload transcript+agenda, get a draft |
| M6 | UI: review + edit + approve | PM can edit, approve; `edited_text` + `approved` persisted |
| M7 | n8n **WF3** | approval DMs the instructor on Discord; status `sent` + audit |
| M8 | Slack alerts (WF1/WF2/WF4) + reminders | all notification paths fire, including error branches |
| M9 | Eval harness + few-shot | precision/recall + severity-vs-rating reported on the labelled set |
| M10 | Deploy + secrets + monitoring | service on Cloud Run/Render, UI on Vercel, Postgres managed, n8n live; secrets in env/credential stores; health alerting on |

Run the existing engine tests (`python -m unittest test_engine`) after any change to `engine.py`.

---

## 10. Configuration & secrets (ask the human for these)

Provide via environment variables / n8n credentials — **never hardcode**:
- `ANTHROPIC_API_KEY`
- **Metabase**: base URL, API key (or session), the saved card ID(s) or SQL for the weekly ratings, and the
  list of assigned courses + the exact column names returned.
- `DATABASE_URL` (Postgres — Supabase or Neon).
- **Slack**: bot token + the PM group channel ID.
- **Discord**: bot token + how instructors are addressed (user IDs / a mapping).
- `UI_URL` (for links in Slack).
- **Uplevel** (transcript source): base URL `https://uplevel.interviewkickstart.com` + a durable credential —
  a platform-issued API/service token, **or** the Cognito `client_id` + a `refresh_token` for the refresh-token
  flow (§6.6). **Never** the captured browser cookies (they expire and are user-scoped).

Also get from the human: **where the class agenda comes from** (until then the PM pastes it in the UI), and
**1–2 real "good feedback" examples** for few-shot calibration.

---

## 11. Production requirements (non-functional)

- **Secrets** in env / credential stores only; nothing in the repo.
- **Retries + timeouts** on every network call (the engine already does; do the same in `metabase.py`/`db.py`).
- **Validation** of every external payload (engine validates LLM output already; validate Metabase rows too).
- **Idempotency** via DB unique constraints + the engine's content hash.
- **Structured logging** everywhere; log run cost/latency (already in `meta`).
- **Error handling → Slack**: any failure in ingest/analysis/delivery posts a clear alert and leaves state
  recoverable (don't half-write).
- **Tests**: unit tests for `db.py`, `metabase.py` (mock the HTTP), and the eval harness; keep the engine tests green.
- **Deploy targets**: engine service → Cloud Run / Render (free); UI → Vercel (free); Postgres → Supabase / Neon
  (free); n8n → cloud or self-hosted. Service scales to zero between weekly runs — fine.
- **Observability**: a simple cost/latency view (sum `analyses.cost_usd`) and the `audit_log` are enough to start.

---

## 12. Out of scope (for now)
- Full uplevel auto-fetch (§6.6) can follow once the manual-upload path works; manual upload is the fallback.
- The read-only "advisor" LLM over the audit log + ratings (a later phase).
- Re-class *scheduling* (the system recommends and records the decision; actually re-running a class is manual).

---

*Build NP-first, prove it with the eval harness, then roll out to the other three teams. Keep the human in
the loop on every send. Ask when unsure.*
