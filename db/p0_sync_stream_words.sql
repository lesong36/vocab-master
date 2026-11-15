create or replace function private.vocab_project_words_v3(p_user_id uuid,p_epoch uuid,old_p jsonb,new_p jsonb,baseline_profile jsonb,added_ids text[],ignored jsonb,is_baseline boolean)
returns table(prior_word jsonb,projected_word jsonb) language plpgsql set search_path=pg_catalog,public as $$
declare old_words jsonb; old_word jsonb; new_word jsonb; chosen jsonb; baseline_word jsonb; baseline_word_map jsonb; e jsonb;
 count_correct integer; count_incorrect integer; streak integer; cleared boolean;
begin
 select coalesce(jsonb_object_agg(w->>'id',w),'{}'::jsonb) into baseline_word_map
 from jsonb_array_elements(coalesce(baseline_profile->'words','[]'::jsonb)) w;
  old_words := coalesce(old_p->'words','[]'::jsonb);
  for old_word,new_word in
    select a.value,b.value from jsonb_array_elements(old_words) with ordinality a(value,position)
      full join jsonb_array_elements(coalesce(new_p->'words','[]'::jsonb)) with ordinality b(value,position)
        on a.value->>'id'=b.value->>'id'
      order by coalesce(a.position,jsonb_array_length(old_words)+b.position)
  loop
    chosen := case when coalesce(old_word->>'vocabMasterProgressUpdatedAt','') > coalesce(new_word->>'vocabMasterProgressUpdatedAt','')
      then coalesce(new_word,'{}'::jsonb) || old_word else coalesce(old_word,'{}'::jsonb) || coalesce(new_word,'{}'::jsonb) end;
    if ignored ? (chosen->>'id') then prior_word:=old_word; projected_word:=null; return next; continue; end if;
    if is_baseline then
      count_correct := greatest(0,coalesce((chosen->>'correctCount')::integer,0));
      count_incorrect := greatest(0,coalesce((chosen->>'incorrectCount')::integer,0));
      streak := greatest(0,coalesce((chosen->>'consecutiveCorrect')::integer,0));
      cleared := coalesce((chosen->>'mistakeCleared')::boolean,false);
    else
      count_correct := greatest(0,coalesce((old_word->>'correctCount')::integer,0));
      count_incorrect := greatest(0,coalesce((old_word->>'incorrectCount')::integer,0));
      streak := greatest(0,coalesce((old_word->>'consecutiveCorrect')::integer,0));
      cleared := coalesce((old_word->>'mistakeCleared')::boolean,false);
      baseline_word := baseline_word_map->(chosen->>'id');
      streak := greatest(0,coalesce((baseline_word->>'consecutiveCorrect')::integer,0));
      cleared := coalesce((baseline_word->>'mistakeCleared')::boolean,false);
      -- Recompute chronological state: a late offline incorrect answer between
      -- two correct answers must break the streak, regardless of arrival order.
      for e in select payload from public.vocab_learning_events
        where user_id=p_user_id and epoch=p_epoch and accounted_as='answer'
        and word_id=chosen->>'id' order by occurred_at,event_id loop
        if e->>'id'=any(added_ids) then
          if e->>'result'='correct' then count_correct:=count_correct+1; else count_incorrect:=count_incorrect+1; end if;
        end if;
        if e->>'result'='incorrect' then streak:=0; cleared:=false;
        else streak:=streak+1; if count_incorrect>0 and streak>=2 then cleared:=true; end if; end if;
        if jsonb_typeof(e->'wordState')='object' then
          chosen := chosen || jsonb_strip_nulls(jsonb_build_object(
            'readingIntroducedAt',e->'wordState'->'readingIntroducedAt',
            'readingMasteredAt',e->'wordState'->'readingMasteredAt',
            'readingNextDueAt',e->'wordState'->'readingNextDueAt',
            'readingReviewStage',e->'wordState'->'readingReviewStage'));
        end if;
        chosen := chosen || jsonb_build_object('vocabMasterProgressUpdatedAt',e->>'at');
      end loop;
    end if;
    chosen := chosen || jsonb_build_object('correctCount',count_correct,'incorrectCount',count_incorrect,
      'consecutiveCorrect',streak,'mistakeCleared',cleared);
    prior_word:=old_word; projected_word:=chosen; return next;
  end loop;
