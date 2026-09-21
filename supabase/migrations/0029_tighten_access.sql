-- 0029 - tighten three policies the production review found too open
--
-- report_shares: the token IS the link. It was readable by every signed-in account (including
--   learners), so anyone could list every live report link; and any PM could edit anyone's link.
--   Now staff read; the creator (or an admin) changes or removes; inserts carry the creator's id.
-- course_members: a list of staff names and emails was readable by learners. Staff only.
-- audit_log: any signed-in account could insert any row, as anyone. Staff only, as themselves.
--   (The worker writes audit rows as the database owner and is not affected.)
--
-- Policies only; no data changes. Safe to re-run.

drop policy if exists report_shares_select on public.report_shares;
create policy report_shares_select on public.report_shares
  for select to authenticated using (public.is_admin() or public.is_pm());

drop policy if exists report_shares_write on public.report_shares;
drop policy if exists report_shares_insert on public.report_shares;
create policy report_shares_insert on public.report_shares
  for insert to authenticated
  with check ((public.is_admin() or public.is_pm()) and created_by = auth.uid());
drop policy if exists report_shares_update on public.report_shares;
create policy report_shares_update on public.report_shares
  for update to authenticated
  using (public.is_admin() or created_by = auth.uid())
  with check (public.is_admin() or created_by = auth.uid());
drop policy if exists report_shares_delete on public.report_shares;
create policy report_shares_delete on public.report_shares
  for delete to authenticated using (public.is_admin() or created_by = auth.uid());

drop policy if exists course_members_select on public.course_members;
create policy course_members_select on public.course_members
  for select to authenticated using (public.is_admin() or public.is_pm());

drop policy if exists audit_insert on public.audit_log;
create policy audit_insert on public.audit_log
  for insert to authenticated
  with check ((public.is_admin() or public.is_pm()) and (actor_id is null or actor_id = auth.uid()));

-- Two more lists that learners could read: the course handlers (names, emails, Slack ids) and the
-- scoring formula versions. Staff only, like the rest of the ratings tables since 0021.
drop policy if exists course_handlers_select on public.course_handlers;
create policy course_handlers_select on public.course_handlers
  for select to authenticated using (public.is_admin() or public.is_pm());

drop policy if exists scoring_configs_select on public.scoring_configs;
create policy scoring_configs_select on public.scoring_configs
  for select to authenticated using (public.is_admin() or public.is_pm());
