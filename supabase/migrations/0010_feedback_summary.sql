-- 0010_feedback_summary.sql
-- The analysis now produces TWO instructor texts: the detailed, timestamped feedback (draft_text /
-- edited_text, for the internal team) and a short summary to SEND the instructor. Store the summary
-- as its own draft + PM-edited pair so it can be edited, AI-revised and approved just like the detail.
alter table public.feedback add column if not exists summary_draft_text  text;   -- engine draft (never overwritten)
alter table public.feedback add column if not exists summary_edited_text text;   -- PM edit of the send-summary
