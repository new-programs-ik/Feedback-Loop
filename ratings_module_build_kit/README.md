# Ratings & Feedback — Analysis Engine + Service

Reads a low-rated class transcript (+ the class agenda) and returns three things:

1. **flags** — per-quality-dimension findings, each with a timestamp + verbatim quote
2. **feedback** — the coaching message for the instructor
3. **reclass** — a PM-only recommendation on whether the class needs to be re-taught

Pipeline: `parse → chunk by time → extract findings per window (LLM) → synthesise + verify + write (LLM)`.
Model is pinned to **Claude Sonnet 4.6** in `Config` (engine.py).

## Files
| File | What it is |
|---|---|
| `engine.py` | The core engine (parse, chunk, extract, synthesise, validate, report) + CLI |
| `service.py` | FastAPI HTTP wrapper so **n8n** can call the engine |
| `schema.sql` | PostgreSQL schema for the store (queue, analyses, drafts, audit log) |
| `db.py` | Data-access layer over the store (SQLAlchemy Core) — §6.2 (**M1**) |
| `apply_schema.py` | One-command apply of `schema.sql` to `DATABASE_URL` |
| `test_engine.py` | Unit tests for the deterministic parts (no API key needed) |
| `test_db.py` | Unit tests for `db.py` (run on in-memory SQLite, no server needed) |
| `.env.example` | All config/secrets (§10) — copy to `.env`, never commit |
| `requirements.txt` | Dependencies |

## Setup
```bash
# Windows note: the bare `python` may be the Microsoft Store shim — use `py -3`.
py -3 -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # macOS/Linux: .venv/bin/python
cp .env.example .env                       # then fill it in; .env is gitignored
export ANTHROPIC_API_KEY=sk-ant-...        # or set it in .env — never hardcode the key
```

## Run — CLI
```bash
python engine.py --dry-run transcript.srt                      # parse + chunk only, no API
python engine.py transcript.srt --course "Python for ML" \
    --topic "pandas indexing" --instructor "Justin" \
    --rating 4.47 --agenda agenda.txt
```
Outputs land in `outputs/<run_id>/` as `result.json`, `feedback.md`, `run.json`. Re-running the
same transcript+context is a no-op (idempotent); pass `--force` to override.

## Run — service (for n8n)
```bash
uvicorn service:app --port 8000
```
| Endpoint | Purpose |
|---|---|
| `GET /health` | liveness + the pinned model |
| `POST /dry-run` | `{cues, windows, est_tokens}` — cheap pre-check, no API key |
| `POST /analyze` | `{result, meta}` — the full analysis (needs `ANTHROPIC_API_KEY`) |

n8n calls `/analyze` with an HTTP Request node, passing `{transcript, course, topic, instructor, rating, agenda}`.
Deploy the service on any free tier (Cloud Run / Render / Railway) and set the API key in its environment.

## Store + data-access layer (M1)
Apply `schema.sql` to a Postgres database (Supabase or Neon free tier). Tables: `classes`
(the queue + status), `analyses` (engine output as JSONB), `feedback` (draft, PM edits, approval/send),
`audit_log` (append-only trail). The `feedback.edited_text` vs `draft_text` gap is the ongoing accuracy signal.

```bash
# apply the schema (idempotent) once DATABASE_URL is set:
.venv/Scripts/python apply_schema.py
```

`db.py` is the thin access layer (SQLAlchemy Core) the service and UI use:
`upsert_class` (idempotent on the natural key), `set_status`, `save_analysis`,
`save_draft`, `update_feedback`, `approve`, `mark_sent`, `log`, plus reads
`list_queue` / `get_class` / `get_audit`. Every write is transactional; the same code
runs on Postgres (prod) and SQLite (tests).

## Tests
```bash
.venv/Scripts/python -m unittest test_engine test_db -v   # engine + data-access layer
```
`test_db.py` runs entirely on in-memory SQLite — no Postgres needed — and includes a
parity check that `db.py` hasn't drifted from `schema.sql`.

## Architecture (Phase 2)
```
n8n (Mon 9am trigger, Vimeo fetch, Discord/alerts)
      │  HTTP
      ▼
engine service (Python, free hosting) ── reads ──▶ Metabase (ratings)
      │  writes
      ▼
Postgres (queue · analyses · drafts · audit)  ◀── reads/writes ──  PM UI (free hosting)
```

## Production notes
- **Config** (engine.py): model, window size, retries, timeout, repair attempts, pricing for cost reporting.
- **Robustness**: SDK retries + timeout; the model's JSON is validated against a schema and re-asked once if malformed.
- **Cost/latency**: taken from real API usage and written to `run.json` / returned in `meta`.
- **Secrets**: read from `ANTHROPIC_API_KEY` in the environment.

## What's next
- **Eval harness** — score the engine on 15–20 PM-labelled past classes (precision, recall, severity-vs-rating correlation).
- **Few-shot calibration** — drop 1–2 real "good feedback" examples into the synthesis prompt.
- **Metabase ingest** — pull the low-rated list + ratings (the engine reads Metabase directly).
- **Wiring** — the n8n flow, the store writes, and the PM UI over Postgres.
