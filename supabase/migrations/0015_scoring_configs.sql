-- 0015_scoring_configs.sql — the Class Sentiment Score inside the database.
--
-- One source of truth: `score_class_rating()` is a line-by-line translation of the reference
-- scorer (analysis/sentiment_score.py) and must reproduce every case in
-- supabase/fixtures/scoring_cases.json (run supabase/test_scoring_sql.py). Every scoring setting
-- is a stored, versioned row in `scoring_configs`; one version is active; every scored class
-- carries the version that produced it; `class_score_history` records every change.
--
-- What this adds (all additive, all idempotent — the database is shared with production):
--   scoring_configs                 versioned config rows (draft / active / retired), one active
--   class_ratings.sentiment_*       score (2 dp), band, action, provisional, flags, config, breakdown
--   class_ratings.decision_v2       one-time snapshot of today's rule-v2 decision (before/after)
--   class_score_history (+trigger)  a row whenever score / band / config changes on a class
--   course_priors(course)           the course's typical rating + pooled approval (the guard)
--   score_class_rating(...)         THE scoring function (STABLE, pure)
--   active_scoring_config()         the active row
--   apply_scoring_config(id)        activate a version + re-score every class in one statement
--   scoring_whatif_summary(cfg)     preview any config on a window (band mix, workload, changes)
--
-- `components` returned by score_class_rating (stored in class_ratings.score_components):
--   {rating, approval, sample, reach, track}      each 0–100 or null when excluded (2 dp)
--   weights_used: {component: weight}             only the INCLUDED components (re-scaled sum)
--   adjusted:     {rating, approval}              after the small-sample guard
--   inputs:       {rating, num_ratings, attended, yes_votes, no_votes, votes, approval_pct,
--                  reach_pct, track_avg, prior_rating, prior_approval}
--   Points earned by a component = value × weight / sum(weights_used).
--
-- Side effect to know about: apply_scoring_config() sets `decision` = the score's action on every
-- row that is not frozen (no decision_override, not dismissed / analysis_started; escalated rows
-- stay 'video'). The seed at the bottom activates C0 (the manager's original) and scores every
-- existing row, so the queue follows the active scoring version from here on. The rule-v2
-- verdict each row had before the first pass is kept in class_ratings.decision_v2.

-- ─────────────────────────────────────────────────────────────── scoring_configs
create table if not exists public.scoring_configs (
  id           uuid primary key default gen_random_uuid(),
  version      int  not null unique,
  key          text unique,
  name         text not null,
  status       text not null default 'draft' check (status in ('draft','active','retired')),
  config       jsonb not null,
  note         text,
  created_by   uuid references auth.users(id) on delete set null,
  created_at   timestamptz not null default now(),
  activated_at timestamptz,
  retired_at   timestamptz
);
create unique index if not exists scoring_configs_one_active_uidx
  on public.scoring_configs (status) where status = 'active';

alter table public.scoring_configs enable row level security;
drop policy if exists scoring_configs_select on public.scoring_configs;
create policy scoring_configs_select on public.scoring_configs
  for select to authenticated using (true);
drop policy if exists scoring_configs_insert on public.scoring_configs;
create policy scoring_configs_insert on public.scoring_configs
  for insert to authenticated with check (public.is_admin());
drop policy if exists scoring_configs_update on public.scoring_configs;
create policy scoring_configs_update on public.scoring_configs
  for update to authenticated using (public.is_admin()) with check (public.is_admin());

-- ─────────────────────────────────────────────────────── class_ratings: the score
alter table public.class_ratings
  add column if not exists sentiment_score       numeric(5,2),
  add column if not exists sentiment_band        text
    check (sentiment_band is null or sentiment_band in ('excellent','good','average','bad')),
  add column if not exists sentiment_action      text
    check (sentiment_action is null or sentiment_action in ('video','transcript','none','watch')),
  add column if not exists sentiment_provisional boolean not null default false,
  add column if not exists sentiment_flags       text[]  not null default '{}',
  add column if not exists score_config_id       uuid references public.scoring_configs(id) on delete set null,
  add column if not exists score_components      jsonb,
  add column if not exists scored_at             timestamptz,
  -- the rule-v2 verdict as it stood before the first scoring pass (kept for before/after)
  add column if not exists decision_v2           rating_decision;

create index if not exists idx_class_ratings_sentiment_band on public.class_ratings (sentiment_band, review_status);
create index if not exists idx_class_ratings_course_date    on public.class_ratings (course_id, class_date desc);

-- ───────────────────────────────────────────────────────────── class_score_history
create table if not exists public.class_score_history (
  id              uuid primary key default gen_random_uuid(),
  class_rating_id uuid not null references public.class_ratings(id) on delete cascade,
  config_id       uuid references public.scoring_configs(id) on delete set null,
  score           numeric(5,2),
  band            text,
  action          text,
  components      jsonb,
  scored_at       timestamptz not null default now(),
  reason          text
);
create index if not exists idx_class_score_history_rating on public.class_score_history (class_rating_id, scored_at desc);

alter table public.class_score_history enable row level security;
drop policy if exists class_score_history_select on public.class_score_history;
create policy class_score_history_select on public.class_score_history
  for select to authenticated using (true);
-- no client write policies: rows come from the trigger below (SECURITY DEFINER)

create or replace function public.class_ratings_score_history_trg()
returns trigger language plpgsql security definer set search_path = public as $$
declare
  v_reason text;
begin
  if tg_op = 'UPDATE'
     and new.sentiment_score  is not distinct from old.sentiment_score
     and new.sentiment_band   is not distinct from old.sentiment_band
     and new.score_config_id  is not distinct from old.score_config_id then
    return null;
  end if;
  if tg_op = 'INSERT'
     and new.sentiment_score is null and new.sentiment_band is null and new.score_config_id is null then
    return null;
  end if;
  v_reason := nullif(current_setting('app.score_reason', true), '');
  if v_reason is null then
    v_reason := case
      when tg_op = 'INSERT' then 'scored'
      when new.score_config_id is distinct from old.score_config_id then 'config_change'
      else 'rescored' end;
  end if;
  insert into public.class_score_history
    (class_rating_id, config_id, score, band, action, components, scored_at, reason)
  values
    (new.id, new.score_config_id, new.sentiment_score, new.sentiment_band, new.sentiment_action,
     new.score_components, coalesce(new.scored_at, now()), v_reason);
  return null;
end;
$$;

drop trigger if exists trg_class_ratings_score_history on public.class_ratings;
create trigger trg_class_ratings_score_history
  after insert or update on public.class_ratings
  for each row execute function public.class_ratings_score_history_trg();

-- ───────────────────────────────────────────────────────────────── course_priors
-- The course's typical rating and POOLED approval (sum yes / sum(yes+no) × 100) over its classes
-- in the last 180 days. Under 30 such classes (or no course) → the same over ALL classes.
-- Both are rounded to 2 dp so the guard's inputs are explainable ("typical rating 4.71").
create or replace function public.course_priors(p_course_id uuid)
returns table (prior_rating numeric, prior_approval numeric)
language sql stable set search_path = public as $$
  with course_rows as (
    select rating, yes_votes, no_votes
    from public.class_ratings
    where p_course_id is not null and course_id = p_course_id
      and class_date >= current_date - 180 and rating is not null
  ),
  all_rows as (
    select rating, yes_votes, no_votes
    from public.class_ratings
    where class_date >= current_date - 180 and rating is not null
  ),
  chosen as (
    select * from course_rows where (select count(*) from course_rows) >= 30
    union all
    select * from all_rows  where (select count(*) from course_rows) <  30
  )
  select round(avg(rating), 2) as prior_rating,
         round(sum(yes_votes) filter (where no_votes is not null) * 100.0
               / nullif(sum(yes_votes + no_votes), 0), 2) as prior_approval
  from chosen;
$$;

-- ───────────────────────────────────────────────────────────── score_class_rating
-- Translation of analysis/sentiment_score.py::score(). Numeric arithmetic throughout;
-- round(x, 2) on numerics is half-up, the same rule as the Python round2().
create or replace function public.score_class_rating(
  p_rating         numeric,
  p_num_ratings    int,
  p_attended       int,
  p_yes            int,
  p_no             int,
  p_escalated      boolean,
  p_track          numeric,
  p_prior_rating   numeric,
  p_prior_approval numeric,
  p_config         jsonb)
returns table (score numeric, band text, action text, provisional boolean, flags text[], components jsonb)
language plpgsql stable set search_path = public as $$
declare
  cfg            jsonb   := coalesce(p_config, '{}'::jsonb);
  v_flags        text[]  := '{}';
  v_escalated    boolean := coalesce(p_escalated, false);
  v_no_data      text    := coalesce(cfg #>> '{actions,no_data}', 'watch');
  v_scale        numeric := coalesce((cfg #>> '{rating,scale}')::numeric, 5);
  v_rating       numeric := p_rating;
  v_n            numeric := p_num_ratings;
  v_attended     numeric := p_attended;
  v_yes          numeric := p_yes;
  v_no           numeric := p_no;
  v_votes        numeric;
  v_approval     numeric;
  v_reach        numeric;
  v_k            numeric := coalesce((cfg #>> '{guard,k}')::numeric, 0);
  v_adj_rating   numeric;
  v_adj_approval numeric;
  c_rating       numeric;
  c_approval     numeric;
  c_sample       numeric;
  c_reach        numeric;
  c_track        numeric;
  v_mode         text;
  v_floor        numeric;
  v_line         numeric;
  v_lv           numeric;
  v_bar          numeric;
  v_target       numeric;
  w_rating       numeric := coalesce((cfg #>> '{weights,rating}')::numeric, 0);
  w_approval     numeric := coalesce((cfg #>> '{weights,approval}')::numeric, 0);
  w_sample       numeric := coalesce((cfg #>> '{weights,sample}')::numeric, 0);
  w_reach        numeric := coalesce((cfg #>> '{weights,reach}')::numeric, 0);
  w_track        numeric := coalesce((cfg #>> '{weights,track}')::numeric, 0);
  v_used         jsonb   := '{}'::jsonb;
  v_denom        numeric := 0;
  v_raw          numeric := 0;
  v_score        numeric;
  v_band         text;
  v_band_out     text;
  v_mv_band      numeric := coalesce((cfg #>> '{min_votes,band}')::numeric, 0);
  v_mv_action    numeric := coalesce((cfg #>> '{min_votes,action}')::numeric, 0);
  v_cap_rating   numeric := (cfg #>> '{caps,rating_line}')::numeric;
  v_cap_approval numeric := (cfg #>> '{caps,approval_bar}')::numeric;
  v_voices       numeric;
  v_enough       boolean;
  v_missed       int := 0;
  v_provisional  boolean := false;
  v_action       text;
begin
  -- ---- reject nonsense outright --------------------------------------------------------------
  if v_n        is not null and v_n        < 0 then v_flags := array_append(v_flags, 'invalid_num_ratings'); end if;
  if v_attended is not null and v_attended < 0 then v_flags := array_append(v_flags, 'invalid_attended');    end if;
  if v_yes      is not null and v_yes      < 0 then v_flags := array_append(v_flags, 'invalid_yes_votes');   end if;
  if v_no       is not null and v_no       < 0 then v_flags := array_append(v_flags, 'invalid_no_votes');    end if;
  if v_rating is not null and (v_rating < 0 or v_rating > v_scale) then
    v_flags := array_append(v_flags, 'invalid_rating');
  end if;
  if cardinality(v_flags) > 0 then
    -- any invalid_* flag → no score
    score := null; band := null; provisional := false; components := '{}'::jsonb;
    if v_escalated then action := 'video'; v_flags := array_append(v_flags, 'escalated'); else action := v_no_data; end if;
    flags := v_flags;
    return next; return;
  end if;
  if v_rating is null or v_rating = 0 then
    v_flags := array_append(v_flags, case when v_rating is null then 'no_rating' else 'rating_zero' end);
    score := null; band := null; provisional := false; components := '{}'::jsonb;
    if v_escalated then action := 'video'; v_flags := array_append(v_flags, 'escalated'); else action := v_no_data; end if;
    flags := v_flags;
    return next; return;
  end if;

  -- ---- derived inputs ------------------------------------------------------------------------
  if v_yes is not null and v_no is not null then
    v_votes := v_yes + v_no;
    if v_votes <= 0 then v_votes := null; end if;
  end if;
  if v_votes is not null then v_approval := v_yes / v_votes * 100; end if;
  if v_approval is null then v_flags := array_append(v_flags, 'no_vote'); end if;
  if v_votes is not null and v_n is not null and abs(v_votes - v_n) > 0.5 then
    v_flags := array_append(v_flags, 'votes_ne_responses');
  end if;
  if v_n is null then v_flags := array_append(v_flags, 'no_responses');
  elsif v_n = 0 then v_flags := array_append(v_flags, 'zero_responses');
  end if;
  if v_attended is null or v_attended = 0 then v_flags := array_append(v_flags, 'no_attendance'); end if;
  if v_n is not null and v_attended is not null and v_attended <> 0 then
    v_reach := v_n / v_attended * 100;
    if v_reach > 100 then v_reach := 100; v_flags := array_append(v_flags, 'reach_clamped'); end if;
  end if;
  if v_approval is not null and v_rating >= 4.5 and v_approval < 50 then
    v_flags := array_append(v_flags, 'rating_vote_disagree');
  end if;

  -- ---- small-sample guard (shrinkage toward the course's typical values) ---------------------
  v_adj_rating := v_rating;
  v_adj_approval := v_approval;
  if v_k > 0 then
    if p_prior_rating is not null and v_n is not null then
      v_adj_rating := (v_n * v_rating + v_k * p_prior_rating) / (v_n + v_k);
    end if;
    if v_approval is not null and p_prior_approval is not null and v_votes is not null then
      v_adj_approval := (v_yes + v_k * p_prior_approval / 100) / (v_votes + v_k) * 100;
    end if;
    if v_adj_rating <> v_rating or v_adj_approval is distinct from v_approval then
      v_flags := array_append(v_flags, 'guarded');
    end if;
  end if;

  -- ---- components ----------------------------------------------------------------------------
  v_mode := coalesce(cfg #>> '{rating,mode}', 'linear');
  if v_mode = 'knee' then
    v_floor := coalesce((cfg #>> '{rating,floor}')::numeric, 3.55);
    v_line  := coalesce((cfg #>> '{rating,line}')::numeric, 4.55);
    v_lv    := coalesce((cfg #>> '{rating,line_value}')::numeric, 75);
    if v_adj_rating <= v_floor then
      c_rating := 0;
    elsif v_adj_rating <= v_line then
      c_rating := (v_adj_rating - v_floor) / (v_line - v_floor) * v_lv;
    else
      c_rating := v_lv + (v_adj_rating - v_line) / (v_scale - v_line) * (100 - v_lv);
    end if;
  else
    c_rating := v_adj_rating / v_scale * 100;
  end if;
  c_rating := greatest(0, least(100, c_rating));

  v_mode  := coalesce(cfg #>> '{approval,mode}', 'cliff');
  v_bar   := coalesce((cfg #>> '{approval,bar}')::numeric, 80);
  v_floor := coalesce((cfg #>> '{approval,floor}')::numeric, 40);
  if v_adj_approval is null then
    c_approval := case when coalesce(cfg #>> '{missing,approval}', 'zero') = 'zero' then 0 else null end;
  elsif v_mode = 'graded' then
    c_approval := greatest(0, least(100, (v_adj_approval - v_floor) / (v_bar - v_floor) * 100));
  else
    c_approval := case when v_adj_approval >= v_bar then 100 else 0 end;
  end if;

  v_mode   := coalesce(cfg #>> '{sample,mode}', 'cliff');
  v_target := coalesce((cfg #>> '{sample,target}')::numeric, 10);
  if v_mode = 'off' then
    c_sample := null;
  elsif v_n is null then
    c_sample := 0;
  elsif v_mode = 'graded' then
    c_sample := greatest(0, least(100, v_n / v_target * 100));
  else
    c_sample := case when v_n >= v_target then 100 else 0 end;
  end if;

  if coalesce(cfg #>> '{reach,mode}', 'graded') = 'off' then
    c_reach := null;
  elsif v_reach is null then
    c_reach := case when coalesce(cfg #>> '{missing,reach}', 'zero') = 'zero' then 0 else null end;
  else
    c_reach := v_reach;
  end if;

  v_mode := coalesce(cfg #>> '{track,mode}', 'off');
  if v_mode <> 'on' or p_track is null then
    c_track := null;
    if v_mode = 'on' and p_track is null then v_flags := array_append(v_flags, 'no_track'); end if;
  else
    v_floor := coalesce((cfg #>> '{track,floor}')::numeric, 4.05);
    v_line  := coalesce((cfg #>> '{track,line}')::numeric, 4.55);
    c_track := greatest(0, least(100, (p_track - v_floor) / (v_line - v_floor) * 100));
  end if;

  -- ---- weighted sum over the INCLUDED components (weights re-scaled) ------------------------
  if c_rating   is not null and w_rating   > 0 then v_denom := v_denom + w_rating;   v_raw := v_raw + c_rating   * w_rating;   v_used := v_used || jsonb_build_object('rating',   w_rating);   end if;
  if c_approval is not null and w_approval > 0 then v_denom := v_denom + w_approval; v_raw := v_raw + c_approval * w_approval; v_used := v_used || jsonb_build_object('approval', w_approval); end if;
  if c_sample   is not null and w_sample   > 0 then v_denom := v_denom + w_sample;   v_raw := v_raw + c_sample   * w_sample;   v_used := v_used || jsonb_build_object('sample',   w_sample);   end if;
  if c_reach    is not null and w_reach    > 0 then v_denom := v_denom + w_reach;    v_raw := v_raw + c_reach    * w_reach;    v_used := v_used || jsonb_build_object('reach',    w_reach);    end if;
  if c_track    is not null and w_track    > 0 then v_denom := v_denom + w_track;    v_raw := v_raw + c_track    * w_track;    v_used := v_used || jsonb_build_object('track',    w_track);    end if;
  v_raw   := case when v_denom > 0 then v_raw / v_denom else 0 end;
  v_score := round(v_raw, 2);

  -- ---- band (from the ROUNDED score), caps, vote floors ---------------------------------------
  v_band := case
    when v_score >= coalesce((cfg #>> '{bands,excellent}')::numeric, 90) then 'excellent'
    when v_score >= coalesce((cfg #>> '{bands,good}')::numeric, 75)      then 'good'
    when v_score >= coalesce((cfg #>> '{bands,average}')::numeric, 60)   then 'average'
    else 'bad' end;

  v_voices := coalesce(v_votes, coalesce(v_n, 0));
  v_enough := v_voices >= v_mv_action;
  if v_cap_rating is not null and v_enough and v_adj_rating < v_cap_rating then
    v_missed := v_missed + 1; v_flags := array_append(v_flags, 'under_rating_line');
  end if;
  if v_cap_approval is not null and v_enough and v_adj_approval is not null and v_adj_approval < v_cap_approval then
    v_missed := v_missed + 1; v_flags := array_append(v_flags, 'under_approval_bar');
  end if;
  if v_missed = 1 then
    if v_band in ('excellent', 'good') then v_band := 'average'; end if;
  elsif v_missed >= 2 then
    v_band := 'bad';
  end if;

  if v_voices < v_mv_band then
    v_band_out := null; v_flags := array_append(v_flags, 'thin_no_band');
  else
    v_band_out := v_band;
    if not v_enough and v_mv_action <> 0 then
      v_provisional := true; v_flags := array_append(v_flags, 'thin_provisional');
    end if;
  end if;

  if v_escalated then
    v_action := 'video'; v_flags := array_append(v_flags, 'escalated');
  elsif v_band_out is null or v_provisional then
    v_action := v_no_data;
  else
    v_action := coalesce(cfg #>> array['actions', v_band_out],
                         case v_band_out when 'bad' then 'video' when 'average' then 'transcript' else 'none' end);
  end if;

  score       := v_score;
  band        := v_band_out;
  action      := v_action;
  provisional := v_provisional;
  flags       := v_flags;
  components  := jsonb_build_object(
    'rating',   round(c_rating, 2),
    'approval', round(c_approval, 2),
    'sample',   round(c_sample, 2),
    'reach',    round(c_reach, 2),
    'track',    round(c_track, 2),
    'weights_used', v_used,
    'adjusted', jsonb_build_object('rating', round(v_adj_rating, 2), 'approval', round(v_adj_approval, 2)),
    'inputs',   jsonb_build_object(
      'rating', v_rating, 'num_ratings', p_num_ratings, 'attended', p_attended,
      'yes_votes', p_yes, 'no_votes', p_no, 'votes', v_votes,
      'approval_pct', round(v_approval, 2), 'reach_pct', round(v_reach, 2),
      'track_avg', p_track, 'prior_rating', p_prior_rating, 'prior_approval', p_prior_approval));
  return next;
  return;
end;
$$;

-- ─────────────────────────────────────────────────────────── active_scoring_config
create or replace function public.active_scoring_config()
returns public.scoring_configs
language sql stable set search_path = public as $$
  select * from public.scoring_configs where status = 'active' limit 1;
$$;

-- ─────────────────────────────────────────────────────────── apply_scoring_config
-- Activate a version and re-score EVERY class in one statement. Admin only (or a direct
-- database session: auth.uid() is null). Returns {version, scored, band_counts, action_counts}.
create or replace function public.apply_scoring_config(p_config_id uuid)
returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  v_cfg           public.scoring_configs%rowtype;
  v_scored        int := 0;
  v_band_counts   jsonb;
  v_action_counts jsonb;
begin
  if auth.uid() is not null and not public.is_admin() then
    raise exception 'apply_scoring_config: admin only' using errcode = '42501';
  end if;
  select * into v_cfg from public.scoring_configs where id = p_config_id;
  if not found then
    raise exception 'apply_scoring_config: config % not found', p_config_id;
  end if;

  -- keep today's rule-v2 verdict once, before the first scoring pass ever rewrites `decision`
  update public.class_ratings set decision_v2 = decision where decision_v2 is null and scored_at is null;

  -- one active row at a time (partial unique index): retire first, then activate
  update public.scoring_configs
     set status = 'retired', retired_at = now()
   where status = 'active' and id <> p_config_id;
  update public.scoring_configs
     set status = 'active', activated_at = now(), retired_at = null
   where id = p_config_id and status <> 'active';

  perform set_config('app.score_reason', 'config:v' || v_cfg.version, true);

  with priors as (
    select c.course_id, p.prior_rating, p.prior_approval
    from (select distinct course_id from public.class_ratings) c
    cross join lateral public.course_priors(c.course_id) p
  ),
  scored as (
    select r.id, s.score, s.band, s.action, s.provisional, s.flags, s.components
    from public.class_ratings r
    left join priors p on p.course_id is not distinct from r.course_id
    cross join lateral public.score_class_rating(
      r.rating, r.num_ratings, r.attended, r.yes_votes, r.no_votes, r.escalated, r.track_avg,
      p.prior_rating, p.prior_approval, v_cfg.config) s
  )
  update public.class_ratings r
     set sentiment_score       = s.score,
         sentiment_band        = s.band,
         sentiment_action      = s.action,
         sentiment_provisional = s.provisional,
         sentiment_flags       = s.flags,
         score_config_id       = p_config_id,
         score_components      = s.components,
         scored_at             = now(),
         decision = case
           when r.decision_override is not null                       then r.decision
           when r.review_status in ('dismissed', 'analysis_started')  then r.decision
           when r.escalated                                           then 'video'::rating_decision
           else s.action::rating_decision end
    from scored s
   where s.id = r.id;
  get diagnostics v_scored = row_count;

  perform set_config('app.score_reason', '', true);

  select coalesce(jsonb_object_agg(coalesce(sentiment_band, 'no_band'), n), '{}'::jsonb) into v_band_counts
  from (select sentiment_band, count(*) n from public.class_ratings group by 1) t;
  select coalesce(jsonb_object_agg(coalesce(sentiment_action, 'none'), n), '{}'::jsonb) into v_action_counts
  from (select sentiment_action, count(*) n from public.class_ratings group by 1) t;

  insert into public.audit_log (actor_id, actor_label, action, detail)
  values (auth.uid(), 'system', 'scoring_config_activated',
          jsonb_build_object('version', v_cfg.version, 'key', v_cfg.key, 'name', v_cfg.name,
                             'config_id', v_cfg.id, 'scored', v_scored,
                             'band_counts', v_band_counts, 'action_counts', v_action_counts));

  return jsonb_build_object('version', v_cfg.version, 'scored', v_scored,
                            'band_counts', v_band_counts, 'action_counts', v_action_counts);
end;
$$;
revoke all on function public.apply_scoring_config(uuid) from public, anon;
grant execute on function public.apply_scoring_config(uuid) to authenticated, service_role;

-- ─────────────────────────────────────────────────────────── scoring_whatif_summary
-- Score the rows in a window with ANY config (stored or not) and summarise what would change.
-- SECURITY INVOKER: reads class_ratings under the caller's own RLS.
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
           (to_band is not null and (
              (band_vote_flip   is not null and band_vote_flip   is distinct from to_band) or
              (band_rating_drop is not null and band_rating_drop is distinct from to_band))) as flipped
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
    'flip_share',    round(coalesce((select count(*) filter (where flipped) from flips)::numeric
                                    / nullif((select count(*) filter (where to_band is not null) from flips), 0), 0), 4)
  ) into v_result;

  return v_result;
end;
$$;
revoke all on function public.scoring_whatif_summary(jsonb, date, date) from public, anon;
grant execute on function public.scoring_whatif_summary(jsonb, date, date) to authenticated, service_role;

-- ───────────────────────────────────────────────────────────────────────── seed
-- The six candidate configurations from supabase/fixtures/scoring_configs.json (embedded verbatim).
-- Versions 1–6 = C0–C5. Inserted as drafts; C0 becomes active only if nothing is active yet
-- (a re-run never flips the team's chosen version).
insert into public.scoring_configs (version, key, name, status, config, note)
values
  (1, 'C0', 'Manager''s original (60/30/6/4, pass/fail)', 'draft',
   $cfg${"name":"Manager's original (60/30/6/4, pass/fail)","rating":{"mode":"linear","scale":5,"floor":3.55,"line":4.55,"line_value":75},"approval":{"mode":"cliff","bar":80,"floor":40},"sample":{"mode":"cliff","target":10},"reach":{"mode":"graded"},"track":{"mode":"off","floor":4.05,"line":4.55,"min_classes":3},"weights":{"rating":60,"approval":30,"sample":6,"reach":4,"track":0},"guard":{"k":0,"prior":"course"},"min_votes":{"band":0,"action":0},"caps":{"rating_line":null,"approval_bar":null},"bands":{"excellent":90,"good":75,"average":60},"missing":{"approval":"zero","reach":"zero","track":"neutral"},"actions":{"bad":"video","average":"transcript","good":"none","excellent":"none","no_data":"watch"}}$cfg$::jsonb,
   'Seeded by migration 0015 from supabase/fixtures/scoring_configs.json'),
  (2, 'C1', 'Original + minimum votes', 'draft',
   $cfg${"name":"Original + minimum votes","rating":{"mode":"linear","scale":5,"floor":3.55,"line":4.55,"line_value":75},"approval":{"mode":"cliff","bar":80,"floor":40},"sample":{"mode":"cliff","target":10},"reach":{"mode":"graded"},"track":{"mode":"off","floor":4.05,"line":4.55,"min_classes":3},"weights":{"rating":60,"approval":30,"sample":6,"reach":4,"track":0},"guard":{"k":0,"prior":"course"},"min_votes":{"band":5,"action":5},"caps":{"rating_line":null,"approval_bar":null},"bands":{"excellent":90,"good":75,"average":60},"missing":{"approval":"zero","reach":"zero","track":"neutral"},"actions":{"bad":"video","average":"transcript","good":"none","excellent":"none","no_data":"watch"}}$cfg$::jsonb,
   'Seeded by migration 0015 from supabase/fixtures/scoring_configs.json'),
  (3, 'C2', 'Graded approval', 'draft',
   $cfg${"name":"Graded approval","rating":{"mode":"linear","scale":5,"floor":3.55,"line":4.55,"line_value":75},"approval":{"mode":"graded","bar":80,"floor":40},"sample":{"mode":"cliff","target":10},"reach":{"mode":"graded"},"track":{"mode":"off","floor":4.05,"line":4.55,"min_classes":3},"weights":{"rating":60,"approval":30,"sample":6,"reach":4,"track":0},"guard":{"k":0,"prior":"course"},"min_votes":{"band":0,"action":0},"caps":{"rating_line":null,"approval_bar":null},"bands":{"excellent":90,"good":75,"average":60},"missing":{"approval":"neutral","reach":"neutral","track":"neutral"},"actions":{"bad":"video","average":"transcript","good":"none","excellent":"none","no_data":"watch"}}$cfg$::jsonb,
   'Seeded by migration 0015 from supabase/fixtures/scoring_configs.json'),
  (4, 'C3', 'Graded + small-sample guard', 'draft',
   $cfg${"name":"Graded + small-sample guard","rating":{"mode":"linear","scale":5,"floor":3.55,"line":4.55,"line_value":75},"approval":{"mode":"graded","bar":80,"floor":40},"sample":{"mode":"graded","target":10},"reach":{"mode":"graded"},"track":{"mode":"off","floor":4.05,"line":4.55,"min_classes":3},"weights":{"rating":60,"approval":30,"sample":6,"reach":4,"track":0},"guard":{"k":5,"prior":"course"},"min_votes":{"band":3,"action":5},"caps":{"rating_line":null,"approval_bar":null},"bands":{"excellent":90,"good":75,"average":60},"missing":{"approval":"neutral","reach":"neutral","track":"neutral"},"actions":{"bad":"video","average":"transcript","good":"none","excellent":"none","no_data":"watch"}}$cfg$::jsonb,
   'Seeded by migration 0015 from supabase/fixtures/scoring_configs.json'),
  (5, 'C4', 'Data-derived weights', 'draft',
   $cfg${"name":"Data-derived weights","rating":{"mode":"knee","scale":5,"floor":3.55,"line":4.55,"line_value":75},"approval":{"mode":"graded","bar":80,"floor":40},"sample":{"mode":"off","target":10},"reach":{"mode":"off"},"track":{"mode":"on","floor":4.05,"line":4.55,"min_classes":3},"weights":{"rating":60,"approval":25,"sample":0,"reach":0,"track":15},"guard":{"k":5,"prior":"course"},"min_votes":{"band":3,"action":5},"caps":{"rating_line":null,"approval_bar":null},"bands":{"excellent":90,"good":75,"average":60},"missing":{"approval":"neutral","reach":"neutral","track":"neutral"},"actions":{"bad":"video","average":"transcript","good":"none","excellent":"none","no_data":"watch"}}$cfg$::jsonb,
   'Seeded by migration 0015 from supabase/fixtures/scoring_configs.json'),
  (6, 'C5', 'Two lines + graded score', 'draft',
   $cfg${"name":"Two lines + graded score","rating":{"mode":"knee","scale":5,"floor":3.55,"line":4.55,"line_value":75},"approval":{"mode":"graded","bar":80,"floor":40},"sample":{"mode":"off","target":10},"reach":{"mode":"off"},"track":{"mode":"on","floor":4.05,"line":4.55,"min_classes":3},"weights":{"rating":60,"approval":25,"sample":0,"reach":0,"track":15},"guard":{"k":5,"prior":"course"},"min_votes":{"band":3,"action":5},"caps":{"rating_line":4.55,"approval_bar":80},"bands":{"excellent":90,"good":75,"average":60},"missing":{"approval":"neutral","reach":"neutral","track":"neutral"},"actions":{"bad":"video","average":"transcript","good":"none","excellent":"none","no_data":"watch"}}$cfg$::jsonb,
   'Seeded by migration 0015 from supabase/fixtures/scoring_configs.json')
on conflict (version) do nothing;

update public.scoring_configs
   set status = 'active', activated_at = coalesce(activated_at, now()), retired_at = null
 where key = 'C0'
   and not exists (select 1 from public.scoring_configs where status = 'active');

-- Score every row that has never been scored, under the active version (C0 on first run).
do $$
declare
  v_active uuid;
begin
  select id into v_active from public.scoring_configs where status = 'active';
  if v_active is not null
     and exists (select 1 from public.class_ratings where score_config_id is null) then
    perform public.apply_scoring_config(v_active);
  end if;
end $$;
