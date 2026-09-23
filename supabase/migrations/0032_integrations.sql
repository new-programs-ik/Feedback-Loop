-- 0032_integrations.sql — the outside services the worker depends on: their secrets and their health.
--
-- Two needs, one pattern.
--
--  * UpLevel. The New-analysis form finds a class's recording on UpLevel by itself. UpLevel has no
--    service token yet, so an admin pastes a signed-in session once, on Admin › UpLevel, and the
--    worker uses it. That session is a credential: it lives in `integration_credentials`, which
--    has row-level security ON and NO policies, and is revoked from the API roles. Nobody signed in
--    can read or write it through the website's API. Only the website's server (service role, for
--    an admin's "connect") and the worker's direct database connection touch it. It is never shown
--    back to anyone.
--
--  * The Claude API credit. When the credit runs out, analyses are refused. The website must say so
--    only while it is actually empty, and stop saying it the moment it is recharged. The worker
--    records the state in `integration_status` ('empty' on a refusal, 'ok' on any success or a
--    successful re-check), and the website reads that one row.
--
-- Additive and idempotent: two new tables, one policy, two seed rows. Nothing existing changes.

create table if not exists public.integration_credentials (
  name          text primary key,                 -- 'uplevel'
  secret        text not null,                    -- e.g. 'sessionid=…; csrftoken=…'
  set_by        uuid references auth.users(id) on delete set null,
  set_by_label  text,
  set_at        timestamptz not null default now()
);
alter table public.integration_credentials enable row level security;
revoke all on public.integration_credentials from anon, authenticated;

create table if not exists public.integration_status (
  name           text primary key,                -- 'uplevel' | 'claude_credit'
  state          text not null default 'unknown'
                 check (state in ('ok', 'expired', 'empty', 'error', 'not_set', 'unknown')),
  detail         text,                            -- a sentence a person can read; never a secret
  last_ok_at     timestamptz,
  last_error_at  timestamptz,
  checked_at     timestamptz,
  set_at         timestamptz,                     -- when the credential was last connected
  set_by_label   text,
  updated_at     timestamptz not null default now()
);
alter table public.integration_status enable row level security;
revoke insert, update, delete on public.integration_status from anon, authenticated;
drop policy if exists integration_status_select on public.integration_status;
create policy integration_status_select on public.integration_status
  for select to authenticated using (public.is_admin() or public.is_pm());

-- UpLevel starts unconnected.
insert into public.integration_status (name, state, detail)
values ('uplevel', 'not_set', 'Not connected yet: an admin connects it on Admin › UpLevel.')
on conflict (name) do nothing;

-- The credit starts from what the audit trail already says: empty if the last credit refusal came
-- after the last completed analysis, ok otherwise. The worker re-checks it live from then on.
insert into public.integration_status (name, state, detail, last_error_at, last_ok_at, checked_at)
select 'claude_credit',
       case when e.at is not null and (a.at is null or e.at > a.at) then 'empty' else 'ok' end,
       case when e.at is not null and (a.at is null or e.at > a.at)
            then 'The last analysis was refused because the Claude API credit was empty.' end,
       e.at, a.at, now()
  from (select max(created_at) as at from public.audit_log
         where action = 'error'
           and (detail->>'kind' = 'no_credit'
                or detail->>'message' ilike '%credit balance is too low%'
                or detail->>'message' ilike '%Claude API fund is empty%'
                or detail->>'technical' ilike '%credit balance is too low%')) e,
       (select max(created_at) as at from public.audit_log where action = 'analyzed') a
on conflict (name) do nothing;
