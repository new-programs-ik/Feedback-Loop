-- 0012_ratings_ingest.sql — the live ratings platform.
--
-- One row per class session synced from the ratings source (Google Sheet today, Metabase later),
-- for EVERY class — not just the ones someone chose to analyze. The team decision rule
-- (4.55 line / 40% participation bar / 5-voice floor) is applied per row by the worker; flagged
-- classes surface in the web "Needs analysis" queue and notify the course handler on Slack.
--
-- Idempotent: safe to re-run. RLS follows the 0005 staff-wide pattern
-- (read: any signed-in user; write: admin or pm; the worker writes via DATABASE_URL, bypassing RLS).

-- ── enums ─────────────────────────────────────────────────────────────────────
do $$ begin
  create type rating_decision as enum ('none', 'watch', 'transcript', 'video');
exception when duplicate_object then null; end $$;

do $$ begin
  create type rating_review_status as enum
    ('new', 'notified', 'confirmed', 'dismissed', 'analysis_started');
exception when duplicate_object then null; end $$;

-- ── course aliases: sheet labels -> our courses. Map, never auto-create. ──────
create table if not exists public.course_aliases (
  id         uuid primary key default gen_random_uuid(),
  alias      text not null unique,
  course_id  uuid not null references public.courses(id) on delete cascade,
  created_at timestamptz not null default now()
);

-- ── the synced ratings themselves ─────────────────────────────────────────────
create table if not exists public.class_ratings (
  id                uuid primary key default gen_random_uuid(),
  source            text not null default 'sheet',            -- 'sheet' | 'metabase'
  course_label      text not null,                            -- mapped label from the source
  course_id         uuid references public.courses(id) on delete set null,  -- null = unmapped
  cohort_text       text,
  topic             text not null,
  instructor        text not null default '',
  instructor_id     uuid references public.instructors(id) on delete set null,
  class_date        date not null,
  session_kind      text not null default 'Live Class',       -- Live Class | Test Review | Other
  rating            numeric(3,2) not null,
  num_ratings       integer,                                  -- learners who rated ("Responses")
  attended          integer,
  participation_pct numeric(5,1),
  escalated         boolean not null default false,           -- PM toggle; forces decision 'video'
  decision          rating_decision not null default 'none',
  decision_override rating_decision,                          -- PM manual; sync never touches it
  review_status     rating_review_status not null default 'new',
  class_id          uuid references public.classes(id) on delete set null,  -- once analysis starts
  first_seen_at     timestamptz not null default now(),
  synced_at         timestamptz not null default now(),
  updated_at        timestamptz not null default now(),
  -- Natural key for upserts. Rating deliberately excluded: it drifts as more learners rate.
  -- Known limitation: two same-day sessions with identical topic+instructor+kind would merge.
  unique (class_date, topic, instructor, session_kind)
);
create index if not exists idx_class_ratings_decision on public.class_ratings(decision, review_status);
create index if not exists idx_class_ratings_date     on public.class_ratings(class_date desc);
create index if not exists idx_class_ratings_course   on public.class_ratings(course_id);

