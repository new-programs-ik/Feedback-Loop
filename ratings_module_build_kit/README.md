# Ratings & Feedback — Analysis Engine + Worker

Two jobs in one Python service:

1. **The AI feedback engine** — reads a low-rated class transcript (+ the class agenda and
   materials) and returns per-dimension **flags** (timestamp + verbatim quote), the coaching
   **feedback** note, and a PM-only **reclass** recommendation.
   Pipeline: `parse → chunk by time → extract findings per window (LLM) → synthesise + verify + write (LLM)`.
   Model is pinned in `Config` (engine.py).
2. **The ratings sync (Feedback Loop v3)** — pulls every class session from the team's ratings
   source (the Google Sheet), parses cohorts, resolves instructor names through
   aliases, and saves each row; the database scores it (the Class Sentiment Score) in the same
   statement and the band decides which classes reach the "Needs analysis" queue. Newly flagged
   classes get a Slack card to the course's people.

## Files
| File | What it is |
|---|---|
| `engine.py` | The core engine (parse, chunk, extract, synthesise, validate, report) + CLI |
| `video.py`, `vimeo.py`, `materials_fetch.py` | Video-frames stage, Vimeo captions, materials-by-link |
| `store.py` | Async write-back of an analysis to the `classes` / `analyses` tables |
| `service.py` | FastAPI HTTP wrapper: `/analyze*`, `/transcript`, `/revise`, `/dry-run`, `/sync-ratings`, `/health` |
| `ratings_source.py` | The "where do ratings come from" seam (canonical row contract) |
| `sheet_source.py` | Reads the ratings sheet |
| `course_rules.py` | Cohort text → course label, session kind, region (mirrors `analysis/ratings_data.py`) |
| `cohort_parse.py` | Cohort labels → course / region / intake window / ordinal / cohort no. / audience (pure) |
| `instructor_match.py` | Name normalisation (twin of SQL `normalize_person_name`) + duplicate-name suggestions (pure) |
| `ratings_store.py` | psycopg2 persistence: cohorts, topics, the scored upsert, notifications, sync-run metrics |
| `ratings_sync.py` | One sync run start to finish |
| `notify.py` | Slack cards (plain httpx, no slack-sdk) |
| `decision.py` | LEGACY rule v1/v2 — kept for one release so the old read-out can sit beside the score |
| `test_*.py` | Offline tests (no API key, no database, no network) |
| `.env.example` | All config/secrets — copy to `.env`, never commit |
| `requirements.txt` | Dependencies (upper-bounded on purpose — see the file header) |

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

## Run — service
```bash
uvicorn service:app --port 8000
```
| Endpoint | Purpose |
|---|---|
| `GET /health` | liveness, the pinned model, the build, the active scoring-config version, `rule_version`, `database` (ok / unreachable from this instance), `jobs_running` |
| `POST /dry-run` | `{cues, windows, est_tokens}` — cheap pre-check, no API key |
| `POST /transcript` | captions from a Vimeo URL |
| `POST /analyze` | `{result, meta}` — the full analysis (needs `ANTHROPIC_API_KEY`) |
| `POST /analyze-async` | same, in the background, written straight to the database |
| `POST /revise` | rewrite a draft per the PM's instruction |
| `POST /sync-ratings` | one ratings sync in the background ("Sync now"; body `{"full": true}` rewrites every row) |
| `POST /sync-ratings/cron` | the same sync, started by the database's schedule with a single-use token instead of the key |
| `POST /uplevel/find` | the class's recording on UpLevel: `{status, matches}` ranked with reasons; status `ok` / `none` / `not_connected` / `expired` / `unreachable` (`uplevel.py`) |
| `POST /uplevel/check` | Admin › UpLevel's "Test connection": one small search, status recorded |
| `POST /ai-credit/check` | is the Claude API credit still empty? A one-token request, cached 90 seconds |

If `WORKER_API_KEY` is set, every POST needs `Authorization: Bearer <it>`.

## The ratings sync (what one run does)
1. Fetch every class row from the source (the sheet). On the sheet, columns
   are read **by header name**; a renamed required column fails the run loudly. When a tab has both
   `Topic` and `Class`, `Class` is the class name (the Agentic tab's `Topic` is the session kind).
2. Per row: parse the cohort labels (`cohort_parse.py`) → upsert cohorts → resolve the instructor
   through `instructors` + `instructor_aliases` (exact normalised spelling only) → resolve the
   topic → upsert the class row; the statement calls `score_class_rating(...)` with
   `course_priors(course_id)` and the active `scoring_configs` row, so the score, band, action and
   flags are stored with the row and `decision` follows the action unless a PM froze it.
3. After the loop: suggestions for unresolved names (`instructor_match.suggest`), Slack cards to
   the course's members (`course_members`, falling back to `course_handlers`), metrics into
   `sync_runs`, and an optional `${UI_URL}/api/revalidate` ping.

Setup for the sheet: `docs/GOOGLE_SHEET_SYNC_SETUP.md` (service-account key + share the sheet).

## Tests
```bash
.venv/Scripts/python -m unittest            # everything, fully offline
.venv/Scripts/python -m unittest test_cohort_parse test_instructor_match test_ratings_sync -v
```

## Production notes
- **Config** (engine.py): model, window size, retries, timeout, repair attempts, pricing for cost reporting.
- **Robustness**: SDK retries + timeout; the model's JSON is validated against a schema and re-asked once if malformed.
- **Cost/latency**: taken from real API usage and written to `run.json` / returned in `meta`.
- **Secrets**: read from the environment (`.env` locally; Render env vars in production).
- **Docker**: every module `service.py` imports (directly, through the sync, or inside a function)
  is listed in the `Dockerfile` COPY line and must not appear in `.dockerignore`. `test_packaging.py`
  walks the imports and fails when one is missing (23 Sep 2026: `uplevel.py` was left out and every
  UpLevel lookup crashed on the server while every test passed).
