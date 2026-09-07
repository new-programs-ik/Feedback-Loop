-- 0019_rollups_queue_sync.sql — ready-made rollups, the queue query, sync metrics, share links.
--
-- Pages load from a few small queries instead of pulling thousands of rows. Every view runs with
-- security_invoker, so the caller's own row-level access to class_ratings applies.
--
--   v_course_month_rollup   course × month: n, avg rating / score, votes, approval, reach, band and
--                           decision counts
--   v_instructor_rollup     one row per instructor (resolved id, or the raw name until aliased) per
--                           course
--   v_cohort_journey        one row per class per cohort it belongs to (cohort_id or cohort_ids),
--                           with the cohort week
--   v_topic_hotspots        per course × topic: n, distinct instructors, averages, bad share, the
--                           instructor with the lowest average score on that topic
--   queue_rows(course, since)  the analysis queue (video / transcript / watch; still open)
--   sync_runs.*             rows scored, config version, band counts, cohort / identity / topic
--                           metrics, duration
--   report_shares           read-only share links (token, expiry, revoke)
--
-- Additive and idempotent; safe to re-run.

-- ──────────────────────────────────────────────────────── v_course_month_rollup
create or replace view public.v_course_month_rollup with (security_invoker = true) as
select r.course_id,
       date_trunc('month', r.class_date)::date                                   as month,
       count(*)::int                                                              as n,
       round(avg(r.rating), 2)                                                    as avg_rating,
       round(avg(r.sentiment_score), 2)                                           as avg_score,
       coalesce(sum(r.yes_votes) filter (where r.no_votes is not null), 0)::int   as yes,
       coalesce(sum(r.yes_votes + r.no_votes), 0)::int                            as votes,
       round(sum(r.yes_votes) filter (where r.no_votes is not null) * 100.0
             / nullif(sum(r.yes_votes + r.no_votes), 0), 2)                       as approval_pct,
       round(avg(least(100, r.num_ratings * 100.0 / nullif(r.attended, 0))), 2)   as avg_reach,
       count(*) filter (where r.sentiment_band = 'excellent')::int                as n_excellent,
       count(*) filter (where r.sentiment_band = 'good')::int                     as n_good,
       count(*) filter (where r.sentiment_band = 'average')::int                  as n_average,
       count(*) filter (where r.sentiment_band = 'bad')::int                      as n_bad,
       count(*) filter (where r.decision = 'video')::int                          as n_video,
       count(*) filter (where r.decision = 'transcript')::int                     as n_transcript
from public.class_ratings r
group by r.course_id, date_trunc('month', r.class_date);

-- ──────────────────────────────────────────────────────────── v_instructor_rollup
create or replace view public.v_instructor_rollup with (security_invoker = true) as
select coalesce(r.instructor_id::text,
                'name:' || coalesce(public.normalize_person_name(r.instructor), ''))  as instructor_key,
       r.instructor_id,
       coalesce(max(i.name), max(r.instructor_canonical),
                mode() within group (order by r.instructor))                         as instructor_name,
       r.course_id,
       count(*)::int                                                                 as n,
       round(avg(r.rating), 2)                                                       as avg_rating,
       round(avg(r.sentiment_score), 2)                                              as avg_score,
       round(sum(r.yes_votes) filter (where r.no_votes is not null) * 100.0
             / nullif(sum(r.yes_votes + r.no_votes), 0), 2)                          as approval_pct,
       count(*) filter (where r.sentiment_band = 'bad')::int                         as n_bad,
       count(*) filter (where r.sentiment_band = 'average')::int                     as n_average,
       max(r.class_date)                                                             as last_class_date
from public.class_ratings r
left join public.instructors i on i.id = r.instructor_id
group by 1, 2, 4;

-- ─────────────────────────────────────────────────────────────── v_cohort_journey
create or replace view public.v_cohort_journey with (security_invoker = true) as
select m.cohort_id,
       coalesce(r.week_no,
                case when c.start_date is not null then ((r.class_date - c.start_date) / 7) + 1 end) as week_no,
       r.class_date,
       r.topic_id,
       coalesce(t.name, r.topic)                                   as topic,
       r.instructor_id,
       coalesce(i.name, r.instructor_canonical, r.instructor)      as instructor_name,
       r.session_kind,
       r.rating,
       r.sentiment_score,
       r.sentiment_band,
       r.decision,
       r.num_ratings,
       r.attended,
       r.id                                                        as class_rating_id
