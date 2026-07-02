-- 0001_init.sql — initial schema for the IK New Programs Feedback & Analytics platform.
-- Idempotent: create-if-not-exists throughout; policies are dropped-then-created so the file
-- can be re-applied safely. Runs on a fresh Supabase Postgres (after 0000 legacy cleanup).
--
-- Sections: extensions · enums · core identity/roles · reference data · feedback module (live)
--           · analytics scaffold (later) · indexes · RBAC helper functions · RLS policies · seed.

-- ─────────────────────────────────────────────────────────────── extensions
create extension if not exists "pgcrypto";   -- gen_random_uuid()

-- ───────────────────────────────────────────────────────────────────── enums
do $$ begin
  if not exists (select 1 from pg_type where typname = 'app_role') then
    create type app_role as enum ('admin','pm','learner');
  end if;
  if not exists (select 1 from pg_type where typname = 'reclass_rec') then
    create type reclass_rec as enum ('yes','no','maybe');
  end if;
  if not exists (select 1 from pg_type where typname = 'class_status') then
    create type class_status as enum
      ('scheduled','analyzing','draft_ready','approved','discarded','no_action');
  end if;
  if not exists (select 1 from pg_type where typname = 'feedback_status') then
    create type feedback_status as enum ('draft','approved','discarded','sent');
  end if;
  if not exists (select 1 from pg_type where typname = 'health_band') then
    create type health_band as enum ('healthy','at_risk','critical');
  end if;
end $$;

