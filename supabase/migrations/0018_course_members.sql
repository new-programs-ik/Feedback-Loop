-- 0018_course_members.sql — people and ownership: who owns which course (and cohort).
--
-- One table replaces the unused pm_course_assignments and the UI-less course_handlers (both are
-- kept untouched until the switch-over; their rows are copied here once). A member is a person
-- by IK email — linked to their login (user_id) the first time they sign in — with a role
-- (owner · pm · viewer), an optional cohort, the "is handler" flag (exactly one per course), Slack
-- preferences, who added them, and hand-over history.
--
--   course_members                   the table (unique per course × cohort × email)
--   courses.color / initials         the course identity square (placeholders seeded here)
--   default_course_for(uid)          slug of the user's first membership (owner > pm > viewer)
--   is_course_owner(course_id)       RLS helper (SECURITY DEFINER, avoids recursive policies)
--   handle_new_user()                now also links memberships added by email before sign-up
--   on_auth_user_signed_in           links memberships on every sign-in (never blocks a sign-in)
--
-- Additive and idempotent; safe to re-run.

create table if not exists public.course_members (
  id               uuid primary key default gen_random_uuid(),
  course_id        uuid not null references public.courses(id) on delete cascade,
  cohort_id        uuid references public.cohorts(id) on delete cascade,        -- null = whole course
  user_id          uuid references auth.users(id) on delete set null,
  email            text not null,
  display_name     text,
  role             text not null default 'pm' check (role in ('owner','pm','viewer')),
  is_handler       boolean not null default false,
  notify_slack     boolean not null default true,
  slack_user_id    text,
  added_by         uuid references auth.users(id) on delete set null,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),
  handed_over_from uuid,                                                        -- previous member row / user
  handed_over_at   timestamptz
);
create unique index if not exists course_members_person_uidx
  on public.course_members (course_id, coalesce(cohort_id, '00000000-0000-0000-0000-000000000000'::uuid), lower(email));
create unique index if not exists course_members_one_handler_uidx
  on public.course_members (course_id) where is_handler and cohort_id is null;
create index if not exists idx_course_members_user  on public.course_members (user_id);
create index if not exists idx_course_members_email on public.course_members (lower(email));

-- ───────────────────────────────────────────────────────────────────────── RLS
create or replace function public.is_course_owner(p_course_id uuid)
returns boolean language sql stable security definer set search_path = public as $$
  select exists (
    select 1 from public.course_members m
    where m.course_id = p_course_id and m.user_id = auth.uid() and m.role = 'owner');
$$;

alter table public.course_members enable row level security;
drop policy if exists course_members_select on public.course_members;
create policy course_members_select on public.course_members
  for select to authenticated using (true);
drop policy if exists course_members_write on public.course_members;
create policy course_members_write on public.course_members
  for all to authenticated
  using (public.is_admin() or public.is_course_owner(course_id))
  with check (public.is_admin() or public.is_course_owner(course_id));

-- ─────────────────────────────────────────────── copy what exists today (once)
insert into public.course_members (course_id, email, display_name, role, is_handler, slack_user_id, added_by, created_at)
select h.course_id, h.handler_email, h.handler_name, 'pm', true, h.slack_user_id, h.assigned_by, h.assigned_at
from public.course_handlers h
where h.handler_email is not null
  and not exists (select 1 from public.course_members m
                   where m.course_id = h.course_id and m.cohort_id is null
                     and lower(m.email) = lower(h.handler_email))
  and not exists (select 1 from public.course_members m
                   where m.course_id = h.course_id and m.is_handler and m.cohort_id is null);

insert into public.course_members (course_id, user_id, email, display_name, role, created_at)
select a.course_id, a.pm_user_id, p.email, p.full_name, 'pm', a.assigned_at
from public.pm_course_assignments a
join public.profiles p on p.user_id = a.pm_user_id
where p.email is not null
  and not exists (select 1 from public.course_members m
                   where m.course_id = a.course_id and m.cohort_id is null
                     and lower(m.email) = lower(p.email));

-- ─────────────────────────────────────────────────────────── course identity
alter table public.courses
  add column if not exists color    text,
  add column if not exists initials text;

-- initials: the name's capitals (max 3); a name with fewer than two capitals → its first 3 letters
update public.courses c
   set initials = sub.initials
  from (
    select id,
           case when length(caps) >= 2 then left(caps, 3)
                else upper(left(regexp_replace(name, '[^A-Za-z0-9]', '', 'g'), 3)) end as initials
    from (select id, name, regexp_replace(name, '[^A-Z]', '', 'g') as caps from public.courses) x
  ) sub
 where sub.id = c.id and c.initials is null;

-- colour: eight fixed hues, assigned round-robin in creation order (placeholders until the team
-- picks its own; the band colours are reserved for scores and never used here)
with palette as (
  select array['#2563eb','#7c3aed','#c026d3','#db2777','#ea580c','#ca8a04','#16a34a','#0891b2'] as hues
),
ordered as (
  select id, (row_number() over (order by created_at, name) - 1) as rn
  from public.courses where color is null
)
update public.courses c
   set color = (select hues[(o.rn % 8) + 1] from palette)
  from ordered o
 where o.id = c.id;

-- ───────────────────────────────────────────────────────── default_course_for
-- The slug of the user's first membership (owner > pm > viewer), matched on user_id or on the
-- user's profile email; null when they belong nowhere.
create or replace function public.default_course_for(p_uid uuid)
returns text language sql stable security definer set search_path = public as $$
  select c.slug
  from public.course_members m
  join public.courses c on c.id = m.course_id
  left join public.profiles p on p.user_id = p_uid
  where p_uid is not null
    and (m.user_id = p_uid or (p.email is not null and lower(m.email) = lower(p.email)))
  order by case m.role when 'owner' then 0 when 'pm' then 1 else 2 end, m.created_at, c.name
  limit 1;
$$;
revoke all on function public.default_course_for(uuid) from public, anon;
grant execute on function public.default_course_for(uuid) to authenticated, service_role;

-- ───────────────────────────────────────────── link memberships to logins
-- New sign-ups (0006 logic kept: IK emails → pm, everyone else → learner) + membership linking.
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
  begin
    update public.course_members
       set user_id = new.id, updated_at = now()
     where user_id is null and lower(email) = lower(coalesce(new.email, ''));
  exception when others then
    null;  -- a membership link must never block a sign-up
  end;
  return new;
end;
$$;

-- On every sign-in: link memberships added by email while the person had no login yet.
create or replace function public.link_course_member_on_sign_in()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  begin
    update public.course_members
       set user_id = new.id, updated_at = now()
     where user_id is null and lower(email) = lower(coalesce(new.email, ''));
  exception when others then
    null;  -- never block a sign-in
  end;
  return new;
end;
$$;

drop trigger if exists on_auth_user_signed_in on auth.users;
create trigger on_auth_user_signed_in
  after update of last_sign_in_at on auth.users
  for each row
  when (old.last_sign_in_at is distinct from new.last_sign_in_at)
  execute function public.link_course_member_on_sign_in();

-- memberships for people who already have a login
update public.course_members m
   set user_id = p.user_id, updated_at = now()
  from public.profiles p
 where m.user_id is null and p.email is not null and lower(p.email) = lower(m.email);
