-- 0005_cohort_classes.sql — the per-cohort weekly schedule imported from the Flagship sheet.
-- Each row: a week's class (date + topic) with up to 3 instructors (Sun live / Thu review / Wed coaching).

create unique index if not exists instructors_name_uidx on public.instructors(name);

create table if not exists public.cohort_classes (
  id                     uuid primary key default gen_random_uuid(),
  cohort_id              uuid not null references public.cohorts(id) on delete cascade,
  week_no                integer,
  class_date             date not null,
  topic                  text not null,
  instructor_id          uuid references public.instructors(id) on delete set null,  -- Sunday live
  review_instructor_id   uuid references public.instructors(id) on delete set null,  -- Thursday review
  coaching_instructor_id uuid references public.instructors(id) on delete set null,  -- Wednesday coaching
  created_at             timestamptz not null default now(),
  updated_at             timestamptz not null default now(),
  unique (cohort_id, class_date, topic)
);
create index if not exists idx_cohort_classes_cohort on public.cohort_classes(cohort_id);
create index if not exists idx_cohort_classes_date   on public.cohort_classes(class_date);

alter table public.cohort_classes enable row level security;

drop policy if exists cohort_classes_select on public.cohort_classes;
create policy cohort_classes_select on public.cohort_classes for select to authenticated using (true);

drop policy if exists cohort_classes_write on public.cohort_classes;
create policy cohort_classes_write on public.cohort_classes for all to authenticated
  using (public.is_admin() or public.is_pm()) with check (public.is_admin() or public.is_pm());
