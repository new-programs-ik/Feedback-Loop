-- 0000_drop_legacy_m1.sql — ONE-TIME cleanup of the empty M1 (automation-era) tables.
--
-- The original build created flat bigserial tables (classes/analyses/feedback/audit_log).
-- The product pivot replaces them with the normalized, UUID-based, RLS-secured model in
-- 0001_init.sql. These legacy tables are EMPTY (no data was ever written), so dropping is safe.
--
-- ⚠️  Do NOT re-run this file once real data exists — it drops tables by name. It is meant to
--     run exactly once, on the fresh database, before 0001_init.sql.

drop table if exists public.feedback   cascade;
drop table if exists public.analyses   cascade;
drop table if exists public.audit_log  cascade;
drop table if exists public.classes    cascade;
