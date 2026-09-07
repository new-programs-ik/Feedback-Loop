-- 0016_instructor_identity.sql — one instructor, many spellings.
--
-- The sheet records the same person under several names ("Kalpesh Singh" / "Kalpesh"). This adds
-- the alias table (any spelling → one instructor), the suggestion queue the worker's matcher fills
-- after every sync, soft + reversible merges, and the canonical name on every class row.
--
--   normalize_person_name(text)    lower · unaccent · keep [a-z0-9 ] · collapse spaces · trim
--                                  ('' → null). The worker mirrors this rule exactly.
--   instructors.normalized_name    generated from name; merged_into / merged_at (soft merge)
--   instructor_aliases             alias_norm (unique) → instructor_id; source sheet|manual|merge|import
--   instructor_match_suggestions   raw_name → candidate, score + evidence; pending|accepted|rejected
--   instructor_merges              every moved row id, so undo can replay in reverse
--   class_ratings.instructor_canonical  the resolved instructor's display name
--
-- RPCs (SECURITY DEFINER; admin only — or a direct database session where auth.uid() is null):
--   accept_instructor_suggestion(p_id)          alias + link every class row with that raw name
--   reject_instructor_suggestion(p_id)          never suggested again
--   add_instructor_alias(p_alias, p_instructor) alias + link rows
--   merge_instructors(p_from, p_into) → uuid    soft merge: alias, repoint every table, record ids
--   undo_instructor_merge(p_merge_id)           replay in reverse
--
-- Only EXACT normalised matches are linked automatically (the backfill at the bottom, and only
-- when the normalised name is unambiguous); everything else is a suggestion a human accepts.
-- Additive and idempotent; safe to re-run.

create extension if not exists unaccent with schema extensions;

-- unaccent() is STABLE (dictionary-dependent); a generated column needs IMMUTABLE. The wrapper
-- pins the dictionary explicitly — the documented way to index on unaccent.
create or replace function public.immutable_unaccent(p text)
returns text language sql immutable strict parallel safe
set search_path = public as $$
  select extensions.unaccent('extensions.unaccent'::regdictionary, p);
$$;

create or replace function public.normalize_person_name(p text)
returns text language sql immutable parallel safe
set search_path = public as $$
  select nullif(trim(regexp_replace(
           regexp_replace(lower(public.immutable_unaccent(coalesce(p, ''))), '[^a-z0-9 ]', '', 'g'),
           ' +', ' ', 'g')), '');
$$;

-- ───────────────────────────────────────────────────────────────────── instructors
alter table public.instructors
  add column if not exists normalized_name text generated always as (public.normalize_person_name(name)) stored,
  add column if not exists merged_into     uuid references public.instructors(id) on delete set null,
  add column if not exists merged_at       timestamptz;
create index if not exists idx_instructors_normalized_name on public.instructors (normalized_name);
create index if not exists idx_instructors_merged_into     on public.instructors (merged_into);

-- ──────────────────────────────────────────────────────────────── the new tables
create table if not exists public.instructor_aliases (
  id            uuid primary key default gen_random_uuid(),
  alias         text not null,
  alias_norm    text not null unique,
  instructor_id uuid not null references public.instructors(id) on delete cascade,
  source        text check (source in ('sheet','manual','merge','import')),
  created_by    uuid references auth.users(id) on delete set null,
  created_at    timestamptz not null default now()
);
create index if not exists idx_instructor_aliases_instructor on public.instructor_aliases (instructor_id);

create table if not exists public.instructor_match_suggestions (
  id                      uuid primary key default gen_random_uuid(),
  raw_name                text not null,
  raw_norm                text not null,
  candidate_instructor_id uuid not null references public.instructors(id) on delete cascade,
  score                   numeric(4,3),
  method                  text,
  evidence                jsonb,
  status                  text not null default 'pending' check (status in ('pending','accepted','rejected')),
  first_seen_at           timestamptz not null default now(),
  last_seen_at            timestamptz not null default now(),
  decided_by              uuid references auth.users(id) on delete set null,
  decided_at              timestamptz,
  unique (raw_norm, candidate_instructor_id)
);
create index if not exists idx_instructor_suggestions_status on public.instructor_match_suggestions (status, score desc);

