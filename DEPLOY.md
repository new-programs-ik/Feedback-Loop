# Deployment guide

Three pieces, all live today. This guide covers how each one is deployed, the exact order of
steps for the v3 release, and how to roll back.

| Piece | What | Where |
|---|---|---|
| **Database** | Supabase — Postgres, sign-in, row-level security | One Supabase project, **shared by local work and production** |
| **Website** | Next.js (`web/`) | **Vercel** → https://feedback-loop-ten.vercel.app · auto-deploys on push to `main` |
| **Worker** | Python FastAPI (`ratings_module_build_kit/`) — the ratings sync (three times a day, India time) **and** the AI analysis engine | **Render**, as a Docker container · auto-deploys on push to `main` |

> 🧑‍💻 **Setting the worker up click by click (non-technical):** [docs/RENDER_SETUP.md](docs/RENDER_SETUP.md).
> **Connecting the ratings sheet:** [docs/GOOGLE_SHEET_SYNC_SETUP.md](docs/GOOGLE_SHEET_SYNC_SETUP.md).

---

## 1. Releasing a change, in order

One fact shapes everything below: local work and production share one database. Every migration
is *additive* (new tables, columns, functions and policies; nothing dropped or renamed) and
*idempotent* (safe to run twice). Applying one changes nothing on the live site until the code
that uses it is deployed, so the order is always: migration, then code.

### Before you start

- The Google service-account key file is at `ratings_module_build_kit/google-sa.json` and the
  ratings sheet is shared with that account as **Viewer**.
- Tests are green: worker `pytest -q` (435), web `npm test` (144) and `npx tsc --noEmit` and
  `npx next build`, `supabase/test_scoring_sql.py` against the database (120 fixture cases), and
  `supabase/test_worker_sql.py` (the worker's statements run against the real database and
  rolled back; the unit tests cannot see a statement Postgres refuses).
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
| `0024_trust_approval_from_min_answers.sql` | The scoring function reads a `thin` block: below a number of approval answers a passing approval does not count (scoring version 9, since replaced). |
| `0025_too_few_responses_low_rating_read.sql` | `min_votes.low_rating_line`: under the response floor a class rated below the line is still read (scoring version 10, live). |
| `0026_kb_export_views.sql` | The `kb` schema (three read-only views) and the `kb_reader` role for other teams' knowledge bases. |
| `0027_sync_schedule.sql`, `0031_sync_checks_on_the_hour.sql` | The scheduled sync: `sync_triggers` (single-use tokens), `app_settings` (worker address, hours, zones), the trigger functions, the `pg_cron` checks. |
| `0028_sync_fingerprints.sql` | `class_ratings.row_hash` and `sync_runs.rows_unchanged`: the sync skips rows the sheet did not change. |
| `0029_tighten_access.sql` | Share links, course members and handlers, scoring versions and audit inserts are staff-only. |
| `0030_sync_heartbeat.sql` | `sync_runs.heartbeat_at`: a long run says it is alive; stale means no heartbeat. |

Migrations 0012–0014 are already applied; re-running them is harmless. Do **not** re-run
`0000_drop_legacy_m1.sql` on a database with real data (it is the one-time legacy drop) — that is
why the files are listed by name above rather than run as a batch.

### Step 2 — the schedule (no secrets to paste)

Migrations `0027` and `0031` create the schedule. `pg_cron` runs a check at :00, :05, :30 and :35
every hour; the check fires when a configured time zone's local clock reads one of the configured
hours. Today: **10:00, 12:00 and 14:00 India time**, each with a retry five minutes later for a
worker that was asleep. Every run mints a single-use token in `sync_triggers` and posts it to the
worker's `POST /sync-ratings/cron`; the worker spends the token (unused, under ten minutes old)
before it starts. No key is stored in the database.

Three rows in `app_settings` drive it; change them with an `update`, no migration needed:

| Key | Value today | Meaning |
|---|---|---|
| `worker_url` | `https://feedback-loop-50w0.onrender.com` | Where the worker lives. Change it if the worker moves. |
| `sync_local_hours` | `10,12,14` | The local hours to run at. |
| `sync_timezones` | `Asia/Kolkata` | The zone(s) those hours are read in. Adding a second zone is one edit. |

