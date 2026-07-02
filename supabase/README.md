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
- **pm** — sees only classes/analyses/feedback for courses assigned in `pm_course_assignments`.
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