-- ── course handlers: a NAME + IK EMAIL per course (not auth.users — handlers may ──
--    never have signed in; pm_course_assignments stays what it is: an RLS construct).
create table if not exists public.course_handlers (
  id            uuid primary key default gen_random_uuid(),
  course_id     uuid not null references public.courses(id) on delete cascade unique,
  handler_name  text not null,
  handler_email text not null,
  slack_user_id text,                                         -- cached users.lookupByEmail result
  assigned_by   uuid references auth.users(id) on delete set null,
  assigned_at   timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

-- ── notification ledger: the duplicate-send guard + the transparency record ───
create table if not exists public.rating_notifications (
  id              uuid primary key default gen_random_uuid(),
  class_rating_id uuid not null references public.class_ratings(id) on delete cascade,
  channel         text not null default 'slack',              -- 'slack' | 'email'
  recipient       text,
  status          text not null default 'sent',               -- 'sent' | 'failed'
  slack_ts        text,
  error           text,
  sent_at         timestamptz not null default now(),
  unique (class_rating_id, channel)
);

-- ── sync run log: powers the "Last synced …" banner and failure alerts ────────
create table if not exists public.sync_runs (
  id                 uuid primary key default gen_random_uuid(),
  source             text not null,
  trigger            text not null,                           -- 'cron' | 'manual'
  status             text not null default 'running',         -- 'running' | 'ok' | 'failed'
  rows_fetched       integer,
  rows_upserted      integer,
  rows_flagged       integer,
  notifications_sent integer,
  unmapped_labels    text[],
  error              text,
  started_at         timestamptz not null default now(),
  finished_at        timestamptz
);
create index if not exists idx_sync_runs_started on public.sync_runs(started_at desc);

-- ── RLS (0005 pattern: staff-wide read, pm/admin write) ───────────────────────
alter table public.course_aliases       enable row level security;
alter table public.class_ratings        enable row level security;
alter table public.course_handlers      enable row level security;
alter table public.rating_notifications enable row level security;
alter table public.sync_runs            enable row level security;

drop policy if exists course_aliases_select on public.course_aliases;
create policy course_aliases_select on public.course_aliases
  for select to authenticated using (true);
drop policy if exists course_aliases_write on public.course_aliases;
create policy course_aliases_write on public.course_aliases
  for all to authenticated
  using (public.is_admin() or public.is_pm())
  with check (public.is_admin() or public.is_pm());

drop policy if exists class_ratings_select on public.class_ratings;
create policy class_ratings_select on public.class_ratings
  for select to authenticated using (true);
drop policy if exists class_ratings_write on public.class_ratings;
create policy class_ratings_write on public.class_ratings
  for all to authenticated
  using (public.is_admin() or public.is_pm())
  with check (public.is_admin() or public.is_pm());

drop policy if exists course_handlers_select on public.course_handlers;
create policy course_handlers_select on public.course_handlers
  for select to authenticated using (true);
drop policy if exists course_handlers_write on public.course_handlers;
create policy course_handlers_write on public.course_handlers
  for all to authenticated
  using (public.is_admin() or public.is_pm())
  with check (public.is_admin() or public.is_pm());

drop policy if exists rating_notifications_select on public.rating_notifications;
create policy rating_notifications_select on public.rating_notifications
  for select to authenticated using (true);

drop policy if exists sync_runs_select on public.sync_runs;
create policy sync_runs_select on public.sync_runs
  for select to authenticated using (true);

-- ── seeds ─────────────────────────────────────────────────────────────────────
-- Courses that exist in the ratings sheet but not in the original seed set.
insert into public.courses (name, slug) values
  ('ML SwitchUp', 'ml-switchup'),
  ('AI Data Science SwitchUp', 'ai-ds-switchup'),
  ('Transformative GenAI', 'transformative-genai'),
  ('Applied Agentic AI', 'applied-agentic-ai')
on conflict (name) do nothing;

-- Aliases: every label the sheet's course-mapping rules can produce -> a course row.
insert into public.course_aliases (alias, course_id)
select v.alias, c.id
from (values
  ('ML Flagship (IND)',                  'Flagship ML'),
  ('Advanced ML Program',                'Advanced ML'),
  ('PwC x IK Agentic AI Accelerator',    'PwC Accelerator'),
  ('FDE (Forward Deployed Engineering)', 'FDE'),
  ('ML Program',                         'ML SwitchUp'),
  ('ML SwitchUp (unmapped cohort)',      'ML SwitchUp'),
  ('AI Data Science SwitchUp',           'AI Data Science SwitchUp'),
  ('Transformative GenAI',               'Transformative GenAI'),
  ('Applied Agentic AI',                 'Applied Agentic AI')
) as v(alias, course_name)
join public.courses c on c.name = v.course_name
on conflict (alias) do nothing;
