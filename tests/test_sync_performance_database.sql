-- Run once before and once after the migration in a transaction; every write rolls back.
begin;
set local statement_timeout='55s';
do $$
declare uid uuid; m jsonb; r jsonb; t timestamptz; submitted jsonb; profile_key text; event_id text; target_word jsonb; timings jsonb:='{}';
begin
 select user_id,vocab_master_progress into uid,m from public.reader_sync_state
 order by octet_length(vocab_master_progress::text) desc limit 1;
 if uid is null then raise exception 'No benchmark profile'; end if;
 perform set_config('request.jwt.claim.sub',uid::text,true);
 -- Each subtransaction rolls back its writes; PL/pgSQL variables retain the receipt.
 profile_key:='reader_'||uid;
 select value into target_word from jsonb_array_elements(m#>array['appState','users',profile_key,'words']) w
 where not coalesce(m#>array['appState','users',profile_key,'ignoredReadingWordIds'],'[]'::jsonb) ? (w->>'id') limit 1;
 for n in 1..3 loop
  submitted:=case when n=1 then m else jsonb_set(m,'{appState,savedAt}',to_jsonb('benchmark-only'::text)) end;
  if n=3 then
   event_id:=gen_random_uuid()::text;
   submitted:=jsonb_set(m,array['appState','users',profile_key,'studyEvents'],
     (m#>array['appState','users',profile_key,'studyEvents'])||jsonb_build_array(jsonb_build_object(
       'id',event_id,'wordId',target_word->>'id','at',clock_timestamp(),'result','correct','durableVersion',3,'rewardPoints',10)));
  end if;
  t:=clock_timestamp();
  begin
   r:=public.sync_vocab_master_v3(submitted,gen_random_uuid(),null);
   raise no_data_found;
  exception when no_data_found then null; end;
  timings:=timings||jsonb_build_object(case when n=1 then 'canonical_retry_ms' when n=2 then 'metadata_write_ms' else 'new_answer_ms' end,round(extract(epoch from clock_timestamp()-t)*1000));
  if clock_timestamp()-t > interval '8 seconds' then raise exception 'Sync exceeded production 8-second budget'; end if;
  if r->'master' is null then raise exception 'Missing master'; end if;
  if (select count(*) from jsonb_array_elements(r->'acknowledgedEventIds')) <>
     (select count(*) from jsonb_each(m#>'{appState,users}') u,jsonb_array_elements(u.value->'studyEvents')) + (case when n=3 then 1 else 0 end) then
    raise exception 'Missing event acknowledgements'; end if;
  if n=3 and (not (r->'acknowledgedEventIds' ? event_id) or
    (r#>>array['master','appState','users',profile_key,'rewardLedger',event_id])::int is distinct from 10) then
   raise exception 'New answer receipt or reward missing'; end if;
 end loop;
 perform set_config('p0.performance',timings::text,true);
end $$;
select current_setting('p0.performance')::jsonb benchmark;
rollback;
