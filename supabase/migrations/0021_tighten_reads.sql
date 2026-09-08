-- 0021_tighten_reads.sql — ratings data is for staff.
--
-- The ratings tables were created with `using (true)` select policies (0012, 0015), which would
-- let any signed-in account — including a future learner login — read every class rating, sync
-- run, notification and score history row. Reads are now limited to staff (admin or pm).
-- Writes were already staff-only. Policies are replaced in place (same names), which is the
-- repo's idempotent pattern; no table or column changes.

drop policy if exists class_ratings_select on public.class_ratings;
create policy class_ratings_select on public.class_ratings
  for select to authenticated using (public.is_admin() or public.is_pm());

drop policy if exists course_aliases_select on public.course_aliases;
create policy course_aliases_select on public.course_aliases
  for select to authenticated using (public.is_admin() or public.is_pm());

drop policy if exists sync_runs_select on public.sync_runs;
create policy sync_runs_select on public.sync_runs
  for select to authenticated using (public.is_admin() or public.is_pm());

drop policy if exists rating_notifications_select on public.rating_notifications;
create policy rating_notifications_select on public.rating_notifications
  for select to authenticated using (public.is_admin() or public.is_pm());

drop policy if exists class_score_history_select on public.class_score_history;
create policy class_score_history_select on public.class_score_history
  for select to authenticated using (public.is_admin() or public.is_pm());
