-- 0020_learner_contract.sql — the learner layer: empty tables + the ingestion contract.
--
-- No learner-level data exists yet (the ratings workbook holds not one email). The layer is
-- created now, empty, so that when an export arrives it plugs in without touching the class layer.
-- The long form of this contract, with examples, is docs/LEARNER_INGEST_CONTRACT.md.
--
-- THE CONTRACT (one row per learner per rated class, keyed to the class row we already have)
--   learners.learner_key     a stable, source-independent key — sha256 of the lower-cased, trimmed
--                            email (hex) or the LMS learner id; the raw email is NEVER stored here.
--   learner_ratings          (source, external_id) is the idempotency key: a re-import updates the
--                            row in place. class_rating_id links the row to class_ratings through
--                            the class natural key (class_date, topic, instructor, session_kind)
--                            after alias resolution; unmatched rows are kept with a null link and
--                            counted per run. rating 0–5 (2 dp) or null; approve yes/no/null;
--                            raw keeps the source record verbatim for audit.
--   learner_import_runs      mirrors sync_runs: one row per import with counts + unmatched samples.
--   Access: staff (admin / pm) read everything; a learner with a login reads only their own rows;
--           no client writes — the worker (service role) is the only writer.
--   The class layer is untouched: class_ratings' counts stay the source's counts; a learner-level
--   total that disagrees with the class row is reported by the import, never written over it.
--
-- Additive and idempotent; safe to re-run.

create table if not exists public.learners (
  id           uuid primary key default gen_random_uuid(),
  learner_key  text not null unique,
  user_id      uuid references auth.users(id) on delete set null,
  display_name text,
  created_at   timestamptz not null default now()
);
create index if not exists idx_learners_user on public.learners (user_id);

create table if not exists public.learner_ratings (
  id              uuid primary key default gen_random_uuid(),
  source          text not null,                                    -- 'lms' | 'sheet' | 'metabase' | ...
  external_id     text not null,                                    -- the source's own row id
  learner_id      uuid not null references public.learners(id) on delete cascade,
  class_rating_id uuid references public.class_ratings(id) on delete set null,   -- null = unmatched
  cohort_id       uuid references public.cohorts(id) on delete set null,
  class_date      date,
  topic           text,
  topic_id        uuid references public.topics(id) on delete set null,
  instructor_id   uuid references public.instructors(id) on delete set null,
  rating          numeric(3,2) check (rating is null or (rating >= 0 and rating <= 5)),
  approve         boolean,                                          -- "would you want this instructor back?"
  comment         text,
  submitted_at    timestamptz,
  ingested_at     timestamptz not null default now(),
  raw             jsonb,
  unique (source, external_id)
);
create index if not exists idx_learner_ratings_learner on public.learner_ratings (learner_id, class_date);
create index if not exists idx_learner_ratings_class   on public.learner_ratings (class_rating_id);
create index if not exists idx_learner_ratings_cohort  on public.learner_ratings (cohort_id, class_date);

create table if not exists public.learner_import_runs (
  id                uuid primary key default gen_random_uuid(),
  source            text not null,
  trigger           text not null default 'manual',                 -- 'manual' | 'cron' | 'api'
  status            text not null default 'running',                -- 'running' | 'ok' | 'failed'
  rows_fetched      int,
  rows_upserted     int,
  rows_matched      int,                                            -- linked to a class row
  rows_unmatched    int,
  learners_created  int,
  unmatched_samples jsonb,                                          -- up to 50 {external_id, class_date, topic, instructor}
  error             text,
  started_at        timestamptz not null default now(),
  finished_at       timestamptz,
  duration_ms       int
);
create index if not exists idx_learner_import_runs_started on public.learner_import_runs (started_at desc);

-- ───────────────────────────────────────────────────────────────────────── RLS
alter table public.learners            enable row level security;
alter table public.learner_ratings     enable row level security;
alter table public.learner_import_runs enable row level security;

drop policy if exists learners_select on public.learners;
create policy learners_select on public.learners
  for select to authenticated
  using (public.is_admin() or public.is_pm() or user_id = auth.uid());

drop policy if exists learner_ratings_select on public.learner_ratings;
create policy learner_ratings_select on public.learner_ratings
  for select to authenticated
  using (public.is_admin() or public.is_pm()
         or exists (select 1 from public.learners l where l.id = learner_id and l.user_id = auth.uid()));

drop policy if exists learner_import_runs_select on public.learner_import_runs;
create policy learner_import_runs_select on public.learner_import_runs
  for select to authenticated using (public.is_admin() or public.is_pm());
-- no insert/update/delete policies: only the worker (service role / DATABASE_URL) writes
