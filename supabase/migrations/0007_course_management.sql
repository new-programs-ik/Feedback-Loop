-- 0007_course_management.sql — cross-team flexibility: any staff member (pm) can ADD a course.
-- (Update/delete stay admin-only — deleting a course cascades its cohorts/classes/analyses.)

drop policy if exists courses_insert on public.courses;
create policy courses_insert on public.courses for insert to authenticated
  with check (public.is_admin() or public.is_pm());
