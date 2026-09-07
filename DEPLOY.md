# Deployment guide

Three pieces, all live today. This guide covers how each one is deployed, the exact order of
steps for the v3 release, and how to roll back.

| Piece | What | Where |
|---|---|---|
| **Database** | Supabase — Postgres, sign-in, row-level security | One Supabase project, **shared by local work and production** |
| **Website** | Next.js (`web/`) | **Vercel** → https://feedback-loop-ten.vercel.app · auto-deploys on push to `main` |
| **Worker** | Python FastAPI (`ratings_module_build_kit/`) — the hourly ratings sync **and** the AI analysis engine | **Render**, as a Docker container · auto-deploys on push to `main` |

> 🧑‍💻 **Setting the worker up click by click (non-technical):** [docs/RENDER_SETUP.md](docs/RENDER_SETUP.md).
> **Connecting the ratings sheet:** [docs/GOOGLE_SHEET_SYNC_SETUP.md](docs/GOOGLE_SHEET_SYNC_SETUP.md).

---

## 1. The v3 release, in order

**Only on Bishal's word, after his local walkthrough.** One fact shapes everything below: local
work and production share one database. Migrations 0015–0023 are *additive* (new tables, columns
and functions; nothing dropped or renamed) and *idempotent* (safe to run twice). Applying them
changes nothing on the live site until the new code is deployed.

### Before you start

- The Google service-account key file is at `ratings_module_build_kit/google-sa.json` and the
  ratings sheet is shared with that account as **Viewer**.
- Tests are green: worker `python -m unittest` (285), web `npm test` (107), web `npx tsc --noEmit`,
  and `supabase/test_scoring_sql.py` against the database (94 fixture cases).
- Take a backup:
  ```bash
  ./ratings_module_build_kit/.venv/Scripts/python analysis/db_backup.py
  ```
  It writes one JSON-lines file per table plus a `manifest.json` to
  `_archive/backups/<UTC timestamp>/` (gitignored). Add `--tables class_ratings,cohorts` for a
  subset, `--out <folder>` for another destination.

### Step 1 — apply migrations 0015 → 0023

`apply_migrations.py` reads `DATABASE_URL` from `ratings_module_build_kit/.env` and runs each file
in its own transaction. Run the seven new files by name, in order:

```bash
# from the repo root
P=./ratings_module_build_kit/.venv/Scripts/python
$P supabase/apply_migrations.py 0015_scoring_configs.sql
$P supabase/apply_migrations.py 0016_instructor_identity.sql
$P supabase/apply_migrations.py 0017_cohorts_topics.sql
$P supabase/apply_migrations.py 0018_course_members.sql
$P supabase/apply_migrations.py 0019_rollups_queue_sync.sql
$P supabase/apply_migrations.py 0020_learner_contract.sql
$P supabase/apply_migrations.py 0021_tighten_reads.sql
$P supabase/apply_migrations.py 0022_accept_merges_records.sql
$P supabase/apply_migrations.py 0023_flip_share_definition.sql
```

