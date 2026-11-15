-- Production-sized stale-profile retry; all writes are rolled back.
begin;
set local statement_timeout='8s';
do $$
declare uid uuid; canonical jsonb; submitted jsonb; result jsonb; profile_key text; started timestamptz;
begin
 select user_id,vocab_master_progress into uid,canonical from public.reader_sync_state
 order by octet_length(vocab_master_progress::text) desc limit 1;
 profile_key:='reader_'||uid;
 submitted:=jsonb_set(canonical,array['appState','users',profile_key,'words'],
  (select jsonb_agg(value order by n) from jsonb_array_elements(canonical#>array['appState','users',profile_key,'words']) with ordinality x(value,n) where n<=10));
 submitted:=jsonb_set(submitted,array['appState','users',profile_key,'studyEvents'],
  (select jsonb_agg(value order by n) from jsonb_array_elements(canonical#>array['appState','users',profile_key,'studyEvents']) with ordinality x(value,n) where n<=10));
 perform set_config('request.jwt.claim.sub',uid::text,true);
 execute 'set local role authenticated';
 started:=clock_timestamp();
 result:=public.sync_vocab_master_v3(submitted,gen_random_uuid(),null);
 if result->'master' is distinct from canonical then raise exception 'Covered retry dropped or rewrote canonical data'; end if;
 if jsonb_array_length(result->'acknowledgedEventIds')<>10 then raise exception 'Wrong receipt'; end if;
 perform set_config('p0.covered_retry_ms',(extract(epoch from clock_timestamp()-started)*1000)::text,true);
end $$;
select current_setting('p0.covered_retry_ms') covered_retry_ms;
rollback;
