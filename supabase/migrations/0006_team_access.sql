-- 0006_team_access.sql — cross-team rollout.
--   * Internal staff (role 'pm') get FULL access to feedback data (course becomes a label/filter,
--     not an access wall). Admin keeps user/role management on top.
--   * New sign-ups from @interviewkickstart.com auto-become 'pm' (staff); anyone else 'learner'
--     (and the /auth/callback already refuses non-IK Google accounts).

-- 1) any signed-in staff member may access all feedback data
create or replace function public.can_access_class(cid uuid)
returns boolean language sql stable security definer set search_path = public as $$
  select public.is_admin() or public.is_pm();
$$;

drop policy if exists classes_select on public.classes;
create policy classes_select on public.classes for select to authenticated
  using (public.is_admin() or public.is_pm());

drop policy if exists classes_write on public.classes;
create policy classes_write on public.classes for all to authenticated
  using (public.is_admin() or public.is_pm())
  with check (public.is_admin() or public.is_pm());

-- 2) new-user provisioning: IK emails → 'pm' (staff), everyone else → 'learner'
create or replace function public.handle_new_user()
returns trigger language plpgsql security definer set search_path = public as $$
declare
  v_role app_role;
begin
  v_role := case
    when lower(coalesce(new.email, '')) like '%@interviewkickstart.com' then 'pm'::app_role
    else 'learner'::app_role
  end;
  insert into public.profiles (user_id, email, full_name)
    values (new.id, new.email, coalesce(new.raw_user_meta_data->>'full_name', new.email))
    on conflict (user_id) do nothing;
  insert into public.user_roles (user_id, role)
    values (new.id, v_role)
    on conflict (user_id) do nothing;
  return new;
end;
$$;