create table if not exists public.instructor_merges (
  id                 uuid primary key default gen_random_uuid(),
  from_instructor_id uuid not null references public.instructors(id) on delete cascade,
  into_instructor_id uuid not null references public.instructors(id) on delete cascade,
  moved              jsonb not null default '{}'::jsonb,
  performed_by       uuid references auth.users(id) on delete set null,
  performed_at       timestamptz not null default now(),
  undone_by          uuid references auth.users(id) on delete set null,
  undone_at          timestamptz
);
create index if not exists idx_instructor_merges_from on public.instructor_merges (from_instructor_id);

alter table public.class_ratings add column if not exists instructor_canonical text;
create index if not exists idx_class_ratings_instructor_id_date on public.class_ratings (instructor_id, class_date);

-- ─────────────────────────────────────────────────────────────────────────── RLS
alter table public.instructor_aliases           enable row level security;
alter table public.instructor_match_suggestions enable row level security;
alter table public.instructor_merges            enable row level security;

drop policy if exists instructor_aliases_select on public.instructor_aliases;
create policy instructor_aliases_select on public.instructor_aliases
  for select to authenticated using (true);
drop policy if exists instructor_aliases_admin on public.instructor_aliases;
create policy instructor_aliases_admin on public.instructor_aliases
  for all to authenticated using (public.is_admin()) with check (public.is_admin());

drop policy if exists instructor_suggestions_select on public.instructor_match_suggestions;
create policy instructor_suggestions_select on public.instructor_match_suggestions
  for select to authenticated using (true);
drop policy if exists instructor_suggestions_admin on public.instructor_match_suggestions;
create policy instructor_suggestions_admin on public.instructor_match_suggestions
  for all to authenticated using (public.is_admin()) with check (public.is_admin());

drop policy if exists instructor_merges_admin on public.instructor_merges;
create policy instructor_merges_admin on public.instructor_merges
  for all to authenticated using (public.is_admin()) with check (public.is_admin());

-- ──────────────────────────────────────────────────────────────────────── helpers
create or replace function public.assert_admin_or_service()
returns void language plpgsql stable set search_path = public as $$
begin
  if auth.uid() is not null and not public.is_admin() then
    raise exception 'admin only' using errcode = '42501';
  end if;
end;
$$;

-- Follow merged_into to the surviving instructor (bounded, in case of a cycle).
create or replace function public.canonical_instructor_id(p_id uuid)
returns uuid language plpgsql stable set search_path = public as $$
declare
  v_id   uuid := p_id;
  v_next uuid;
  i      int := 0;
begin
  loop
    select merged_into into v_next from public.instructors where id = v_id;
    exit when v_next is null or i >= 10;
    v_id := v_next;
    i := i + 1;
  end loop;
  return v_id;
end;
$$;

-- Link every class row whose normalised raw name is p_norm to one instructor. Internal.
create or replace function public.link_class_ratings_to_instructor(p_norm text, p_instructor_id uuid)
returns int language plpgsql security definer set search_path = public as $$
declare
  v_name text;
  v_n    int;
begin
  if p_norm is null then return 0; end if;
  select name into v_name from public.instructors where id = p_instructor_id;
  if v_name is null then
    raise exception 'instructor % not found', p_instructor_id;
  end if;
  update public.class_ratings
     set instructor_id = p_instructor_id, instructor_canonical = v_name
   where public.normalize_person_name(instructor) = p_norm
     and (instructor_id is distinct from p_instructor_id or instructor_canonical is distinct from v_name);
  get diagnostics v_n = row_count;
  return v_n;
end;
$$;
revoke all on function public.link_class_ratings_to_instructor(text, uuid) from public, anon, authenticated;

-- ────────────────────────────────────────────────────────────────────────── RPCs
create or replace function public.accept_instructor_suggestion(p_id uuid)
returns jsonb language plpgsql security definer set search_path = public as $$
declare
  s          public.instructor_match_suggestions%rowtype;
  v_target   uuid;
  v_alias_id uuid;
  v_linked   int;
