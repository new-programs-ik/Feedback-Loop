-- 0008_profiles_read.sql — team attribution: staff can see each other's name/email
-- (needed for the "Created by" column). Profiles hold only name + email of internal staff.

drop policy if exists profiles_select on public.profiles;
create policy profiles_select on public.profiles for select to authenticated using (true);
