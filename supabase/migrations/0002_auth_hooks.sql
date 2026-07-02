-- 0002_auth_hooks.sql — Supabase Auth integration.
--   1. custom_access_token_hook: injects the user's role as a JWT claim `app_role`
--      (used by the Next.js middleware to pick the right nav without a DB round-trip).
--      MUST be enabled in the dashboard: Authentication → Hooks → Custom Access Token → select
--      public.custom_access_token_hook. RLS does NOT depend on this (it uses helper functions),
--      so the app is secure even before the hook is enabled.
--   2. handle_new_user: on signup, auto-create a profile row + default 'learner' role.

-- 1) Access-token hook
create or replace function public.custom_access_token_hook(event jsonb)
returns jsonb language plpgsql stable as $$
declare
  claims jsonb;
  v_role text;
begin
  select role::text into v_role from public.user_roles where user_id = (event->>'user_id')::uuid;
  v_role := coalesce(v_role, 'learner');
  claims := coalesce(event->'claims', '{}'::jsonb);
  claims := jsonb_set(claims, '{app_role}', to_jsonb(v_role));
  event := jsonb_set(event, '{claims}', claims);
  return event;
end;
$$;

-- Allow the auth server to call the hook; keep it off-limits to client roles.
grant usage on schema public to supabase_auth_admin;
grant execute on function public.custom_access_token_hook(jsonb) to supabase_auth_admin;
revoke execute on function public.custom_access_token_hook(jsonb) from authenticated, anon, public;

-- 2) New-user provisioning: profile + default role
create or replace function public.handle_new_user()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  insert into public.profiles (user_id, email, full_name)
    values (new.id, new.email, coalesce(new.raw_user_meta_data->>'full_name', new.email))
    on conflict (user_id) do nothing;
  insert into public.user_roles (user_id, role)
    values (new.id, 'learner')
    on conflict (user_id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();