begin
  perform public.assert_admin_or_service();
  select * into s from public.instructor_match_suggestions where id = p_id for update;
  if not found then raise exception 'suggestion % not found', p_id; end if;
  if s.status <> 'pending' then raise exception 'suggestion % is already %', p_id, s.status; end if;

  v_target := public.canonical_instructor_id(s.candidate_instructor_id);
  insert into public.instructor_aliases (alias, alias_norm, instructor_id, source, created_by)
  values (s.raw_name, s.raw_norm, v_target, 'sheet', auth.uid())
  on conflict (alias_norm) do update
    set instructor_id = excluded.instructor_id, alias = excluded.alias,
        source = 'sheet', created_by = excluded.created_by
  returning id into v_alias_id;

  v_linked := public.link_class_ratings_to_instructor(s.raw_norm, v_target);

  update public.instructor_match_suggestions
     set status = 'accepted', decided_by = auth.uid(), decided_at = now()
   where id = p_id;
  -- the raw name is resolved: its other candidates were not the same person
  update public.instructor_match_suggestions
     set status = 'rejected', decided_by = auth.uid(), decided_at = now()
   where raw_norm = s.raw_norm and status = 'pending' and id <> p_id;

  insert into public.audit_log (actor_id, actor_label, action, detail)
  values (auth.uid(), case when auth.uid() is null then 'system' end, 'instructor_alias_accepted',
          jsonb_build_object('suggestion_id', p_id, 'raw_name', s.raw_name,
                             'instructor_id', v_target, 'linked_rows', v_linked));
  return jsonb_build_object('suggestion_id', p_id, 'instructor_id', v_target,
                            'alias_id', v_alias_id, 'linked_rows', v_linked);
end;
$$;

create or replace function public.reject_instructor_suggestion(p_id uuid)
returns jsonb language plpgsql security definer set search_path = public as $$
declare
  v_status text;
begin
  perform public.assert_admin_or_service();
  select status into v_status from public.instructor_match_suggestions where id = p_id for update;
  if not found then raise exception 'suggestion % not found', p_id; end if;
  if v_status <> 'pending' then raise exception 'suggestion % is already %', p_id, v_status; end if;
  update public.instructor_match_suggestions
     set status = 'rejected', decided_by = auth.uid(), decided_at = now()
   where id = p_id;
  return jsonb_build_object('suggestion_id', p_id, 'status', 'rejected');
end;
$$;

create or replace function public.add_instructor_alias(p_alias text, p_instructor_id uuid)
returns jsonb language plpgsql security definer set search_path = public as $$
declare
  v_norm     text := public.normalize_person_name(p_alias);
  v_target   uuid;
  v_alias_id uuid;
  v_linked   int;
begin
  perform public.assert_admin_or_service();
  if v_norm is null then raise exception 'alias is blank'; end if;
  v_target := public.canonical_instructor_id(p_instructor_id);
  if not exists (select 1 from public.instructors where id = v_target) then
    raise exception 'instructor % not found', p_instructor_id;
  end if;
  insert into public.instructor_aliases (alias, alias_norm, instructor_id, source, created_by)
  values (trim(p_alias), v_norm, v_target, 'manual', auth.uid())
  on conflict (alias_norm) do update
    set instructor_id = excluded.instructor_id, alias = excluded.alias,
        source = 'manual', created_by = excluded.created_by
  returning id into v_alias_id;
  v_linked := public.link_class_ratings_to_instructor(v_norm, v_target);
  -- a pending suggestion for this spelling is now moot
  update public.instructor_match_suggestions
     set status = case when candidate_instructor_id = v_target then 'accepted' else 'rejected' end,
         decided_by = auth.uid(), decided_at = now()
   where raw_norm = v_norm and status = 'pending';
  insert into public.audit_log (actor_id, actor_label, action, detail)
  values (auth.uid(), case when auth.uid() is null then 'system' end, 'instructor_alias_added',
          jsonb_build_object('alias', p_alias, 'instructor_id', v_target, 'linked_rows', v_linked));
  return jsonb_build_object('alias_id', v_alias_id, 'instructor_id', v_target, 'linked_rows', v_linked);
end;
$$;

-- Soft merge: p_from keeps its row (merged_into = p_into); every reference moves to p_into and the
-- moved ids are recorded so undo_instructor_merge() can put them back.
create or replace function public.merge_instructors(p_from uuid, p_into uuid)
returns uuid language plpgsql security definer set search_path = public as $$
declare
  v_from          public.instructors%rowtype;
  v_into          public.instructors%rowtype;
  a_ratings       uuid[];
  a_classes       uuid[];
  a_cc_live       uuid[];
  a_cc_review     uuid[];
  a_cc_coaching   uuid[];
  a_catalog       uuid[];
  a_aliases       uuid[];
  v_alias_created uuid;
  v_moved         jsonb;
  v_merge_id      uuid;