end $$;
revoke all on function private.vocab_project_words_v3(uuid,uuid,jsonb,jsonb,jsonb,text[],jsonb,boolean) from public,anon,authenticated,service_role;
-- Preserve journal validation, counters, chronology, archives and permissions.
create or replace function public.vocab_guard_snapshot_v3()
returns trigger language plpgsql security definer set search_path = pg_catalog, public as $$
declare
  meta public.vocab_sync_metadata%rowtype;
  old_master jsonb := '{}'::jsonb; incoming jsonb; old_p jsonb; new_p jsonb; merged_p jsonb;
  override_master jsonb; override_reason text; is_baseline boolean := false;
  e jsonb; existing_event jsonb; event_time timestamptz; inserted integer;
  old_words jsonb; merged_words jsonb; word_buffer jsonb[] := '{}'::jsonb[]; merged_word_map jsonb; baseline_word_map jsonb; old_word jsonb; new_word jsonb; chosen jsonb;
  merged_events jsonb; reward jsonb; ignored jsonb; added_ids text[] := '{}'::text[];
  count_correct integer; count_incorrect integer; streak integer; cleared boolean;
  baseline_word jsonb; baseline_profile jsonb; latest_answer jsonb;
  latest_at text; changed_old_words jsonb; archive_full boolean;
