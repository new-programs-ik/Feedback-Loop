-- 0011_failed_status.sql
-- Bug fix: the failure paths (worker mark_failed + web failStart) wrote status 'needs_transcript',
-- a value left over from the old M1 schema that does NOT exist in the class_status enum — so marking
-- a failure always errored silently and broken classes sat in 'analyzing' forever. Add a real value.
alter type class_status add value if not exists 'failed';
