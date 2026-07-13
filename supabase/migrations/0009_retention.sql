-- 0009_retention.sql — auto-purge stored transcripts after 20 days (confidentiality).
-- Raw class materials are NEVER stored; only the transcript is, and this removes it after 20 days
-- (the analysis result + feedback are kept). Uses pg_cron (a daily job).

create extension if not exists pg_cron;

do $$
begin
  perform cron.unschedule('purge-old-transcripts');
exception when others then null;
end $$;

select cron.schedule(
  'purge-old-transcripts',
  '17 3 * * *',
  $job$ delete from public.transcripts where fetched_at < now() - interval '20 days' $job$
);
