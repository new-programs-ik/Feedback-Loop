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

Three files at the top, four folders of modules, and the tests. A module imports another by its
folder: `from feedback import engine as E`, `from ratings import ratings_store`.

| Where | What it is |
|---|---|
| `service.py` | The web endpoints (FastAPI): `/analyze*`, `/transcript`, `/revise`, `/dry-run`, `/sync-ratings`, `/uplevel/*`, `/health`. The server starts it as `uvicorn service:app`. |
| `config.py` | Loads `.env` |
| `store.py` | The analysis rows in the database: claim a class, save the result, mark a failure, saved integration status and sessions |
| **`feedback/`** | **The AI analysis of a class** |
| `feedback/engine.py` | The engine: prompts, the pipeline (map, windows, synthesis, self-check), validation, cost. Also a CLI. |
| `feedback/video.py` | The video check: a screenshot every two minutes, described one at a time |
| `feedback/materials_fetch.py` | Class materials from a link (switched off on the form for now) |
| **`recordings/`** | **Where a recording and its captions come from** |
| `recordings/vimeo.py` | Vimeo captions and the video file |
| `recordings/uplevel.py` | Finds the class's Vimeo link on UpLevel |
| **`ratings/`** | **The ratings sync** |
| `ratings/ratings_sync.py` | One sync run start to finish |
| `ratings/ratings_source.py`, `ratings/sheet_source.py` | Where ratings come from (the seam, and the Google Sheet reader) |
| `ratings/course_rules.py` | Cohort text → course label, session kind, region (mirrors `analysis/ratings_data.py`) |
| `ratings/cohort_parse.py` | Cohort labels → course / region / intake window / ordinal / cohort no. / audience (pure) |
| `ratings/instructor_match.py` | Name normalisation (twin of SQL `normalize_person_name`) + duplicate-name suggestions (pure) |
| `ratings/ratings_store.py` | Database writes for the sync: cohorts, topics, the scored upsert, notifications, sync-run metrics |
| `ratings/decision.py` | LEGACY rule v1/v2 — kept for one release so the old read-out can sit beside the score |
| **`reporting/`** | **What the worker sends out** |
| `reporting/notify.py` | Slack cards (plain httpx, no slack-sdk) |
| `reporting/reports.py` | The weekly and monthly reports |
| **`tests/`** | Offline tests (no API key, no database, no network). `conftest.py` beside this README cuts every test run off from the real services. |
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
python -m feedback.engine --dry-run transcript.srt             # parse + chunk only, no API
python -m feedback.engine transcript.srt --course "Python for ML" \
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
.venv/Scripts/python -m pytest -q                             # everything, fully offline
.venv/Scripts/python -m pytest -q tests/test_video.py         # one file
```

## Production notes
- **Config** (engine.py): model, window size, retries, timeout, repair attempts, pricing for cost reporting.
- **Robustness**: SDK retries + timeout; the model's JSON is validated against a schema and re-asked once if malformed.
- **Cost/latency**: taken from real API usage and written to `run.json` / returned in `meta`
  (`tokens_in` is everything the model read; `cache_read_tokens` / `cache_write_tokens` show the
  cached share, priced at 0.1x / 1.25x input).
- **Prompt caching**: every extraction window repeats the same block (the class context with the
  whole-session map, the rubric, the severity bars); only the transcript slice differs. That block
  is sent as a separate text block marked for caching (`build_extract_parts`), so windows 2 onward
  read it at a tenth of the price. The prompt text is unchanged (a test compares it byte for byte).
  Measured on a 3 h 46 min class, 25 Sep 2026: 9,397 tokens written once and read 7 times, about
  $0.11 (11%) off the class.
- **Secrets**: read from the environment (`.env` locally; Render env vars in production).
- **Docker**: the image copies `service.py`, `config.py`, `store.py` and the four folders
  (`feedback/`, `recordings/`, `ratings/`, `reporting/`). A new module goes inside one of those
  folders and is then in the image; a new folder needs its own `COPY` line. `tests/test_packaging.py`
  walks every import, and also builds the image's exact layout in a temporary folder and imports
  every module there (23 Sep 2026: `uplevel.py` was left out and every UpLevel lookup crashed on the
  server while every test passed).
