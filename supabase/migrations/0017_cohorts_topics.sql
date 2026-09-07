-- 0017_cohorts_topics.sql — cohorts you can parse, topics you can group.
--
-- Cohorts: the sheet's cohort text ("Applied Agentic AI - 2nd Mid-March 2026 : Cohort 2") is parsed
-- by the worker into region / start month / part of month / intake / cohort number; the parsed
-- identity lives in `cohort_key` (unique) and every raw spelling that mapped to it in `raw_labels`.
-- A class can belong to several cohorts: `class_ratings.cohort_id` is the primary one and
-- `cohort_ids` all of them.
--
-- Topics: canonical module names per course with aliases ("RAG Powered Knowledge Agents" =
-- "RAG Knowledge Agents"). `normalize_topic_name()` = lower · unaccent · every run of
-- non-alphanumerics → one space · trim ('' → null). The worker mirrors this rule exactly.
-- Seeded below from the distinct class names already in class_ratings (per course), skipping the
-- session-kind labels the old loader wrote into the topic column ("Live Class", "Test Review
-- Session") — the worker's Day-1 fix re-syncs the real names.
--
-- Additive and idempotent; safe to re-run. Requires 0016 (immutable_unaccent).

-- ────────────────────────────────────────────────────────────────────── cohorts
alter table public.cohorts
  add column if not exists region         text check (region in ('US','IND')),
  add column if not exists start_month    date,
  add column if not exists start_part     text check (start_part in ('early','mid','end')),
  add column if not exists intake_ordinal int default 1,
  add column if not exists cohort_no      int,
  add column if not exists audience       text,
  add column if not exists cohort_key     text,
  add column if not exists source         text default 'manual',
  add column if not exists raw_labels     text[] default '{}',
  add column if not exists updated_at     timestamptz;
create unique index if not exists cohorts_cohort_key_uidx on public.cohorts (cohort_key);
create index if not exists idx_cohorts_course_start on public.cohorts (course_id, start_month);

-- staff may edit a cohort's parsed identity from the course settings page (insert was already
-- staff-wide in 0003; delete stays admin-only)
drop policy if exists cohorts_update_staff on public.cohorts;
create policy cohorts_update_staff on public.cohorts
  for update to authenticated
  using (public.is_admin() or public.is_pm()) with check (public.is_admin() or public.is_pm());

-- ─────────────────────────────────────────────────────────────────────── topics
create or replace function public.normalize_topic_name(p text)
returns text language sql immutable parallel safe
set search_path = public as $$
  select nullif(trim(regexp_replace(lower(public.immutable_unaccent(coalesce(p, ''))), '[^a-z0-9]+', ' ', 'g')), '');
$$;

create table if not exists public.topics (
  id         uuid primary key default gen_random_uuid(),
  course_id  uuid not null references public.courses(id) on delete cascade,
  name       text not null,
  name_norm  text not null,
  module_no  int,
  week_no    int,
  created_at timestamptz not null default now(),
  unique (course_id, name_norm)
);

create table if not exists public.topic_aliases (
  id         uuid primary key default gen_random_uuid(),
  course_id  uuid not null references public.courses(id) on delete cascade,
  alias      text not null,
  alias_norm text not null,
  topic_id   uuid not null references public.topics(id) on delete cascade,
  created_at timestamptz not null default now(),
  unique (course_id, alias_norm)
);
create index if not exists idx_topic_aliases_topic on public.topic_aliases (topic_id);

alter table public.topics        enable row level security;
alter table public.topic_aliases enable row level security;

drop policy if exists topics_select on public.topics;
create policy topics_select on public.topics for select to authenticated using (true);
drop policy if exists topics_write on public.topics;
create policy topics_write on public.topics for all to authenticated
  using (public.is_admin() or public.is_pm()) with check (public.is_admin() or public.is_pm());

drop policy if exists topic_aliases_select on public.topic_aliases;
create policy topic_aliases_select on public.topic_aliases for select to authenticated using (true);
drop policy if exists topic_aliases_write on public.topic_aliases;
create policy topic_aliases_write on public.topic_aliases for all to authenticated
  using (public.is_admin() or public.is_pm()) with check (public.is_admin() or public.is_pm());

-- ──────────────────────────────────────────────────────── class_ratings columns
alter table public.class_ratings
  add column if not exists cohort_id  uuid references public.cohorts(id) on delete set null,
  add column if not exists cohort_ids uuid[] default '{}',
  add column if not exists topic_id   uuid references public.topics(id) on delete set null,
  add column if not exists week_no    int;
create index if not exists idx_class_ratings_cohort     on public.class_ratings (cohort_id);
create index if not exists idx_class_ratings_cohort_ids on public.class_ratings using gin (cohort_ids);
create index if not exists idx_class_ratings_topic      on public.class_ratings (topic_id);

-- ───────────────────────────────────────────────── seed topics from the class rows
with junk as (
  select unnest(array['live class', 'test review session', 'test review', 'live session',
                      'other', 'class', 'session', 'live']) as norm
),
raw as (
  select r.course_id, r.topic, public.normalize_topic_name(r.topic) as norm, count(*) as n
  from public.class_ratings r
  where r.course_id is not null and public.normalize_topic_name(r.topic) is not null
  group by 1, 2, 3
),
canon as (
  -- the most frequent raw spelling per (course, normalised name) becomes the topic's name
  select distinct on (course_id, norm) course_id, norm, topic as name
  from raw
  where norm not in (select norm from junk)
  order by course_id, norm, n desc, topic
)
insert into public.topics (course_id, name, name_norm)
select course_id, name, norm from canon
on conflict (course_id, name_norm) do nothing;

with raw as (
  select distinct r.course_id, r.topic, public.normalize_topic_name(r.topic) as norm
  from public.class_ratings r
  where r.course_id is not null and public.normalize_topic_name(r.topic) is not null
)
insert into public.topic_aliases (course_id, alias, alias_norm, topic_id)
select r.course_id, r.topic, r.norm, t.id
from raw r
join public.topics t on t.course_id = r.course_id and t.name_norm = r.norm
on conflict (course_id, alias_norm) do nothing;

update public.class_ratings r
   set topic_id = a.topic_id
  from public.topic_aliases a
 where r.topic_id is null
   and a.course_id = r.course_id
   and a.alias_norm = public.normalize_topic_name(r.topic);
