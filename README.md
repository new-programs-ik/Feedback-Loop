# Feedback Loop

The New Programs team's system for class quality at Interview Kickstart. It reads the team's
ratings sheet three times a day, gives every class a score and a band, tells the team which
classes need a look, and, for those, writes an AI analysis of the recording that a programme
manager reviews and sends to the instructor.

Live: **https://feedback-loop-ten.vercel.app** (sign in with an @interviewkickstart.com Google
account). This file is the front door; the detailed documents are listed at the end.

## What it does, in one pass

1. **Reads the sheet.** At 10:00, 12:00 and 14:00 India time the database asks the worker to read
   the ratings sheet. Only rows the sheet changed are written (a run takes seconds); rows a
   corrected spelling replaced are removed; rows a person acted on are never touched.
2. **Scores every class.** The Class Sentiment Score (0 to 100) comes from the rating, instructor
   approval, how many rated and how many attended. It is computed inside the database by one
   function, mirrored in Python and in the website, and pinned by one shared set of test cases so
   the three can never disagree. The live rules (scoring version 10): a class rated below 4.3 is
   always at least read; a class with fewer than 6 responses is "too few to judge" unless it is
   rated below 4.3.
3. **Bands and actions.** Excellent, Good, Average, Bad. Bad: someone watches the recording.
   Average: someone reads the transcript. Good and Excellent: nothing needed. Too few responses:
   kept an eye on. A PM can escalate any class to a video review.
4. **The queue.** Each course has a "Needs analysis" list with the reason in plain words. Confirm,
   dismiss or escalate; or start an analysis.
5. **The AI analysis.** The worker fetches the transcript from Vimeo (and, when asked, samples
   frames from the recording), reads the class in 30-minute windows with the whole-session map for
   context, checks its own findings with a second adversarial pass, and drafts the feedback note
   and the instructor summary. Every finding carries a timestamp and a quote.
6. **Review and send.** The PM edits, approves and marks the note as sent. Every step is in the
   audit trail. Analyses and feedback are kept for at least two years; transcripts are deleted
   after 20 days.

## Where things are in the app

| Where | What |
|---|---|
| `/c/<course>/overview` | The course's numbers, trend, band mix, worst classes, instructors, cohorts, modules |
| `/c/<course>/queue` | Needs analysis: Bad and Average classes with the reason; confirm, dismiss, escalate, analyse |
| `/c/<course>/classes` | Every rated class; filters by band, cohort, instructor, status; a drawer per class |
| `/c/<course>/instructors`, `/cohorts`, `/modules` | Instructor portfolios, cohort journeys, module hot-spots |
| `/c/<course>/feedback` | The AI analyses for the course; `/feedback/new` starts one |
| `/c/<course>/reports` | Weekly, monthly or custom report; print, CSV, share link |
| `/team` | All courses for leadership; `/team/queue`, `/team/instructors`, `/team/reports` |
| `/admin/scoring` | Scoring versions: draft, preview on real months, activate, roll back |
| `/admin/identity`, `/admin/people`, `/admin/sync`, `/admin/audit` | Instructor name matching, course members, sync runs, the audit trail |
| `/admin/uplevel` | The UpLevel connection that lets the New analysis form find each class's recording by itself |

Roles: **admin** (everything), **pm** (any IK staff sign-in: every course, the queue, analyses),
**learner** (no access to ratings or analyses).

## What's in this repository

| Folder | What it is |
|---|---|
| [`web/`](web/) | The website: Next.js 16, React 19, Tailwind 4, TypeScript. Deployed on Vercel. |
| [`ratings_module_build_kit/`](ratings_module_build_kit/) | The worker: Python, FastAPI. The sheet sync, the AI engine, the reports. Deployed on Render as a Docker container. |
| [`supabase/`](supabase/) | The database: migrations 0001 to 0032, the scoring function, the shared scoring fixtures, the SQL contract test. |
| [`analysis/`](analysis/) | The reference scorer (`sentiment_score.py`), the fixture builder, the formula study and the report builders. |
| [`docs/`](docs/) | The guides listed below. |

