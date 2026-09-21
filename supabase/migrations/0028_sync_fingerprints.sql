-- 0028 - the sync remembers what the sheet said about each class, so it can skip what did not change
--
-- Every run used to make two database round trips per class, 2,833 classes, from the worker in the
-- US to this database in Singapore: nine minutes of waiting, and a deploy in that window killed the
-- run. The worker now stores a fingerprint of the sheet's values on each class row and skips rows
-- whose fingerprint has not changed. A daily run touches the handful of new or edited rows.
--
-- rows_unchanged on sync_runs is the count of skipped rows, for the sync page.
-- Additive and safe to re-run.

alter table public.class_ratings add column if not exists row_hash text;
comment on column public.class_ratings.row_hash is 'Fingerprint of the sheet values this row was last written from; the sync skips rows whose fingerprint has not changed.';

alter table public.sync_runs add column if not exists rows_unchanged integer;
comment on column public.sync_runs.rows_unchanged is 'Rows the sheet had not changed since the previous run, so the sync left them alone.';