-- ───────────────────────────────────────────────── core: identity & roles
create table if not exists public.profiles (
  user_id    uuid primary key references auth.users(id) on delete cascade,
  full_name  text,
  email      text,
  avatar_url text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.user_roles (
  user_id    uuid primary key references auth.users(id) on delete cascade,
  role       app_role not null default 'learner',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- ─────────────────────────────────────────── reference: courses/cohorts/instructors
create table if not exists public.courses (
  id          uuid primary key default gen_random_uuid(),
  name        text not null unique,
  slug        text not null unique,
  description text,
  created_at  timestamptz not null default now()
);

create table if not exists public.cohorts (
  id         uuid primary key default gen_random_uuid(),
  course_id  uuid not null references public.courses(id) on delete cascade,
  name       text not null,
  start_date date,
  end_date   date,
  created_at timestamptz not null default now(),
  unique (course_id, name)
);

create table if not exists public.instructors (
  id         uuid primary key default gen_random_uuid(),
  name       text not null,
  email      text,
  bio        text,
  created_at timestamptz not null default now()
);

-- Which PM owns which course (drives PM row-level access).
create table if not exists public.pm_course_assignments (
  id          uuid primary key default gen_random_uuid(),
  pm_user_id  uuid not null references auth.users(id) on delete cascade,
  course_id   uuid not null references public.courses(id) on delete cascade,
  assigned_at timestamptz not null default now(),
  unique (pm_user_id, course_id)
);

-- ───────────────────────────────────────────────── feedback module (LIVE)
create table if not exists public.classes (
  id               uuid primary key default gen_random_uuid(),
  course_id        uuid not null references public.courses(id) on delete cascade,
  cohort_id        uuid references public.cohorts(id) on delete set null,
  instructor_id    uuid references public.instructors(id) on delete set null,
  topic            text not null,
  class_date       date not null,
  session_type     text not null default 'live_class',
  duration_minutes integer default 240,
  rating           numeric(3,2),
  num_ratings      integer,
  vimeo_link       text,
  agenda           text,
  status           class_status not null default 'analyzing',
  created_by       uuid references auth.users(id) on delete set null,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),
  unique (course_id, cohort_id, instructor_id, topic, class_date)
);

create table if not exists public.transcripts (
  id         uuid primary key default gen_random_uuid(),
  class_id   uuid not null references public.classes(id) on delete cascade,
  content    text not null,
  format     text not null default 'vtt',      -- 'vtt' | 'srt'
  source     text not null default 'vimeo',     -- 'vimeo' | 'upload'
  fetched_at timestamptz not null default now(),
  unique (class_id)
);

create table if not exists public.analyses (
  id             uuid primary key default gen_random_uuid(),
  class_id       uuid not null references public.classes(id) on delete cascade,
  model          text not null,
  result         jsonb not null,               -- full engine output (flags+feedback+reclass)
  reclass        reclass_rec,                  -- re-teach recommendation: yes/no/maybe (PM-only)
  reclass_reason text,
  tokens_in      integer,
  tokens_out     integer,
  cost_usd       numeric(8,4),
  created_at     timestamptz not null default now()
);

create table if not exists public.feedback (
  id          uuid primary key default gen_random_uuid(),
  class_id    uuid not null references public.classes(id) on delete cascade,
  analysis_id uuid references public.analyses(id) on delete set null,
  draft_text  text not null,                    -- engine draft (never overwritten)
  edited_text text,                             -- PM edit (draft-vs-edit = accuracy signal)
  status      feedback_status not null default 'draft',
  approved_by uuid references auth.users(id) on delete set null,
  approved_at timestamptz,
  sent_at     timestamptz,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

create table if not exists public.audit_log (
  id          uuid primary key default gen_random_uuid(),
  class_id    uuid references public.classes(id) on delete set null,
  actor_id    uuid references auth.users(id) on delete set null,
  actor_label text,                             -- 'engine'/'system'/email when no auth user
  action      text not null,
  detail      jsonb,
  created_at  timestamptz not null default now()
);

-- ───────────────────────────────────────────── analytics scaffold (LATER)
create table if not exists public.enrollments (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references auth.users(id) on delete cascade,
  cohort_id   uuid not null references public.cohorts(id) on delete cascade,
  status      text not null default 'active',
  enrolled_at timestamptz not null default now(),
  unique (user_id, cohort_id)
);

create table if not exists public.attendance (
  id        uuid primary key default gen_random_uuid(),
  user_id   uuid not null references auth.users(id) on delete cascade,
  class_id  uuid not null references public.classes(id) on delete cascade,
  attended  boolean not null default false,
  marked_at timestamptz not null default now(),
  unique (user_id, class_id)
);

create table if not exists public.assignments (
  id         uuid primary key default gen_random_uuid(),
  cohort_id  uuid not null references public.cohorts(id) on delete cascade,
  title      text not null,
  description text,
  due_date   date,
  created_at timestamptz not null default now()
);

create table if not exists public.assignment_submissions (
  id            uuid primary key default gen_random_uuid(),
  assignment_id uuid not null references public.assignments(id) on delete cascade,
  user_id       uuid not null references auth.users(id) on delete cascade,
  submitted_text text,
  file_url      text,
  score         numeric(5,2),
  submitted_at  timestamptz,
  graded_at     timestamptz,
  unique (assignment_id, user_id)
);

create table if not exists public.quiz_results (
  id        uuid primary key default gen_random_uuid(),
  cohort_id uuid not null references public.cohorts(id) on delete cascade,
  user_id   uuid not null references auth.users(id) on delete cascade,
  quiz_name text not null,
  score     numeric(5,2),
  max_score numeric(5,2) default 100,
  taken_at  timestamptz not null default now()
);

create table if not exists public.support_tickets (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references auth.users(id) on delete cascade,
  cohort_id   uuid references public.cohorts(id) on delete set null,
  category    text,
  title       text not null,
  description text,
  status      text not null default 'open',
  created_at  timestamptz not null default now(),
  resolved_at timestamptz
);

create table if not exists public.participation (
  id                  uuid primary key default gen_random_uuid(),
  user_id             uuid not null references auth.users(id) on delete cascade,
  class_id            uuid not null references public.classes(id) on delete cascade,
  participation_score integer check (participation_score between 1 and 5),
  notes               text,
  recorded_at         timestamptz not null default now(),
  unique (user_id, class_id)
);

create table if not exists public.learner_health_scores (
  id                 uuid primary key default gen_random_uuid(),
  user_id            uuid not null references auth.users(id) on delete cascade,
  cohort_id          uuid not null references public.cohorts(id) on delete cascade,
  health_score       numeric(5,1),
  health_band        health_band,
  attendance_norm    numeric(4,3),
  assignment_norm    numeric(4,3),
  quiz_norm          numeric(4,3),
  support_norm       numeric(4,3),
  participation_norm numeric(4,3),
  computed_at        timestamptz not null default now(),
  unique (user_id, cohort_id)
);

create table if not exists public.health_score_config (
  signal_name text primary key,                 -- attendance|assignment|quiz|support|participation
  weight      numeric(3,2) not null check (weight >= 0 and weight <= 1),
  enabled     boolean not null default true,
  updated_at  timestamptz not null default now()
);

create table if not exists public.health_score_bands (
  band        health_band primary key,
  min_score   numeric(5,1) not null,
  max_score   numeric(5,1) not null,
  color_hex   text,
  description text
);

-- ─────────────────────────────────────────────────────────────────── indexes
create index if not exists idx_classes_course     on public.classes(course_id);
create index if not exists idx_classes_cohort     on public.classes(cohort_id);
create index if not exists idx_classes_instructor on public.classes(instructor_id);
create index if not exists idx_classes_status     on public.classes(status);
create index if not exists idx_classes_date       on public.classes(class_date desc);
create index if not exists idx_analyses_class     on public.analyses(class_id);
create index if not exists idx_feedback_class     on public.feedback(class_id);
create index if not exists idx_feedback_status    on public.feedback(status);
create index if not exists idx_audit_class        on public.audit_log(class_id);
create index if not exists idx_pmca_pm            on public.pm_course_assignments(pm_user_id);
create index if not exists idx_pmca_course        on public.pm_course_assignments(course_id);
create index if not exists idx_enrollments_user   on public.enrollments(user_id);

-- ─────────────────────────────────────────── RBAC helper functions
-- SECURITY DEFINER so they read user_roles/pm_course_assignments without tripping RLS
-- (prevents recursive policy evaluation). Always used inside policies below.
create or replace function public.current_app_role()
returns app_role language sql stable security definer set search_path = public as $$
  select role from public.user_roles where user_id = auth.uid();
$$;

create or replace function public.is_admin()
returns boolean language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.user_roles where user_id = auth.uid() and role = 'admin');
$$;

create or replace function public.is_pm()
returns boolean language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.user_roles where user_id = auth.uid() and role = 'pm');
$$;

