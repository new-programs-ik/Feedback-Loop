-- 0026 - a read-only export layer for other teams' knowledge bases (asked for by the B2B team,
-- September 2026)
--
-- Other teams want the class analyses in their own systems. They get a separate schema of views and
-- a role that can read those views and nothing else: no transcripts (confidential, purged after 20
-- days anyway), no learner data, no auth tables, no writes. The views run with their owner's rights,
-- so row-level security on the source tables does not apply; that is the point of the layer, and
-- why every view names its columns instead of exposing a table.
--
-- The role is created WITHOUT login. Nobody can use it until an admin sets a password by hand:
--   alter role kb_reader with login password '<choose a long one>';
-- Revoking access later is one line:  alter role kb_reader nologin;
-- Additive and safe to re-run.

create schema if not exists kb;
comment on schema kb is 'Read-only views for other teams'' knowledge bases. See docs/B2B_DATA_ACCESS.md.';

-- One row per AI analysis, with the class it was about and the feedback the PM approved (or is
-- still drafting). The raw findings ride along as JSON.
create or replace view kb.class_analyses as
select a.id                                        as analysis_id,
       c.id                                        as class_id,
       co.name                                     as course,
       ch.name                                     as cohort,
       i.name                                      as instructor,
       c.topic,
       c.class_date,
       c.session_type,
       c.rating,
       c.num_ratings,
       c.vimeo_link,
       a.created_at                                as analysed_at,
       a.model,
       a.result->>'overall'                        as overall,
       a.result->'flags'                           as flags,
       a.result->>'instructor_summary'             as instructor_summary,
       a.reclass::text                             as reclass,
       a.reclass_reason,
       f.status::text                              as feedback_status,
       coalesce(f.edited_text, f.draft_text)       as feedback_text,
       coalesce(f.summary_edited_text, f.summary_draft_text) as summary_text,
       f.approved_at,
       f.sent_at,
       (a.result->'video'->>'video_used')::boolean as video_used
from public.analyses a
join public.classes c        on c.id = a.class_id
left join public.courses co  on co.id = c.course_id
left join public.cohorts ch  on ch.id = c.cohort_id
left join public.instructors i on i.id = c.instructor_id
left join public.feedback f  on f.analysis_id = a.id;
comment on view kb.class_analyses is 'One row per AI analysis of a class, with the PM''s feedback text and status.';

-- Every class from the ratings sheet with its Class Sentiment Score, band and what the band asks for.
create or replace view kb.class_scores as
select r.id                 as class_rating_id,
       co.name              as course,
       r.course_label,
       r.cohort_text,
       r.topic,
       r.instructor,
       r.class_date,
       r.session_kind,
       r.rating,
       r.num_ratings,
       r.attended,
       r.yes_votes,
       r.no_votes,
       r.approval_pct,
       r.sentiment_score,
       r.sentiment_band,
       r.sentiment_action,
       r.sentiment_flags,
       r.review_status,
       r.escalated,
       r.week_no,
       s.version            as scoring_version,
       r.scored_at,
       r.synced_at
from public.class_ratings r
left join public.courses co on co.id = r.course_id
left join public.scoring_configs s on s.id = r.score_config_id;
comment on view kb.class_scores is 'Every rated class with its score, band (excellent/good/average/bad or null = too few responses) and action (video/transcript/none/watch).';

-- How the bands were computed, so a score can be read in context.
create or replace view kb.scoring_versions as
select version, key, name, status, config, note, created_at, activated_at, retired_at
from public.scoring_configs;
comment on view kb.scoring_versions is 'The scoring formula versions; status = active is the one class_scores uses now.';

-- The role: read the kb schema, nothing else, and never for long.
do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'kb_reader') then
    create role kb_reader nologin connection limit 5;
  end if;
end $$;
grant usage on schema kb to kb_reader;
grant select on all tables in schema kb to kb_reader;
alter default privileges in schema kb grant select on tables to kb_reader;
alter role kb_reader set search_path = kb;
alter role kb_reader set statement_timeout = '60s';
alter role kb_reader set default_transaction_read_only = on;
