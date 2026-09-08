-- 0022_accept_merges_records.sql
--
-- Accepting a duplicate-name suggestion ("this spelling is that person") when the spelling already
-- has its OWN instructor record must merge the two records - not just add an alias. Otherwise the
-- next sync resolves the spelling to its own record again (records win over aliases in the
-- resolver) and silently undoes the decision, and the thin record lingers as an empty identity.
--
-- The alias path is unchanged for spellings that have no record. A merge made this way is a normal
-- merge: it appears under "Recent merges" and can be undone for 30 days.
--
-- Additive and idempotent (create or replace).

create or replace function public.accept_instructor_suggestion(p_id uuid)
returns jsonb language plpgsql security definer set search_path = public as $$
declare
  s          public.instructor_match_suggestions%rowtype;
  v_target   uuid;
  v_own      uuid;
  v_alias_id uuid;
  v_merge_id uuid;
  v_linked   int := 0;
begin
  perform public.assert_admin_or_service();
  select * into s from public.instructor_match_suggestions where id = p_id for update;
  if not found then raise exception 'suggestion % not found', p_id; end if;
  if s.status <> 'pending' then raise exception 'suggestion % is already %', p_id, s.status; end if;

  v_target := public.canonical_instructor_id(s.candidate_instructor_id);

  -- Is the spelling an instructor record's own name (a live record, other than the target)?
  select id into v_own
    from public.instructors
   where normalized_name = s.raw_norm and merged_into is null and id <> v_target
   order by created_at
   limit 1;

  if v_own is not null then
    v_merge_id := public.merge_instructors(v_own, v_target);   -- moves rows + aliases, undoable
  else
    insert into public.instructor_aliases (alias, alias_norm, instructor_id, source, created_by)
    values (s.raw_name, s.raw_norm, v_target, 'sheet', auth.uid())
    on conflict (alias_norm) do update
      set instructor_id = excluded.instructor_id, alias = excluded.alias,
          source = 'sheet', created_by = excluded.created_by
    returning id into v_alias_id;
  end if;

  -- rows recorded under the spelling that were never linked (imported before any record existed)
  v_linked := public.link_class_ratings_to_instructor(s.raw_norm, v_target);

  update public.instructor_match_suggestions
     set status = 'accepted', decided_by = auth.uid(), decided_at = now()
   where id = p_id;
  -- the spelling is resolved: its other candidates were not the same person
  update public.instructor_match_suggestions
     set status = 'rejected', decided_by = auth.uid(), decided_at = now()
   where raw_norm = s.raw_norm and status = 'pending' and id <> p_id;

  insert into public.audit_log (actor_id, actor_label, action, detail)
  values (auth.uid(), case when auth.uid() is null then 'system' end, 'instructor_alias_accepted',
          jsonb_build_object('suggestion_id', p_id, 'raw_name', s.raw_name,
                             'instructor_id', v_target, 'linked_rows', v_linked,
                             'merged_record', v_own, 'merge_id', v_merge_id));
  return jsonb_build_object('suggestion_id', p_id, 'instructor_id', v_target,
                            'alias_id', v_alias_id, 'linked_rows', v_linked,
                            'merged_record', v_own, 'merge_id', v_merge_id);
end;
$$;

revoke all on function public.accept_instructor_suggestion(uuid) from public, anon;
grant execute on function public.accept_instructor_suggestion(uuid) to authenticated, service_role;
