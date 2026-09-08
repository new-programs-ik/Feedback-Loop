-- 0014_approval_vote.sql — Rule v2: the instructor-approval vote + the weighted Class Health Score.
--
-- The ratings sheet carries a second signal per class — "would you want this instructor to take
-- the class again?" — as Yes/No counts. Rule v2 (Sep 2026, Instructor-Approval study) uses two
-- bars to decide IF a class enters the queue (rating < 4.55 or approval < 80%), and a Health
-- Score (0–100, weighted 60/30/10 across rating / approval / the instructor's track record) to
-- decide HOW URGENT (the band) and HOW DEEP (video vs transcript). The worker computes every
-- value here (ratings_module_build_kit/decision.py); the web mirror (web/src/lib/decision.ts)
-- explains them on the page.
--
-- Idempotent: safe to re-run.

alter table public.class_ratings
  add column if not exists yes_votes    integer,                       -- "Yes" column in the sheet
  add column if not exists no_votes     integer,                       -- "No" column in the sheet
  add column if not exists approval_pct numeric(5,2),                  -- yes/(yes+no); null when no votes
  add column if not exists track_avg    numeric(4,2),                  -- instructor's avg over earlier classes; null under 3 of them
  add column if not exists health_score numeric(5,1),                  -- 0–100; null only when the rating is unknown
  add column if not exists health_band  text,                          -- urgent | look | borderline; null unless queued
  add column if not exists flag_reasons text[] not null default '{}';  -- why it was flagged: rating | approval | escalated

do $$ begin
  alter table public.class_ratings
    add constraint class_ratings_health_band_check
    check (health_band is null or health_band in ('urgent', 'look', 'borderline'));
exception when duplicate_object then null; end $$;

do $$ begin
  alter table public.class_ratings
    add constraint class_ratings_flag_reasons_check
    check (flag_reasons <@ array['rating', 'approval', 'escalated']::text[]);
exception when duplicate_object then null; end $$;

-- The queue sorts by band; the track record looks up an instructor's earlier rows.
create index if not exists idx_class_ratings_band on public.class_ratings(health_band, review_status);
create index if not exists idx_class_ratings_instructor_date on public.class_ratings(instructor, class_date);
