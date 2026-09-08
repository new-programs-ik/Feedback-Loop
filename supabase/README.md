# Supabase — database schema & migrations

The Postgres database (on Supabase) is the **single source of truth** for the platform.
The Next.js app reads/writes it through Row-Level Security; the Python analysis worker never
touches it.

## Files
- `migrations/0000_drop_legacy_m1.sql` — one-time cleanup of the empty automation-era tables.
- `migrations/0001_init.sql` — the full schema: enums, identity/roles, reference data
  (courses/cohorts/instructors), the **feedback module** (classes, transcripts, analyses,
  feedback, audit_log), the **analytics scaffold** (enrollments, attendance, assignments,
  quizzes, tickets, participation, learner_health_scores + config), indexes, RBAC helper
  functions, **RLS policies**, and seed data.
- `migrations/0002_auth_hooks.sql` — the JWT role-claim hook + the new-user provisioning trigger.
- `migrations/0003` … `0014` — feedback-module additions, team access, the ratings ingest
  (`class_ratings`, `sync_runs`, handlers, notifications), the hourly cron, the approval vote.
- **Feedback Loop v3 (0015 → 0021, applied in this order; all additive, all idempotent):**
  - `0015_scoring_configs.sql` — the Class Sentiment Score in the database: `scoring_configs`
    (versioned, one active), `score_class_rating()`, `course_priors()`, `apply_scoring_config()`
    (activate + re-score every class), `scoring_whatif_summary()` (preview any config),
    `class_score_history` + trigger, the `sentiment_*` columns on `class_ratings`. Seeds C0–C5
    from `fixtures/scoring_configs.json`; C0 active.
  - `0016_instructor_identity.sql` — `normalize_person_name()`, `instructor_aliases`,
    `instructor_match_suggestions`, `instructor_merges`, accept / reject / alias / merge / undo RPCs,
    `class_ratings.instructor_canonical`.
  - `0017_cohorts_topics.sql` — parsed cohort identity on `cohorts`, `topics` + `topic_aliases`
    (`normalize_topic_name()`), `cohort_id` / `cohort_ids` / `topic_id` / `week_no` on `class_ratings`.
  - `0018_course_members.sql` — `course_members` (people × courses, handler flag), course
    colour/initials, `default_course_for()`, membership ↔ login linking on sign-in.
  - `0019_rollups_queue_sync.sql` — `v_course_month_rollup`, `v_instructor_rollup`,
    `v_cohort_journey`, `v_topic_hotspots`, `queue_rows()`, sync metrics, `report_shares`.
  - `0020_learner_contract.sql` — the empty learner layer (`learners`, `learner_ratings`,
    `learner_import_runs`); contract in `docs/LEARNER_INGEST_CONTRACT.md`.
  - `0021_tighten_reads.sql` — ratings tables readable by staff (admin / pm) only.
- `fixtures/scoring_cases.json`, `fixtures/scoring_configs.json` — the scoring contract (94 cases,
  six configs) shared by `analysis/sentiment_score.py`, the SQL function and the web mirror.
- `test_scoring_sql.py` — runs every fixture case through `score_class_rating()`; exits non-zero on
  any mismatch. Run it after touching the scoring function or the fixture:
  `./ratings_module_build_kit/.venv/Scripts/python supabase/test_scoring_sql.py`
- `apply_migrations.py` — applies the `.sql` files (in order) to `DATABASE_URL`.

## Apply
```bash
# from the repo root; DATABASE_URL is read from ratings_module_build_kit/.env
./ratings_module_build_kit/.venv/Scripts/python supabase/apply_migrations.py
```
Idempotent: `create ... if not exists` + policies dropped-then-created, so it's safe to re-run
(except `0000`, which is a one-time legacy drop — do not re-run once real data exists).

## Roles & access (RLS)
- **admin** — sees/does everything.
- **pm** — any @interviewkickstart.com sign-in; reads every course (one team), writes a course's settings only as a member of it (`course_members`, migration 0018). `pm_course_assignments` is legacy and unused.
- **learner** — sees only their own rows (analytics tables); no feedback-module access.
- Instructors do **not** log in — PMs view instructor analytics.

RLS is enforced via `SECURITY DEFINER` helper functions (`is_admin()`, `pm_owns_course()`,
`can_access_class()`), so access is always correct even if a JWT is stale.

## ⚠️ One manual dashboard step (needed before login works end-to-end)
Enable the access-token hook so a user's role rides in their JWT:
**Supabase Dashboard → Authentication → Hooks → Custom Access Token →** select
`public.custom_access_token_hook`. (RLS does not depend on this; it only lets the app read the
role from the token without a DB round-trip.)

## App environment variables (gather at the auth step)
From **Supabase Dashboard → Project Settings → API**:
- `NEXT_PUBLIC_SUPABASE_URL` — the Project URL
- `NEXT_PUBLIC_SUPABASE_ANON_KEY` — the anon/public key
- `SUPABASE_SERVICE_ROLE_KEY` — the service_role key (server-only; never sent to the browser)

`DATABASE_URL` (already in `ratings_module_build_kit/.env`) is used only by these migration
scripts and the Python-side eval harness.