from public.class_ratings r
cross join lateral (
  select distinct x as cohort_id
  from unnest(array_append(coalesce(r.cohort_ids, '{}'::uuid[]), r.cohort_id)) x
  where x is not null) m
join public.cohorts c     on c.id = m.cohort_id
left join public.topics t on t.id = r.topic_id
left join public.instructors i on i.id = r.instructor_id;

-- ─────────────────────────────────────────────────────────────── v_topic_hotspots
create or replace view public.v_topic_hotspots with (security_invoker = true) as
with per_instructor as (
  select r.course_id, r.topic_id, r.instructor_id, avg(r.sentiment_score) as avg_score, count(*) as n
  from public.class_ratings r
  where r.topic_id is not null and r.instructor_id is not null and r.sentiment_score is not null
  group by 1, 2, 3
),
worst as (
  select distinct on (course_id, topic_id) course_id, topic_id, instructor_id
  from per_instructor
  order by course_id, topic_id, avg_score asc, n desc
)
select r.course_id,
       r.topic_id,
       t.name                                                                       as topic,
       count(*)::int                                                                as n,
       count(distinct coalesce(r.instructor_id::text,
             'name:' || coalesce(public.normalize_person_name(r.instructor), '')))::int as instructors,
       round(avg(r.rating), 2)                                                      as avg_rating,
       round(avg(r.sentiment_score), 2)                                             as avg_score,
       round(sum(r.yes_votes) filter (where r.no_votes is not null) * 100.0
             / nullif(sum(r.yes_votes + r.no_votes), 0), 2)                         as approval_pct,
       round(count(*) filter (where r.sentiment_band = 'bad')::numeric
             / nullif(count(*) filter (where r.sentiment_band is not null), 0), 4)  as bad_share,
       w.instructor_id                                                              as worst_instructor_id
from public.class_ratings r
join public.topics t on t.id = r.topic_id
left join worst w on w.course_id = r.course_id and w.topic_id = r.topic_id
group by r.course_id, r.topic_id, t.name, w.instructor_id;

-- ───────────────────────────────────────────────────────────────────── queue_rows
-- The open analysis queue: the score's verdict (video / transcript) or watch, not yet dismissed
-- or started. Course null = every course; since null = all time. Videos first, newest first.
create or replace function public.queue_rows(p_course_id uuid default null, p_since date default null)
returns setof public.class_ratings
language sql stable security invoker set search_path = public as $$
  select *
  from public.class_ratings
  where decision in ('video', 'transcript', 'watch')
    and review_status in ('new', 'notified', 'confirmed')
    and (p_course_id is null or course_id = p_course_id)
    and (p_since is null or class_date >= p_since)
  order by case decision when 'video' then 0 when 'transcript' then 1 else 2 end, class_date desc;
$$;

-- ─────────────────────────────────────────────────────────────── sync_runs metrics
alter table public.sync_runs
  add column if not exists rows_scored            int,
  add column if not exists scoring_config_version int,
  add column if not exists band_counts            jsonb,
  add column if not exists cohorts_created        int,
  add column if not exists cohorts_unparsed       int,
  add column if not exists instructors_unresolved int,
  add column if not exists suggestions_created    int,
  add column if not exists topics_unmapped        int,
  add column if not exists duration_ms            int;

-- ─────────────────────────────────────────────────────────────────── report_shares
create table if not exists public.report_shares (
  id         uuid primary key default gen_random_uuid(),
  token      text not null unique default encode(extensions.gen_random_bytes(16), 'hex'),
  course_id  uuid references public.courses(id) on delete cascade,      -- null = all courses
  period     jsonb,                                                     -- {kind, from, to, ...}
  created_by uuid references auth.users(id) on delete set null,
  created_at timestamptz not null default now(),
  expires_at timestamptz,
  revoked_at timestamptz
);
create index if not exists idx_report_shares_course on public.report_shares (course_id, created_at desc);

alter table public.report_shares enable row level security;
drop policy if exists report_shares_select on public.report_shares;
create policy report_shares_select on public.report_shares
  for select to authenticated using (true);
drop policy if exists report_shares_write on public.report_shares;
create policy report_shares_write on public.report_shares
  for all to authenticated
  using (public.is_admin() or public.is_pm()) with check (public.is_admin() or public.is_pm());