begin
  -- An UPSERT executes INSERT triggers before conflict resolution. Defer all
  -- journal effects to its UPDATE trigger when the learner row already exists.
  if tg_op='INSERT' and exists(select 1 from public.reader_sync_state where user_id=new.user_id) then return new; end if;
  if tg_op = 'UPDATE' then old_master := coalesce(old.vocab_master_progress, '{}'::jsonb); end if;
  incoming := coalesce(new.vocab_master_progress, '{}'::jsonb);
  delete from public.vocab_admin_baseline_override where user_id=new.user_id
    returning master, reason into override_master, override_reason;
  if override_master is not null then incoming := override_master; is_baseline := true; end if;
  select * into meta from public.vocab_sync_metadata where user_id=new.user_id for update;
  if not found then
    insert into public.vocab_sync_metadata(user_id) values(new.user_id) returning * into meta;
    is_baseline := true;
    -- When upgrading an existing row, OLD is the trusted baseline. INSERTs
    -- start with their first supplied profile, whose history is a baseline.
    if tg_op='UPDATE' and override_master is null then incoming := old_master; end if;
  elsif override_master is not null then
    update public.vocab_sync_metadata set epoch=gen_random_uuid(), baseline_at=clock_timestamp()
      where user_id=new.user_id returning * into meta;
  end if;
  old_p := public.vocab_profile_v3(old_master,new.user_id);
  new_p := public.vocab_profile_v3(incoming,new.user_id);
  if is_baseline then
    update public.vocab_sync_metadata set baseline_master=incoming,
      baseline_at=coalesce((select max((value->>'at')::timestamptz)
        from jsonb_array_elements(coalesce(new_p->'studyEvents','[]'::jsonb))),case when new_p='{}'::jsonb then '-infinity'::timestamptz else clock_timestamp() end)
      where user_id=new.user_id returning * into meta;
    old_p := '{}'::jsonb;
  end if;
  baseline_profile := public.vocab_profile_v3(meta.baseline_master,new.user_id);


  -- Immutable IDs: replaying an ID with altered identity/result is rejected.
  -- New durable v3 answers are counted even with an older clock timestamp.
  -- Unmarked legacy events before the baseline are evidence only: existing
  -- aggregate counters may already include them, so they cannot be summed.
  for e in select value from jsonb_array_elements(coalesce(new_p->'studyEvents','[]'::jsonb)) loop
    if nullif(e->>'id','') is null or nullif(e->>'wordId','') is null or e->>'result' not in ('correct','incorrect')
       or nullif(e->>'at','') is null then
      raise exception 'Malformed study event' using errcode='22023';
    end if;
    event_time := (e->>'at')::timestamptz;
    if event_time > clock_timestamp() + interval '5 minutes' then
      raise exception 'Study event timestamp exceeds clock tolerance' using errcode='22023';
    end if;
    select payload into existing_event from public.vocab_learning_events where user_id=new.user_id and event_id=e->>'id';
    if found then
      if (existing_event->>'wordId',existing_event->>'at',existing_event->>'result') is distinct from
         (e->>'wordId',e->>'at',e->>'result') then
        raise exception 'Study event ID already identifies a different answer' using errcode='22023';
      end if;
    else
      insert into public.vocab_learning_events(user_id,event_id,epoch,word_id,occurred_at,result,payload,accounted_as)
        values(new.user_id,e->>'id',meta.epoch,e->>'wordId',event_time,e->>'result',e,
          case when is_baseline or (coalesce(e->>'durableVersion','')<>'3' and event_time <= meta.baseline_at)
            then 'baseline' else 'answer' end)
        on conflict(user_id,event_id) do nothing;
      get diagnostics inserted = row_count;
      if inserted=1 and not is_baseline and (e->>'durableVersion'='3' or event_time > meta.baseline_at) then
        added_ids := array_append(added_ids,e->>'id');
      end if;
    end if;
  end loop;

  merged_p := case when coalesce(old_p->>'updatedAt','') > coalesce(new_p->>'updatedAt','')
    then new_p || old_p else old_p || new_p end;
  select coalesce(jsonb_agg(distinct x),'[]'::jsonb) into ignored from (
    select value x from jsonb_array_elements(coalesce(old_p->'ignoredReadingWordIds','[]'::jsonb))
    union all select value from jsonb_array_elements(coalesce(new_p->'ignoredReadingWordIds','[]'::jsonb))
  ) t;
  old_words := coalesce(old_p->'words','[]'::jsonb);
  select coalesce(jsonb_agg(projected_word) filter(where projected_word is not null),'[]'::jsonb),
    coalesce(jsonb_agg(prior_word) filter(where prior_word is not null and prior_word is distinct from projected_word),'[]'::jsonb)
  into merged_words,changed_old_words
  from private.vocab_project_words_v3(new.user_id,meta.epoch,old_p,new_p,baseline_profile,added_ids,ignored,is_baseline);
  -- An answer without its word cannot be projected safely.
  if exists(select 1 from public.vocab_learning_events e where e.user_id=new.user_id and e.event_id=any(added_ids)
    and not exists(select 1 from jsonb_array_elements(merged_words) w where w->>'id'=e.word_id)
    and not ignored ? e.word_id) then raise exception 'Answer references missing word' using errcode='22023'; end if;
  select coalesce(jsonb_agg(payload order by occurred_at,event_id),'[]'::jsonb) into merged_events
    from public.vocab_learning_events where user_id=new.user_id;
  -- Aggregate once: repeated JSONB concatenation copies the growing ledger per event.
  select coalesce(old_p->'rewardLedger','{}'::jsonb) ||
    coalesce(jsonb_object_agg(entries.e->>'id',(entries.e->>'rewardPoints')::integer
      order by position) filter (where coalesce((entries.e->>'rewardPoints')::integer,0) between 1 and 15),'{}'::jsonb)
    into reward
    from jsonb_array_elements(merged_events) with ordinality entries(e,position);
  if is_baseline then reward := reward || coalesce(new_p->'rewardLedger','{}'::jsonb); end if;
  merged_p := merged_p || jsonb_build_object('id','reader_'||new.user_id,'words',merged_words,
    'studyEvents',merged_events,'rewardLedger',reward,'ignoredReadingWordIds',ignored);
  incoming := incoming || jsonb_build_object('version',3,'appState',
    coalesce(incoming->'appState',old_master->'appState','{}'::jsonb) || jsonb_build_object('version',1,
      'currentUserId','reader_'||new.user_id,'users',jsonb_build_object('reader_'||new.user_id,merged_p)));
  -- Reading convenience projection is derived from the same authoritative words.
  incoming := incoming || jsonb_build_object('words',coalesce((select jsonb_object_agg(lower(w->>'english_word'),
    jsonb_build_object('correctCount',w->'correctCount','incorrectCount',w->'incorrectCount',
      'consecutiveCorrect',w->'consecutiveCorrect','mistakeCleared',w->'mistakeCleared',
      'flashcardKnown',coalesce(w->'flashcardKnown','false'::jsonb),
      'updatedAt',coalesce(w->'vocabMasterProgressUpdatedAt','""'::jsonb),
      'readingIntroducedAt',coalesce(w->'readingIntroducedAt','""'::jsonb),
      'readingNextDueAt',coalesce(w->'readingNextDueAt','""'::jsonb),
      'readingMasteredAt',coalesce(w->'readingMasteredAt','""'::jsonb),
      'readingReviewStage',coalesce(w->'readingReviewStage','0'::jsonb)))
    from jsonb_array_elements(merged_words) w where w->>'source'='reading'),'{}'::jsonb));
  if (incoming-'_sync') is distinct from (old_master-'_sync') or is_baseline then
    -- One daily full baseline; intermediate deltas contain the replaced old
    -- words, old profile metadata, event IDs and reward ledger for reconstruction.
    archive_full := not exists(select 1 from public.vocab_snapshot_archive where user_id=new.user_id
      and full_master is not null and (archived_at at time zone 'UTC')::date=(clock_timestamp() at time zone 'UTC')::date);
    insert into public.vocab_snapshot_archive(user_id,revision,epoch,full_master,delta,reason)
      values(new.user_id,meta.revision,coalesce((old_master#>>'{_sync,epoch}')::uuid,meta.epoch),case when archive_full or override_master is not null then old_master end,
        case when not archive_full and override_master is null then jsonb_build_object(
          'previousTopLevel',old_master-'appState'-'words',
          'previousAppMetadata',coalesce(old_master->'appState','{}'::jsonb)-'users',
          'previousProfileMetadata',old_p-'words'-'studyEvents'-'rewardLedger',
          'previousWords',changed_old_words,
          'previousWordIds',coalesce((select jsonb_agg(w->'id') from jsonb_array_elements(old_words) w),'[]'::jsonb),
          'previousEventIds',coalesce((select jsonb_agg(prior_event->'id') from jsonb_array_elements(coalesce(old_p->'studyEvents','[]'::jsonb)) prior_event),'[]'::jsonb),
          'previousRewardLedger',old_p->'rewardLedger') end,
        coalesce(override_reason,case when is_baseline then 'verified baseline seed' else 'atomic learning sync' end))
      on conflict(user_id,revision) do nothing;
    update public.vocab_sync_metadata set revision=revision+1 where user_id=new.user_id returning * into meta;
  end if;
  incoming := incoming || jsonb_build_object('_sync',jsonb_build_object('epoch',meta.epoch,'revision',meta.revision,'baselineAt',meta.baseline_at));
  new.vocab_master_progress := incoming;
  return new;
end $$;


create or replace function public.sync_vocab_master_v3(p_master jsonb,p_mutation_id uuid,p_expected_epoch uuid default null)
returns jsonb language plpgsql security invoker set search_path=pg_catalog,public as $$
declare uid uuid:=auth.uid(); row_master jsonb; meta public.vocab_sync_metadata%rowtype; ack jsonb; incoming_profile jsonb; canonical_profile jsonb; already_covered boolean:=false;
begin
  if uid is null then raise exception 'Authentication required' using errcode='42501'; end if;
  if p_mutation_id is null or jsonb_typeof(p_master) is distinct from 'object' then
    raise exception 'Mutation ID and master object required' using errcode='22023'; end if;
  -- Serialize first-time initialization as well as updates. The empty seed
  -- trusts no imported counters; genuine incoming events establish progress.
  perform pg_advisory_xact_lock(hashtextextended(uid::text,0));
  if not exists(select 1 from public.reader_sync_state where user_id=uid) then
    insert into public.reader_sync_state(user_id,vocab_master_progress)
      values(uid,'{"appState":{"users":{}}}'::jsonb) on conflict(user_id) do nothing;
  end if;
  select vocab_master_progress into row_master from public.reader_sync_state where user_id=uid for update;
  if not exists(select 1 from public.vocab_sync_metadata where user_id=uid) then
    -- Readmaster may have created the shared row without a vocabulary profile.
    -- Seed only OLD, then accept this RPC's genuine events in a separate update.
    update public.reader_sync_state set vocab_master_progress=vocab_master_progress where user_id=uid
      returning vocab_master_progress into row_master;
  end if;
  select * into meta from public.vocab_sync_metadata where user_id=uid;
  if p_expected_epoch is not null and p_expected_epoch is distinct from meta.epoch then
    raise exception 'Learning baseline changed; reload before syncing' using errcode='P0001',detail='VMEPOCH'; end if;
  -- Empty users is the authenticated, read-only canonical refresh protocol.
  if coalesce(p_master->'appState'->'users','{}'::jsonb)='{}'::jsonb then
    return jsonb_build_object('master',row_master,'revision',meta.revision,'epoch',meta.epoch,'acknowledgedEventIds','[]'::jsonb);
  end if;
  -- A stale client can omit cloud words/history without requesting their deletion.
  -- Return the complete canonical profile when every submitted word and event is
  -- byte-for-byte JSONB equal to an existing entry and all writable metadata agrees.
  if (p_master-'_sync') is distinct from (row_master-'_sync') then
    incoming_profile:=public.vocab_profile_v3(p_master,uid);
    canonical_profile:=public.vocab_profile_v3(row_master,uid);
    already_covered:=
      (p_master-'_sync'-'words'-'appState')=(row_master-'_sync'-'words'-'appState')
      and ((p_master->'appState')-'users')=((row_master->'appState')-'users')
      and (incoming_profile-'words'-'studyEvents')=(canonical_profile-'words'-'studyEvents')
      and coalesce(row_master->'words','{}'::jsonb) @> coalesce(p_master->'words','{}'::jsonb)
      and not exists ((select value from jsonb_array_elements(incoming_profile->'words'))
        except (select value from jsonb_array_elements(canonical_profile->'words')))
      and not exists ((select value from jsonb_array_elements(coalesce(incoming_profile->'studyEvents','[]'::jsonb)))
        except (select value from jsonb_array_elements(coalesce(canonical_profile->'studyEvents','[]'::jsonb))));
    if not coalesce(already_covered,false) then
      update public.reader_sync_state set vocab_master_progress=p_master,updated_at=clock_timestamp() where user_id=uid
        returning vocab_master_progress into row_master;
    end if;
  end if;
  select * into meta from public.vocab_sync_metadata where user_id=uid;
  select coalesce(jsonb_agg(e->'id'),'[]'::jsonb) into ack
    from jsonb_array_elements(coalesce(public.vocab_profile_v3(p_master,uid)->'studyEvents','[]'::jsonb)) e
    where exists(select 1 from public.vocab_learning_events j where j.user_id=uid and j.event_id=e->>'id');
  return jsonb_build_object('master',row_master,'revision',meta.revision,'epoch',meta.epoch,'acknowledgedEventIds',ack);
end $$;