Admin › Sync shows every run and counts "scheduled runs not picked up" (a token minted that the
worker never spent), which is the sign the worker was unreachable.

### Step 3 — the worker's environment on Render

Set these on the worker service (Render → the service → Environment). Never in code.

| Variable | Needed? | What it is for |
|---|---|---|
| `ANTHROPIC_API_KEY` | **yes** | Runs the AI analysis. |
| `DATABASE_URL` | **yes** | The sync writes every class row here; background analyses save their result here. |
| `WORKER_API_KEY` | **yes** in production | Shared secret. Every POST must carry `Authorization: Bearer <it>`; the same value goes on the web app. (The scheduled sync does not use it: it carries a single-use token instead.) |
| `RATINGS_SHEET_ID` | **yes** for the sync | The long id in the sheet's URL. |
| `GOOGLE_SA_JSON_FILE` | **yes** for the sync | Path to the service-account key. On Render, upload the key as a **Secret File** named `google-sa.json` and set this to `/etc/secrets/google-sa.json`. (`GOOGLE_SA_JSON` with the key's JSON content is the alternative; the file wins.) |
| `RATINGS_SYNC_FULL` | optional | `1` forces the next sync to rewrite every row instead of only the rows the sheet changed (after a logic change). |
| `RATINGS_SHEET_TABS` | optional | Default `MLSU_Live_Class_Poll,Agentic_AI_Live_Class_Poll`. |
| `SLACK_BOT_TOKEN`, `SLACK_PM_CHANNEL_ID` | recommended | The flag cards and the "sync failed" alerts go to this channel. The bot needs `users:read.email` to mention people by their IK email. |
| `UI_URL` | recommended | The site the cards link to and the sync pings after a green run: `https://feedback-loop-ten.vercel.app`. |
| `NOTIFY_MAX_AGE_DAYS`, `NOTIFY_MAX_PER_RUN` | optional | Slack guard rails (defaults 10 days, 25 cards per run; `NOTIFY_MAX_PER_RUN=0` holds every card). |
| `VIMEO_ACCESS_TOKEN` | recommended | Transcripts (and video frames) from Vimeo. See [docs/VIMEO_VIDEO_ACCESS.md](docs/VIMEO_VIDEO_ACCESS.md). |
| `VIDEO_MAX_FRAMES` | optional | Frames sampled per video analysis (default 60; **40** is the safe value on Render's free tier). |
| `VIDEO_DISABLED` | optional | `1` = kill-switch; analyses run transcript-only. |
| `GOOGLE_ACCESS_TOKEN` | optional | Only for private Google Drive materials. |
| `SLACK_LEADERSHIP_CHANNEL_ID`, `REPORTS_DRIVE_FOLDER_ID` | when the reports are scheduled | The monthly and yearly reports (`reports.py`) post to Slack and upload to this Drive folder. Not scheduled yet. |

Render injects `PORT`; the image binds to it. `RENDER_GIT_COMMIT` is also injected and shows up
as `commit` on `/health`.

### Step 4 — the website's environment on Vercel

| Variable | What it is for |
|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | The Supabase project URL. |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | The publishable (anon) key; safe in the browser, protected by row-level security. |
| `SUPABASE_SERVICE_ROLE_KEY` | Server-only. Used for the few reads that must bypass row-level security (resolving a share-link token, the scheduler's token table on the Sync page). |
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

### Step 7 — watch the first scheduled run

Admin › Sync shows every run: status, trigger (`cron:Asia/Kolkata`, `cron-retry:…` or `manual`),
duration, rows read, written and unchanged, the band counts, unparsed cohorts, unresolved names,
suggestions, and "scheduled runs not picked up". A failed run also posts a warning to the Slack
channel when Slack is configured. The first run after a code change that touches the row
fingerprint rewrites every row (about eight minutes); every run after that takes seconds.

---

## 2. Rollback

Three levers, in any combination:

- **Code.** Vercel and Render both keep previous deployments — promote (Vercel) or redeploy
  (Render) the one before. The new tables and columns do not affect the old code.
- **Scoring.** Admin › Scoring → **Roll back to this** on the previously active version (version 1
  is the manager's original). Every class is re-scored in one step; history rows and an audit row
  are written.
- **The schedule.** Pause the scheduled sync from the Supabase SQL editor:
  ```sql
  select cron.unschedule('ratings-sync-check-00');
  select cron.unschedule('ratings-sync-check-05');
  select cron.unschedule('ratings-sync-check-30');
  select cron.unschedule('ratings-sync-check-35');
  ```
  Re-apply `0027_sync_schedule.sql` and `0031_sync_checks_on_the_hour.sql` to switch it back on.

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
source, whether the sheet and Slack are configured, the active scoring version, whether the
database can be reached from the worker right now (`database`: ok / unreachable, checked at most
once a minute) and how many analyses are running (`jobs_running`).

**Jobs survive a restart.** A push to `main` restarts the worker. An analysis running at that
moment is put back in the queue by the stopping instance, and every instance looks for queued
classes on its own (a minute after it starts, then every 90 seconds): the ones it was handed and
could not take, the ones the website could not hand over because the worker was asleep or could
not reach the database, and the ones a restart interrupted. A resumed class runs transcript-only
(materials and video are never stored). `RESUME_SCHEDULED=0` switches this off.

---

## 4. The website (Next.js)

Vercel, root directory `web/`, build `npm run build`, start `npm start`. Any Node host or
container works the same way. Environment variables are in step 4 above.

---

## 5. Wiring and security

- `ANALYSIS_WORKER_URL` on the web app points at the worker; `UI_URL` on the worker points back at
  the site.
- The **same** `WORKER_API_KEY` sits on the web app and on the worker, so only the web app can ask
  the worker for an analysis or a sync, and only the worker can purge the site's caches. The
  schedule does not hold the key: each scheduled run mints a single-use token in the database and
  the worker spends it.
- Sign-in is Google, restricted to `@interviewkickstart.com`; access is enforced by row-level
  security in Postgres. Ratings tables are readable by staff (admin / pm) only since 0021.
- Rotate anything that was shared in chat during development (Supabase keys, the Claude key, the
  database password), and treat `DATABASE_URL` like a password.
- Optional: enable the Supabase **Custom Access Token** hook so the role rides in the sign-in
  token (see `supabase/README.md`).

---

## 6. Backups

The Supabase free tier keeps no backups of its own, and the website, the worker and local
development all write to the one production database. Two copies exist:

**Every night (automatic).** The GitHub Actions job in `.github/workflows/nightly-backup.yml`
runs at 02:00 India time and keeps a full dump of the `public` and `kb` schemas for 14 days,
under the repository's **Actions › Nightly database backup › (the run) › Artifacts**. It needs,
once:

1. The repository set to **private** (Settings › General › Danger Zone › Change visibility).
   Artifacts can be downloaded by anyone who can read the repository, so the job refuses to run
   while it is public. Vercel and Render keep deploying from a private repository.
2. One secret, `SUPABASE_DB_URL` (Settings › Secrets and variables › Actions › New repository
   secret): the **Session pooler** string from Supabase › **Connect** (port 5432, not the
   transaction pooler on 6543), with the database password filled in.

Then press **Run workflow** once to see a green run. A failed run e-mails the repository's
owners; the message says what is missing.

**Before any change to data (by hand).** From the repository root:

```bash
./ratings_module_build_kit/.venv/Scripts/python analysis/db_backup.py
```

One JSON-lines file per table plus a manifest, under `_archive/backups/<UTC timestamp>/`
(gitignored). Put rows back table by table, as section 2 says.

**Restoring the nightly dump** needs the Postgres 17 client tools on your computer (Windows:
`winget install PostgreSQL.PostgreSQL.17`; the tools land in `C:\Program Files\PostgreSQL\17\bin`).
Download the artifact, unzip it, then, with the same connection string as the secret:

```bash
pg_restore --clean --if-exists --no-owner --no-privileges -d "<SUPABASE_DB_URL>" feedback-loop-YYYY-MM-DD.dump
```

`--clean` drops and recreates every object in the dump before loading it, so this is the
**whole database back to that night**: everything written since is lost. For one table, add
`--table=<name>` (and `--data-only` to keep today's schema); for a single row, the JSON-lines
copy and a hand-written `insert` are the safer tool.