create or replace function public.pm_owns_course(cid uuid)
returns boolean language sql stable security definer set search_path = public as $$
  select exists (
    select 1 from public.pm_course_assignments
    where pm_user_id = auth.uid() and course_id = cid
  );
$$;

-- true if the current user (admin, or PM who owns the class's course) may see a class
create or replace function public.can_access_class(cid uuid)
returns boolean language sql stable security definer set search_path = public as $$
  select exists (
    select 1 from public.classes c
    where c.id = cid
      and (public.is_admin() or public.pm_owns_course(c.course_id))
  );
$$;

-- ─────────────────────────────────────────────────────── enable RLS everywhere
alter table public.profiles               enable row level security;
alter table public.user_roles             enable row level security;
alter table public.courses                enable row level security;
alter table public.cohorts                enable row level security;
alter table public.instructors            enable row level security;
alter table public.pm_course_assignments  enable row level security;
alter table public.classes                enable row level security;
alter table public.transcripts            enable row level security;
alter table public.analyses               enable row level security;
alter table public.feedback               enable row level security;
alter table public.audit_log              enable row level security;
alter table public.enrollments            enable row level security;
alter table public.attendance             enable row level security;
alter table public.assignments            enable row level security;
alter table public.assignment_submissions enable row level security;
alter table public.quiz_results           enable row level security;
alter table public.support_tickets        enable row level security;
alter table public.participation          enable row level security;
alter table public.learner_health_scores  enable row level security;
alter table public.health_score_config    enable row level security;
alter table public.health_score_bands     enable row level security;

-- ─────────────────────────────────────────────────────────────── RLS policies
-- profiles: self or admin
drop policy if exists profiles_select on public.profiles;
create policy profiles_select on public.profiles for select to authenticated
  using (user_id = auth.uid() or public.is_admin());
drop policy if exists profiles_update on public.profiles;
create policy profiles_update on public.profiles for update to authenticated
  using (user_id = auth.uid() or public.is_admin()) with check (user_id = auth.uid() or public.is_admin());
drop policy if exists profiles_admin_all on public.profiles;
create policy profiles_admin_all on public.profiles for all to authenticated
  using (public.is_admin()) with check (public.is_admin());

-- user_roles: self read; admin manages
drop policy if exists user_roles_select on public.user_roles;
create policy user_roles_select on public.user_roles for select to authenticated
  using (user_id = auth.uid() or public.is_admin());
drop policy if exists user_roles_admin_all on public.user_roles;
create policy user_roles_admin_all on public.user_roles for all to authenticated
  using (public.is_admin()) with check (public.is_admin());

-- reference data (courses/cohorts/instructors): any signed-in user reads; admin writes
drop policy if exists courses_select on public.courses;
create policy courses_select on public.courses for select to authenticated using (true);
drop policy if exists courses_admin_all on public.courses;
create policy courses_admin_all on public.courses for all to authenticated
  using (public.is_admin()) with check (public.is_admin());

drop policy if exists cohorts_select on public.cohorts;
create policy cohorts_select on public.cohorts for select to authenticated using (true);
drop policy if exists cohorts_admin_all on public.cohorts;
create policy cohorts_admin_all on public.cohorts for all to authenticated
  using (public.is_admin()) with check (public.is_admin());

drop policy if exists instructors_select on public.instructors;
create policy instructors_select on public.instructors for select to authenticated using (true);
drop policy if exists instructors_admin_all on public.instructors;
create policy instructors_admin_all on public.instructors for all to authenticated
  using (public.is_admin()) with check (public.is_admin());

-- pm_course_assignments: PM sees own; admin manages
drop policy if exists pmca_select on public.pm_course_assignments;
create policy pmca_select on public.pm_course_assignments for select to authenticated
  using (pm_user_id = auth.uid() or public.is_admin());
drop policy if exists pmca_admin_all on public.pm_course_assignments;
create policy pmca_admin_all on public.pm_course_assignments for all to authenticated
  using (public.is_admin()) with check (public.is_admin());

-- classes: admin all; PM only for owned courses
drop policy if exists classes_select on public.classes;
create policy classes_select on public.classes for select to authenticated
  using (public.is_admin() or public.pm_owns_course(course_id));
drop policy if exists classes_write on public.classes;
create policy classes_write on public.classes for all to authenticated
  using (public.is_admin() or public.pm_owns_course(course_id))
  with check (public.is_admin() or public.pm_owns_course(course_id));

-- transcripts / analyses / feedback: gated by the parent class's course
drop policy if exists transcripts_rw on public.transcripts;
create policy transcripts_rw on public.transcripts for all to authenticated
  using (public.can_access_class(class_id)) with check (public.can_access_class(class_id));

drop policy if exists analyses_rw on public.analyses;
create policy analyses_rw on public.analyses for all to authenticated
  using (public.can_access_class(class_id)) with check (public.can_access_class(class_id));

drop policy if exists feedback_rw on public.feedback;
create policy feedback_rw on public.feedback for all to authenticated
  using (public.can_access_class(class_id)) with check (public.can_access_class(class_id));

-- audit_log: admin/PM-of-course may read; any authenticated may insert (app writes as actor)
drop policy if exists audit_select on public.audit_log;
create policy audit_select on public.audit_log for select to authenticated
  using (public.is_admin() or (class_id is not null and public.can_access_class(class_id)));
drop policy if exists audit_insert on public.audit_log;
create policy audit_insert on public.audit_log for insert to authenticated with check (true);

-- health config/bands: readable by signed-in users; admin writes
drop policy if exists hsconfig_select on public.health_score_config;
create policy hsconfig_select on public.health_score_config for select to authenticated using (true);
drop policy if exists hsconfig_admin on public.health_score_config;
create policy hsconfig_admin on public.health_score_config for all to authenticated
  using (public.is_admin()) with check (public.is_admin());

drop policy if exists hsbands_select on public.health_score_bands;
create policy hsbands_select on public.health_score_bands for select to authenticated using (true);
drop policy if exists hsbands_admin on public.health_score_bands;
create policy hsbands_admin on public.health_score_bands for all to authenticated
  using (public.is_admin()) with check (public.is_admin());

-- analytics scaffold: learner sees own rows; admin sees all (PM access refined when built)
do $$
declare t text;
begin
  foreach t in array array['enrollments','attendance','assignment_submissions','quiz_results',
                           'support_tickets','participation','learner_health_scores']
  loop
    execute format('drop policy if exists %I_owner on public.%I;', t, t);
    execute format(
      'create policy %I_owner on public.%I for select to authenticated using (user_id = auth.uid() or public.is_admin());',
      t, t);
    execute format('drop policy if exists %I_admin on public.%I;', t, t);
    execute format(
      'create policy %I_admin on public.%I for all to authenticated using (public.is_admin()) with check (public.is_admin());',
      t, t);
  end loop;
end $$;

-- assignments belong to a cohort (no user_id): admin manages, signed-in read
drop policy if exists assignments_select on public.assignments;
create policy assignments_select on public.assignments for select to authenticated using (true);
drop policy if exists assignments_admin on public.assignments;
create policy assignments_admin on public.assignments for all to authenticated
  using (public.is_admin()) with check (public.is_admin());

-- ─────────────────────────────────────────────────────────────────── seed data
insert into public.courses (name, slug) values
  ('Flagship ML','flagship-ml'),
  ('Advanced ML','advanced-ml'),
  ('PwC Accelerator','pwc-accelerator'),
  ('FDE','fde')
on conflict (name) do nothing;

insert into public.health_score_config (signal_name, weight) values
  ('attendance',0.25),('assignment',0.20),('quiz',0.25),('support',0.15),('participation',0.15)
on conflict (signal_name) do nothing;

insert into public.health_score_bands (band, min_score, max_score, color_hex, description) values
  ('healthy', 75.0, 100.0, '#10b981', 'On track for success'),
  ('at_risk', 50.0,  74.9, '#f59e0b', 'Needs attention'),
  ('critical', 0.0,  49.9, '#ef4444', 'Immediate support required')
on conflict (band) do nothing;
