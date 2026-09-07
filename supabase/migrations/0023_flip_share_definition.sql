-- 0023_flip_share_definition.sql
--
-- One definition of "flips on one vote" everywhere. The validation study (Sentiment-Score-
-- Validation.pdf) reports the share of ALL classes in the window whose band changes when one
-- "yes" becomes a "no" or one rater gives a point less. scoring_whatif_summary divided by the
-- classes that have a band, so the same month read 42% in the app and 37% in the study. This
-- makes the database share the study's denominator; the numerator was already the same two
-- perturbations. `banded` stays in the result for the "n of m" note.
--
-- Additive and idempotent (create or replace of the same function).

create or replace function public.scoring_whatif_summary(p_config jsonb, p_from date default null, p_to date default null)
returns jsonb
language plpgsql stable security invoker set search_path = public as $$
declare
  v_from   date;
  v_to     date;
  v_weeks  numeric;
  v_result jsonb;
begin
  select coalesce(p_from, min(class_date)), coalesce(p_to, max(class_date))
    into v_from, v_to
  from public.class_ratings
  where (p_from is null or class_date >= p_from) and (p_to is null or class_date <= p_to);

  if v_from is null or v_to is null then
    return jsonb_build_object('n', 0, 'weeks', 0, 'from', p_from, 'to', p_to,
      'band_counts', '{}'::jsonb, 'action_counts', '{}'::jsonb,
      'analyses_per_week', 0, 'videos_per_week', 0, 'transcripts_per_week', 0,
      'changed', '[]'::jsonb, 'changed_count', 0, 'dropped_count', 0,
      'flip_share', 0, 'flip_count', 0, 'banded', 0);
  end if;
  v_weeks := greatest(1, (v_to - v_from + 1) / 7.0);

  with priors as (
    select c.course_id, p.prior_rating, p.prior_approval
    from (select distinct course_id from public.class_ratings) c
    cross join lateral public.course_priors(c.course_id) p
  ),
  base as (
    select r.id, r.class_date, r.rating, r.num_ratings, r.attended, r.yes_votes, r.no_votes,
           r.escalated, r.track_avg, r.decision,
           r.sentiment_band as from_band, r.sentiment_action as from_action,
           p.prior_rating, p.prior_approval
    from public.class_ratings r
    left join priors p on p.course_id is not distinct from r.course_id
    where r.class_date between v_from and v_to
  ),
  scored as (
    select b.*, s.score, s.band as to_band, s.action as to_action,
           case when b.yes_votes >= 1 then
             (select s2.band from public.score_class_rating(b.rating, b.num_ratings, b.attended,
                     b.yes_votes - 1, b.no_votes + 1, b.escalated, b.track_avg,
                     b.prior_rating, b.prior_approval, p_config) s2)
           end as band_vote_flip,
           case when b.num_ratings > 0 then
             (select s3.band from public.score_class_rating(greatest(0, b.rating - 1.0 / b.num_ratings),
                     b.num_ratings, b.attended, b.yes_votes, b.no_votes, b.escalated, b.track_avg,
                     b.prior_rating, b.prior_approval, p_config) s3)
           end as band_rating_drop
    from base b
    cross join lateral public.score_class_rating(b.rating, b.num_ratings, b.attended, b.yes_votes,
           b.no_votes, b.escalated, b.track_avg, b.prior_rating, b.prior_approval, p_config) s
  ),
  flips as (
    select id, to_band,
           ((band_vote_flip   is distinct from to_band and (band_vote_flip   is not null or to_band is not null)) or
            (band_rating_drop is distinct from to_band and (band_rating_drop is not null or to_band is not null))) as flipped
    from scored
  ),
  changed as (
    select id, class_date, from_band, to_band, from_action, to_action
    from scored
    where to_band is distinct from from_band or to_action is distinct from from_action
  )
  select jsonb_build_object(
    'n',      (select count(*) from scored),
    'weeks',  round(v_weeks, 2),
    'from',   v_from,
    'to',     v_to,
    'band_counts',   coalesce((select jsonb_object_agg(coalesce(to_band, 'no_band'), n)
                                 from (select to_band, count(*) n from scored group by 1) t), '{}'::jsonb),
    'action_counts', coalesce((select jsonb_object_agg(coalesce(to_action, 'none'), n)
                                 from (select to_action, count(*) n from scored group by 1) t), '{}'::jsonb),
    'analyses_per_week',    round((select count(*) from scored where to_action in ('video', 'transcript')) / v_weeks, 2),
    'videos_per_week',      round((select count(*) from scored where to_action = 'video') / v_weeks, 2),
    'transcripts_per_week', round((select count(*) from scored where to_action = 'transcript') / v_weeks, 2),
    'changed', coalesce((select jsonb_agg(jsonb_build_object(
                          'id', id, 'from_band', from_band, 'to_band', to_band,
                          'from_action', from_action, 'to_action', to_action) order by class_date desc)
                         from (select * from changed order by class_date desc limit 500) c), '[]'::jsonb),
    'changed_count', (select count(*) from changed),
    'dropped_count', (select count(*) from scored
                       where decision in ('video', 'transcript') and to_action = 'none'),
    'flip_count',    (select count(*) from flips where flipped),
    'banded',        (select count(*) from flips where to_band is not null),
    -- the study's definition: flips as a share of EVERY class in the window
    'flip_share',    round(coalesce((select count(*) filter (where flipped) from flips)::numeric
                                    / nullif((select count(*) from flips), 0), 0), 4)
  ) into v_result;

  return v_result;
end;
$$;
