-- 0004_class_catalog.sql — the planned classes for a course (topic + assigned instructor).
-- Mirrors the Cohort planning sheet's structure (course → its classes, each with an instructor).
-- For now it's seeded from a snapshot; later a sheet sync populates it.

create table if not exists public.class_catalog (
  id            uuid primary key default gen_random_uuid(),
  course_id     uuid not null references public.courses(id) on delete cascade,
  topic         text not null,
  instructor_id uuid references public.instructors(id) on delete set null,
  created_at    timestamptz not null default now(),
  unique (course_id, topic)
);
create index if not exists idx_class_catalog_course on public.class_catalog(course_id);

alter table public.class_catalog enable row level security;

drop policy if exists class_catalog_select on public.class_catalog;
create policy class_catalog_select on public.class_catalog for select to authenticated using (true);

drop policy if exists class_catalog_write on public.class_catalog;
create policy class_catalog_write on public.class_catalog for all to authenticated
  using (public.is_admin() or public.is_pm()) with check (public.is_admin() or public.is_pm());
