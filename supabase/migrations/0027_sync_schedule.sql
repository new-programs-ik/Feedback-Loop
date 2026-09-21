-- 0027 - the ratings sync runs on its own: 10:00, 12:00 and 14:00 India time, every day
--
-- The sheet is filled in by hand and sometimes late in the day, so three runs a day (Bishal,
-- 21 Sep 2026; India time only, that is who uses it). pg_cron only speaks UTC and India is on a
-- half-hour offset, so a check runs at every half-hour and fires only when the Indian clock reads
-- a wanted hour. The hours and the zone are rows in app_settings, so changing them later is one
-- update, and a second zone can be added there without touching code.
--
-- Each check has a second try five minutes later, because the free worker can take longer to wake
-- than the caller waits; a second run is skipped while the first is still going, otherwise it is
-- harmless.
--
-- No shared secret is stored here. The old design (0013) needed the worker's key pasted into the
-- Vault by hand, which never happened. Instead the database mints a single-use token for every run
-- and sends it to the worker; the worker checks the token against this table before it starts.
-- Nobody has to paste or rotate anything, and a stray request without a fresh token is refused.
--
-- Additive and safe to re-run.

create extension if not exists pg_net;

-- One row per attempt to start a sync. The worker consumes the token; anything older than ten
-- minutes or already used is refused.
create table if not exists public.sync_triggers (
  id          uuid primary key default gen_random_uuid(),
  token       text not null unique,
  trigger     text not null default 'cron',
  created_at  timestamptz not null default now(),
  used_at     timestamptz
);
alter table public.sync_triggers enable row level security;   -- no policies: only the server roles
comment on table public.sync_triggers is 'Single-use tokens the scheduler hands the worker to start a ratings sync.';

-- Small settings the scheduler reads. Not secrets.
create table if not exists public.app_settings (
  key        text primary key,
  value      text not null,
  updated_at timestamptz not null default now()
);
alter table public.app_settings enable row level security;
comment on table public.app_settings is 'Plain settings read by database functions (worker address, sync hours and zones).';
insert into public.app_settings (key, value) values
  ('worker_url',       'https://feedback-loop-50w0.onrender.com'),
  ('sync_local_hours', '10,12,14'),
  ('sync_timezones',   'Asia/Kolkata')
on conflict (key) do nothing;

-- Start one sync now: mint a token, hand it to the worker.
create or replace function public.trigger_ratings_sync(p_trigger text default 'cron')
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  v_url   text;
  v_token text;
begin
  select value into v_url from public.app_settings where key = 'worker_url';
  if v_url is null then
    raise warning 'ratings sync: app_settings.worker_url is not set - skipping';
    return;
  end if;
  delete from public.sync_triggers where created_at < now() - interval '1 day';
  -- Two v4 uuids = 64 hex characters of randomness, from the core, so no dependency on which
  -- schema pgcrypto sits in (on Supabase it is `extensions`, outside this function's search path).
  v_token := replace(gen_random_uuid()::text || gen_random_uuid()::text, '-', '');
  insert into public.sync_triggers (token, trigger) values (v_token, p_trigger);
  perform net.http_post(
    url := rtrim(v_url, '/') || '/sync-ratings/cron',
    headers := '{"Content-Type": "application/json"}'::jsonb,
    body := jsonb_build_object('token', v_token, 'trigger', p_trigger),
    timeout_milliseconds := 15000
  );
end;
$$;
revoke all on function public.trigger_ratings_sync(text) from public, anon, authenticated;

-- Called at every half-hour: fire when a configured zone's local clock reads a wanted hour (within
-- the first 15 minutes, so the :35 retry still counts as the same slot).
create or replace function public.ratings_sync_if_due(p_label text default 'cron')
returns text
language plpgsql
security definer
set search_path = public
as $$
declare
  v_hours text[];
  v_zones text[];
  v_zone  text;
  v_local timestamp;
  v_fired text := null;
begin
  select string_to_array(replace(value, ' ', ''), ',') into v_hours from public.app_settings where key = 'sync_local_hours';
  select string_to_array(replace(value, ' ', ''), ',') into v_zones from public.app_settings where key = 'sync_timezones';
  if v_hours is null or v_zones is null then
    raise warning 'ratings sync: sync_local_hours / sync_timezones not set - skipping';
    return null;
  end if;
  foreach v_zone in array v_zones loop
    v_local := now() at time zone v_zone;
    if extract(hour from v_local)::int::text = any(v_hours) and extract(minute from v_local) < 15 then
      v_fired := p_label || ':' || v_zone;
      perform public.trigger_ratings_sync(v_fired);
      return v_fired;                 -- one run is enough even if two zones line up
    end if;
  end loop;
  return null;
end;
$$;
revoke all on function public.ratings_sync_if_due(text) from public, anon, authenticated;

-- Retire the never-used names from 0013 and any earlier draft of this file, then schedule.
do $$
declare j text;
begin
  foreach j in array array['ratings-sync-hourly', 'ratings-sync-hourly-retry',
                           'ratings-sync-10-ist', 'ratings-sync-10-ist-retry',
                           'ratings-sync-12-ist', 'ratings-sync-12-ist-retry',
                           'ratings-sync-14-ist', 'ratings-sync-14-ist-retry',
                           'ratings-sync-check-00', 'ratings-sync-check-05',
                           'ratings-sync-check-30', 'ratings-sync-check-35'] loop
    begin perform cron.unschedule(j); exception when others then null; end;
  end loop;
end $$;

select cron.schedule('ratings-sync-check-30', '30 * * * *', $job$ select public.ratings_sync_if_due('cron') $job$);
select cron.schedule('ratings-sync-check-35', '35 * * * *', $job$ select public.ratings_sync_if_due('cron-retry') $job$);