Everything is on one Supabase project (Postgres, sign-in, row-level security, the schedule).
The worker and the website share it. No secrets are in this repository: keys live in Render,
Vercel and a local `.env` that git ignores.

## Running it on your computer

Windows, one click: `start-local.bat` (builds the website once, then opens the worker on port
8000 and the website on port 3000). The manual way and the first-time setup are in
[docs/RUN_LOCAL.md](docs/RUN_LOCAL.md). Local runs use the production database, so the rules in
that guide about what not to touch matter.

Checks before any push, all of which must be green:

```
ratings_module_build_kit/.venv/Scripts/python.exe -m pytest -q       # the worker (450 tests)
cd web && npx tsc --noEmit && npx next build && npm test             # the website
ratings_module_build_kit/.venv/Scripts/python.exe supabase/test_scoring_sql.py   # the database scorer against the fixtures
ratings_module_build_kit/.venv/Scripts/python.exe supabase/test_worker_sql.py    # the worker's SQL against the real database (rolled back)
```

The last one exists because a statement can read fine and still be refused by Postgres; the
worker's unit tests have no database and cannot tell.

## Deploying

A push to `main` deploys both: Vercel rebuilds the website and Render rebuilds the worker, about
two minutes each. Database changes are migrations under `supabase/migrations/`, applied with
`supabase/apply_migrations.py`; they are additive only (nothing is dropped or renamed) because
local work and production share the database. [DEPLOY.md](DEPLOY.md) has the full procedure,
the environment variables, how to roll back, and the backups: a nightly copy of the database
(a GitHub Actions job, kept 14 days) and a one-command copy to take before any change to data.

## Changing the scoring

Scoring settings are data, not code: versions in `scoring_configs`, one active. Admin › Scoring
creates a draft, previews it on real months (band mix, analyses a week, classes that move), and
activates it; every class is re-scored in one step and the old version is one click away. Any new
rule must be added in all three scorers (`analysis/sentiment_score.py`, `web/src/lib/sentiment.ts`,
a new migration for `score_class_rating`) and pinned in `analysis/build_scoring_fixtures.py`.

## Keeping the documents true

Every change that alters what a person sees, what runs when, what is stored, or how to set
something up updates the document that describes it, in the same commit. The rule and the
checklist are in [CONTRIBUTING.md](CONTRIBUTING.md). A document that contradicts the system is a
bug.

## The documents

| Read this | When you want |
|---|---|
| [docs/USER_GUIDE.md](docs/USER_GUIDE.md) | to use the website, page by page |
| [docs/HOW_IT_WORKS.md](docs/HOW_IT_WORKS.md) | the full story: the pipeline, the score, the queue, the engine, what is stored |
| [docs/EXECUTIVE_SUMMARY.md](docs/EXECUTIVE_SUMMARY.md) | the two-page version for leadership |
| [docs/THE_AI_ANALYSIS_PROMPTS.md](docs/THE_AI_ANALYSIS_PROMPTS.md) | the exact prompts the engine uses (generated from the code) |
| [docs/RUN_LOCAL.md](docs/RUN_LOCAL.md) | to run it on your computer |
| [DEPLOY.md](DEPLOY.md), [docs/RENDER_SETUP.md](docs/RENDER_SETUP.md), [docs/GOOGLE_SHEET_SYNC_SETUP.md](docs/GOOGLE_SHEET_SYNC_SETUP.md), [docs/VIMEO_VIDEO_ACCESS.md](docs/VIMEO_VIDEO_ACCESS.md) | to deploy or connect a service |
| [docs/UPLEVEL_VIDEO_LINK.md](docs/UPLEVEL_VIDEO_LINK.md) | to find a class's recording link in UpLevel (by hand, or the automatic match) |
| [docs/B2B_DATA_ACCESS.md](docs/B2B_DATA_ACCESS.md) | to read the analyses from another team's system (the `kb` schema) |
| [supabase/README.md](supabase/README.md), [ratings_module_build_kit/README.md](ratings_module_build_kit/README.md), [web/README.md](web/README.md) | the three parts, for developers |
| [CONTRIBUTING.md](CONTRIBUTING.md) | how changes are made and checked, and the documentation rule |
