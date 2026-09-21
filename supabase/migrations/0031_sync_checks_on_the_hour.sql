-- 0031 - the scheduler also checks on the hour
--
-- The due check fires when a configured zone's local clock reads a wanted hour within the first
-- fifteen minutes. India is on a half-hour offset, so only the :30 / :35 checks ever fire for it;
-- a whole-hour zone added later in app_settings.sync_timezones would never fire without checks at
-- :00 / :05. They cost nothing when nothing is due. Safe to re-run.

do $$
declare j text;
begin
  foreach j in array array['ratings-sync-check-00', 'ratings-sync-check-05'] loop
    begin perform cron.unschedule(j); exception when others then null; end;
  end loop;
end $$;

select cron.schedule('ratings-sync-check-00', '0 * * * *', $job$ select public.ratings_sync_if_due('cron') $job$);
select cron.schedule('ratings-sync-check-05', '5 * * * *', $job$ select public.ratings_sync_if_due('cron-retry') $job$);