| File | What it adds |
|---|---|
| `0015_scoring_configs.sql` | `scoring_configs` (versions 1–6 seeded; version 1 becomes active if nothing is), the scoring function `score_class_rating()`, `course_priors()`, `apply_scoring_config()` (activate + re-score every class), `scoring_whatif_summary()` (preview), `class_score_history`, the `sentiment_*` columns on `class_ratings`. Scores every class that has never been scored. |
| `0016_instructor_identity.sql` | `instructor_aliases`, `instructor_match_suggestions`, `instructor_merges`, the accept / reject / alias / merge / undo functions, `instructor_canonical` on class rows. Links exact spellings only. |
| `0017_cohorts_topics.sql` | Parsed cohort identity on `cohorts`; `topics` and `topic_aliases`; `cohort_id`, `cohort_ids`, `topic_id`, `week_no` on class rows. |
| `0018_course_members.sql` | `course_members` (copies today's handlers and PM assignments once), course colour and initials, `default_course_for()`, membership linked to the login on sign-in. |
| `0019_rollups_queue_sync.sql` | The rollup views, `queue_rows()`, the extra sync metrics, `report_shares`. |
| `0020_learner_contract.sql` | The empty learner tables (`learners`, `learner_ratings`, `learner_import_runs`). |
| `0021_tighten_reads.sql` | Ratings tables readable by staff only. |
| `0022_accept_merges_records.sql` | Accepting a duplicate-name suggestion merges the spelling's own record when it has one (undoable), instead of leaving an empty identity behind. |
| `0023_flip_share_definition.sql` | One definition of "flips on one vote" shared with the validation study (share of every class in the window). |

Migrations 0012–0014 are already applied; re-running them is harmless. Do **not** re-run
`0000_drop_legacy_m1.sql` on a database with real data (it is the one-time legacy drop) — that is
why the files are listed by name above rather than run as a batch.

### Step 2 — the two Vault secrets for the hourly timer

Migration `0013_ratings_cron.sql` schedules two jobs (`ratings-sync-hourly` at :00 and
`ratings-sync-hourly-retry` at :05) that call the worker's `POST /sync-ratings`. The job reads the
worker's address and the shared secret from **Supabase Vault**; until both exist it logs
"vault secrets worker_url/worker_api_key not set — skipping" and does nothing. Create them once,
by hand, in the Supabase SQL editor (never in a file):

```sql
select vault.create_secret('https://<your-worker>.onrender.com', 'worker_url');
select vault.create_secret('<the same value as WORKER_API_KEY on Render>', 'worker_api_key');
```

If 0013 has not been applied yet, apply it *after* the worker is live:
`$P supabase/apply_migrations.py 0013_ratings_cron.sql`.

### Step 3 — the worker's environment on Render

Set these on the worker service (Render → the service → Environment). Never in code.

| Variable | Needed? | What it is for |
|---|---|---|
| `ANTHROPIC_API_KEY` | **yes** | Runs the AI analysis. |
| `DATABASE_URL` | **yes** | The sync writes every class row here; background analyses save their result here. |
| `WORKER_API_KEY` | **yes** in production | Shared secret. Every POST must carry `Authorization: Bearer <it>`; the same value goes on the web app and into Vault (step 2). |
| `RATINGS_SHEET_ID` | **yes** for the sync | The long id in the sheet's URL. |
| `GOOGLE_SA_JSON_FILE` | **yes** for the sync | Path to the service-account key. On Render, upload the key as a **Secret File** named `google-sa.json` and set this to `/etc/secrets/google-sa.json`. (`GOOGLE_SA_JSON` with the key's JSON content is the alternative; the file wins.) |
| `RATINGS_SOURCE` | optional | `sheet` (default) or `metabase` (later). |
| `RATINGS_SHEET_TABS` | optional | Default `MLSU_Live_Class_Poll,Agentic_AI_Live_Class_Poll`. |
| `SLACK_BOT_TOKEN`, `SLACK_PM_CHANNEL_ID` | recommended | The flag cards and the "sync failed" alerts go to this channel. The bot needs `users:read.email` to mention people by their IK email. |
| `UI_URL` | recommended | The site the cards link to and the sync pings after a green run: `https://feedback-loop-ten.vercel.app`. |
| `NOTIFY_MAX_AGE_DAYS`, `NOTIFY_MAX_PER_RUN` | optional | Slack guard rails (defaults 10 days, 25 cards per run; `NOTIFY_MAX_PER_RUN=0` holds every card). |
| `VIMEO_ACCESS_TOKEN` | recommended | Transcripts (and video frames) from Vimeo. See [docs/VIMEO_VIDEO_ACCESS.md](docs/VIMEO_VIDEO_ACCESS.md). |
| `VIDEO_MAX_FRAMES` | optional | Frames sampled per video analysis (default 60; **40** is the safe value on Render's free tier). |
| `VIDEO_DISABLED` | optional | `1` = kill-switch; analyses run transcript-only. |
| `GOOGLE_ACCESS_TOKEN` | optional | Only for private Google Drive materials. |
| `LEARNER_SOURCE` | leave unset | `POST /sync-learners` answers 501 until a learner-level source exists. |
| `METABASE_*` | later | Only when `RATINGS_SOURCE=metabase`. |

Render injects `PORT`; the image binds to it. `RENDER_GIT_COMMIT` is also injected and shows up
as `commit` on `/health`.

### Step 4 — the website's environment on Vercel

| Variable | What it is for |
|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | The Supabase project URL. |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | The publishable (anon) key; safe in the browser, protected by row-level security. |
| `SUPABASE_SERVICE_ROLE_KEY` | Server-only. Used for the few writes that must bypass row-level security (a PM's what-if proposal). |
| `ANALYSIS_WORKER_URL` | The worker's URL. |
| `WORKER_API_KEY` | The same secret as on the worker. The web app sends it when it asks the worker to analyse or to sync, and requires it on `POST /api/revalidate` (the worker's "fresh data" ping). Without it that endpoint refuses everything. |
| `NEXT_PUBLIC_SUPPORT_EMAIL` | Optional. The contact shown on the error page (defaults to the New Programs address). |

### Step 5 — merge and deploy

Merge `local-work` into `main`. Vercel builds the website; Render rebuilds the worker image. Wait
for both to go green.

### Step 6 — smoke checks

1. `GET https://<your-worker>/health` → `status: ok`, `commit` = the merged commit,
   `scoring_config_version` = the active version (1 unless changed), `sheet_configured: true`,
   `slack_configured: true`, `ffmpeg: true`, `anthropic_key: true`.
2. Sign in → you land in your own course (an admin with no membership lands on `/team`).
3. An old Slack link such as `/ratings?focus=<id>` redirects to `/c/<course>/queue?focus=<id>`.
4. **Admin › Sync → Sync now** → a green run within a minute or two, with rows fetched, rows
   scored and the version (`v1`); unmapped labels and unresolved names are counted, not fatal.
5. One Slack card arrives in the PM channel for a recently flagged class (only classes from the
   last 10 days are pinged, at most 25 per run).
6. **Admin › Scoring** → open a draft, change a setting → the preview on the right updates.
   Do not activate anything unless that has been decided.
7. From a queue row, **Analyze** → the New analysis form arrives prefilled → run one analysis
   end to end and mark it approved.

### Step 7 — watch the first hourly run

Admin › Sync shows every run: status, trigger (`cron` or `manual`), duration, fetched, upserted,
scored, the band counts, unparsed cohorts, unresolved names, suggestions. A failed run also posts a
warning to the Slack channel. Give it a day before calling it done.

---

## 2. Rollback

Three levers, in any combination:

- **Code.** Vercel and Render both keep previous deployments — promote (Vercel) or redeploy
  (Render) the one before. The new tables and columns do not affect the old code.
- **Scoring.** Admin › Scoring → **Roll back to this** on the previously active version (version 1
  is the manager's original). Every class is re-scored in one step; history rows and an audit row
  are written.
- **The timer.** Pause the hourly sync from the Supabase SQL editor:
  ```sql
  select cron.unschedule('ratings-sync-hourly');
  select cron.unschedule('ratings-sync-hourly-retry');
  ```
  Re-apply `0013_ratings_cron.sql` to switch it back on.

**Restoring rows from a backup** is a manual, table-by-table step on purpose. Each
`<table>.jsonl` holds one row per line exactly as Postgres returned it (`row_to_json`); put rows
back with a small script or by hand, never with a blanket truncate-and-load on the live database.

---

## 3. The worker (a portable container)

The worker ships as a Docker image (`ratings_module_build_kit/Dockerfile`), which also installs
**ffmpeg** for the video-frames stage. It holds nothing between requests and stores no files:
transcripts, materials and frames are used for one analysis and discarded. It does write to the
database — the sync writes class rows and the background analysis writes its result — which is
why `DATABASE_URL` is required. Every module the service imports is listed in the Dockerfile's
`COPY` line and must not appear in `.dockerignore` (a mismatch crashes the container at start).

Runs on any container platform: Render today; AWS App Runner / ECS, Google Cloud Run, Azure
Container Apps, Fly.io, Railway, or internal Kubernetes would all work.

```bash
cd ratings_module_build_kit
docker build -t ik-ratings-worker .
docker run -p 8000:8000 -e ANTHROPIC_API_KEY=... -e DATABASE_URL=... -e WORKER_API_KEY=... ik-ratings-worker
# GET http://localhost:8000/health
```

`GET /health` reports the model, the build (`commit`), the SDK version, whether the keys are
present, whether ffmpeg was found, whether video and the self-check pass are enabled, the ratings
source, whether the sheet and Slack are configured, and the active scoring version.

---

## 4. The website (Next.js)

Vercel, root directory `web/`, build `npm run build`, start `npm start`. Any Node host or
container works the same way. Environment variables are in step 4 above.

---

## 5. Wiring and security

- `ANALYSIS_WORKER_URL` on the web app points at the worker; `UI_URL` on the worker points back at
  the site.
- The **same** `WORKER_API_KEY` sits on the web app, on the worker and in Vault, so only the web app
  and the timer can call the worker, and only the worker can purge the site's caches.
- Sign-in is Google, restricted to `@interviewkickstart.com`; access is enforced by row-level
  security in Postgres. Ratings tables are readable by staff (admin / pm) only since 0021.
- Rotate anything that was shared in chat during development (Supabase keys, the Claude key, the
  database password), and treat `DATABASE_URL` like a password.
- Optional: enable the Supabase **Custom Access Token** hook so the role rides in the sign-in
  token (see `supabase/README.md`).