begin
  perform public.assert_admin_or_service();
  if p_from is null or p_into is null or p_from = p_into then
    raise exception 'merge needs two different instructors';
  end if;
  select * into v_from from public.instructors where id = p_from for update;
  if not found then raise exception 'instructor % not found', p_from; end if;
  select * into v_into from public.instructors where id = p_into for update;
  if not found then raise exception 'instructor % not found', p_into; end if;
  if v_from.merged_into is not null then
    raise exception '% is already merged into another instructor', v_from.name;
  end if;
  if v_into.merged_into is not null then
    raise exception '% is itself merged; merge into % instead', v_into.name, public.canonical_instructor_id(p_into);
  end if;

  with u as (
    update public.class_ratings set instructor_id = p_into, instructor_canonical = v_into.name
     where instructor_id = p_from returning id)
  select coalesce(array_agg(id), '{}') into a_ratings from u;

  with u as (
    update public.classes set instructor_id = p_into, updated_at = now()
     where instructor_id = p_from returning id)
  select coalesce(array_agg(id), '{}') into a_classes from u;

  with u as (
    update public.cohort_classes set instructor_id = p_into, updated_at = now()
     where instructor_id = p_from returning id)
  select coalesce(array_agg(id), '{}') into a_cc_live from u;
  with u as (
    update public.cohort_classes set review_instructor_id = p_into, updated_at = now()
     where review_instructor_id = p_from returning id)
  select coalesce(array_agg(id), '{}') into a_cc_review from u;
  with u as (
    update public.cohort_classes set coaching_instructor_id = p_into, updated_at = now()
     where coaching_instructor_id = p_from returning id)
  select coalesce(array_agg(id), '{}') into a_cc_coaching from u;

  with u as (
    update public.class_catalog set instructor_id = p_into
     where instructor_id = p_from returning id)
  select coalesce(array_agg(id), '{}') into a_catalog from u;

  -- every spelling that pointed at p_from now points at p_into
  with u as (
    update public.instructor_aliases set instructor_id = p_into
     where instructor_id = p_from returning id)
  select coalesce(array_agg(id), '{}') into a_aliases from u;

  -- and p_from's own name becomes an alias of p_into (unless that spelling is already an alias)
  if v_from.normalized_name is not null then
    insert into public.instructor_aliases (alias, alias_norm, instructor_id, source, created_by)
    values (v_from.name, v_from.normalized_name, p_into, 'merge', auth.uid())
    on conflict (alias_norm) do nothing
    returning id into v_alias_created;
  end if;

  update public.instructors set merged_into = p_into, merged_at = now() where id = p_from;

  v_moved := jsonb_build_object(
    'from_name', v_from.name, 'into_name', v_into.name,
    'class_ratings', to_jsonb(a_ratings),
    'classes', to_jsonb(a_classes),
    'cohort_classes_instructor', to_jsonb(a_cc_live),
    'cohort_classes_review', to_jsonb(a_cc_review),
    'cohort_classes_coaching', to_jsonb(a_cc_coaching),
    'class_catalog', to_jsonb(a_catalog),
    'aliases_repointed', to_jsonb(a_aliases),
    'alias_created', v_alias_created,
    'counts', jsonb_build_object(
      'class_ratings', cardinality(a_ratings), 'classes', cardinality(a_classes),
      'cohort_classes', cardinality(a_cc_live) + cardinality(a_cc_review) + cardinality(a_cc_coaching),
      'class_catalog', cardinality(a_catalog), 'aliases', cardinality(a_aliases)));

  insert into public.instructor_merges (from_instructor_id, into_instructor_id, moved, performed_by)
  values (p_from, p_into, v_moved, auth.uid())
  returning id into v_merge_id;

  insert into public.audit_log (actor_id, actor_label, action, detail)
  values (auth.uid(), case when auth.uid() is null then 'system' end, 'instructor_merged',
          jsonb_build_object('merge_id', v_merge_id, 'from', p_from, 'into', p_into,
                             'from_name', v_from.name, 'into_name', v_into.name,
                             'counts', v_moved->'counts'));
  return v_merge_id;
end;
$$;

create or replace function public.undo_instructor_merge(p_merge_id uuid)
returns jsonb language plpgsql security definer set search_path = public as $$
declare
  m           public.instructor_merges%rowtype;
  v_from_name text;
  ids         uuid[];
