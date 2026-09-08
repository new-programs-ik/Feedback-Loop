-- 0013_ratings_cron.sql — the hourly ratings-sync schedule.  ⚠️ DEPLOY-TIME ONLY.
--
-- Apply this AFTER the worker with /sync-ratings is deployed and the two Vault secrets exist:
--   select vault.create_secret('<https://worker-url>', 'worker_url');
--   select vault.create_secret('<the WORKER_API_KEY>', 'worker_api_key');
-- (Run those two lines once, by hand, in the Supabase SQL editor — secrets never live in files.)
--
-- Two schedules, :00 and :05 — the Render free tier can cold-start slower than pg_net's timeout,
-- so the second call lands on a warmed worker. The sync is idempotent and guards against
-- concurrent runs, so a double fire is harmless.

create extension if not exists pg_net;

create or replace function public.trigger_ratings_sync()
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  v_url text;
  v_key text;
begin
  select decrypted_secret into v_url from vault.decrypted_secrets where name = 'worker_url';
  select decrypted_secret into v_key from vault.decrypted_secrets where name = 'worker_api_key';
  if v_url is null or v_key is null then
    raise warning 'ratings sync: vault secrets worker_url/worker_api_key not set — skipping';
    return;
  end if;
  perform net.http_post(
    url := rtrim(v_url, '/') || '/sync-ratings',
    headers := jsonb_build_object(
      'Authorization', 'Bearer ' || v_key,
      'Content-Type', 'application/json'),
    body := '{"trigger":"cron"}'::jsonb,
    timeout_milliseconds := 15000
  );
end;
$$;

revoke all on function public.trigger_ratings_sync() from public, anon, authenticated;

do $$ begin perform cron.unschedule('ratings-sync-hourly'); exception when others then null; end $$;
select cron.schedule('ratings-sync-hourly', '0 * * * *', $job$ select public.trigger_ratings_sync() $job$);

do $$ begin perform cron.unschedule('ratings-sync-hourly-retry'); exception when others then null; end $$;
select cron.schedule('ratings-sync-hourly-retry', '5 * * * *', $job$ select public.trigger_ratings_sync() $job$);
