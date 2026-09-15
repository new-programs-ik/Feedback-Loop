-- 0025 - too few responses: no band, but a low rating is still read
--
-- Below `min_votes.band` responses a class gets no band and no automatic analysis. With
-- `min_votes.low_rating_line` set, a class under the floor that is rated below that line is banded
-- Average instead, so its transcript is read (Sreejit's rule: below 4.3 always gets at least a
-- transcript). Classes at or above the floor score exactly as before.
--
-- Read from the configuration; no version before v10 carries the key, so their scores do not change.
-- Same signature as 0015/0024, so no caller changes. Additive and safe to re-run.

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
  v_low_line     numeric := (cfg #>> '{min_votes,low_rating_line}')::numeric;
  v_thin_min     numeric := (cfg #>> '{thin,min_answers}')::numeric;
  v_thin_line    numeric := (cfg #>> '{thin,rating_line}')::numeric;
  v_is_thin      boolean := false;
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

  -- Too few approval answers: approval may warn, never vouch. A failing approval from a small
  -- group still counts; a passing one no longer lifts the score.
  v_is_thin := v_thin_min is not null and v_votes is not null and v_votes < v_thin_min;
  if v_is_thin and v_adj_approval is not null and v_adj_approval >= v_bar then
    c_approval := null;
    v_flags := array_append(v_flags, 'thin_approval_not_counted');
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

  -- With approval untrustworthy the rating carries the decision alone. Caps at Average, never
  -- pushes to Bad.
  if v_is_thin and v_thin_line is not null and v_adj_rating < v_thin_line then
    if v_band in ('excellent', 'good') then v_band := 'average'; end if;
    v_flags := array_append(v_flags, 'thin_under_rating_line');
  end if;

  if v_voices < v_mv_band and v_low_line is not null and v_adj_rating < v_low_line then
    -- too few responses to judge the class, but rated low enough that the transcript is read anyway
    v_band_out := 'average'; v_flags := array_append(v_flags, 'thin_low_rating_read');
  elsif v_voices < v_mv_band then
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
