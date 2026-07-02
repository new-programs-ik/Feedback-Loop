-- 0003_feedback_writes.sql — let PMs (not just admins) add cohorts + instructors when they
-- create an analysis. Reference data stays read-only to learners; update/delete stay admin-only.

drop policy if exists cohorts_insert on public.cohorts;
create policy cohorts_insert on public.cohorts for insert to authenticated
  with check (public.is_admin() or public.is_pm());

drop policy if exists instructors_insert on public.instructors;
create policy instructors_insert on public.instructors for insert to authenticated
  with check (public.is_admin() or public.is_pm());