begin
  perform public.assert_admin_or_service();
  select * into m from public.instructor_merges where id = p_merge_id for update;
  if not found then raise exception 'merge % not found', p_merge_id; end if;
  if m.undone_at is not null then raise exception 'merge % was already undone', p_merge_id; end if;
  select name into v_from_name from public.instructors where id = m.from_instructor_id;
  if v_from_name is null then raise exception 'the merged instructor row no longer exists'; end if;

  ids := array(select jsonb_array_elements_text(coalesce(m.moved->'class_ratings', '[]'::jsonb)))::uuid[];
  update public.class_ratings set instructor_id = m.from_instructor_id, instructor_canonical = v_from_name
   where id = any(ids);

  ids := array(select jsonb_array_elements_text(coalesce(m.moved->'classes', '[]'::jsonb)))::uuid[];
  update public.classes set instructor_id = m.from_instructor_id, updated_at = now() where id = any(ids);

  ids := array(select jsonb_array_elements_text(coalesce(m.moved->'cohort_classes_instructor', '[]'::jsonb)))::uuid[];
  update public.cohort_classes set instructor_id = m.from_instructor_id, updated_at = now() where id = any(ids);
  ids := array(select jsonb_array_elements_text(coalesce(m.moved->'cohort_classes_review', '[]'::jsonb)))::uuid[];
  update public.cohort_classes set review_instructor_id = m.from_instructor_id, updated_at = now() where id = any(ids);
  ids := array(select jsonb_array_elements_text(coalesce(m.moved->'cohort_classes_coaching', '[]'::jsonb)))::uuid[];
  update public.cohort_classes set coaching_instructor_id = m.from_instructor_id, updated_at = now() where id = any(ids);

  ids := array(select jsonb_array_elements_text(coalesce(m.moved->'class_catalog', '[]'::jsonb)))::uuid[];
  update public.class_catalog set instructor_id = m.from_instructor_id where id = any(ids);

  ids := array(select jsonb_array_elements_text(coalesce(m.moved->'aliases_repointed', '[]'::jsonb)))::uuid[];
  update public.instructor_aliases set instructor_id = m.from_instructor_id where id = any(ids);

  if (m.moved->>'alias_created') is not null then
    delete from public.instructor_aliases where id = (m.moved->>'alias_created')::uuid;
  end if;

  update public.instructors set merged_into = null, merged_at = null where id = m.from_instructor_id;
  update public.instructor_merges set undone_by = auth.uid(), undone_at = now() where id = p_merge_id;

  insert into public.audit_log (actor_id, actor_label, action, detail)
  values (auth.uid(), case when auth.uid() is null then 'system' end, 'instructor_merge_undone',
          jsonb_build_object('merge_id', p_merge_id, 'from', m.from_instructor_id,
                             'into', m.into_instructor_id, 'counts', m.moved->'counts'));
  return jsonb_build_object('merge_id', p_merge_id, 'restored', m.moved->'counts');
end;
$$;

-- admin-checked inside; never callable with the anon key
revoke all on function public.accept_instructor_suggestion(uuid) from public, anon;
revoke all on function public.reject_instructor_suggestion(uuid) from public, anon;
revoke all on function public.add_instructor_alias(text, uuid)   from public, anon;
revoke all on function public.merge_instructors(uuid, uuid)      from public, anon;
revoke all on function public.undo_instructor_merge(uuid)        from public, anon;
grant execute on function public.accept_instructor_suggestion(uuid) to authenticated, service_role;
grant execute on function public.reject_instructor_suggestion(uuid) to authenticated, service_role;
grant execute on function public.add_instructor_alias(text, uuid)   to authenticated, service_role;
grant execute on function public.merge_instructors(uuid, uuid)      to authenticated, service_role;
grant execute on function public.undo_instructor_merge(uuid)        to authenticated, service_role;

-- ────────────────────────────────────────────────────────────────────── backfill
-- 1) every instructor's own name is an alias of itself — only where the normalised name is
--    unambiguous (two rows normalising the same, e.g. "Jacob" / "jacob", wait for a merge)
with unique_norms as (
  select normalized_name, min(id::text)::uuid as id
  from public.instructors
  where normalized_name is not null and merged_into is null
  group by normalized_name having count(*) = 1
)
insert into public.instructor_aliases (alias, alias_norm, instructor_id, source)
select i.name, i.normalized_name, i.id, 'import'
from unique_norms u join public.instructors i on i.id = u.id
on conflict (alias_norm) do nothing;

-- 2) link class rows whose normalised raw name matches an alias (exact spelling matches only)
update public.class_ratings r
   set instructor_id = a.instructor_id, instructor_canonical = i.name
  from public.instructor_aliases a
  join public.instructors i on i.id = a.instructor_id
 where r.instructor_id is null
   and public.normalize_person_name(r.instructor) = a.alias_norm;

-- 3) rows already linked get their canonical name
update public.class_ratings r
   set instructor_canonical = i.name
  from public.instructors i
 where i.id = r.instructor_id and r.instructor_canonical is distinct from i.name;
