-- 0030 - a heartbeat for long sync runs
--
-- A run was declared dead after ten minutes with no way to say "still here", so a full pass
-- longer than that could be marked failed and a second run started on top of it. The worker now
-- touches heartbeat_at every half minute while it works; stale means no heartbeat, not merely old.
-- Additive and safe to re-run.

alter table public.sync_runs add column if not exists heartbeat_at timestamptz;
comment on column public.sync_runs.heartbeat_at is 'Last time the running sync said it was still working.';
