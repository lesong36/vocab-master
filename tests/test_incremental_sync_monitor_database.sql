-- Apply db/p0_incremental_sync.sql and db/p0_incremental_sync_monitor.sql first.
begin;
insert into auth.users(id,email,raw_user_meta_data) values('77777777-7777-4777-8777-777777777777','delta-monitor@example.invalid','{"username":"delta_monitor_777"}');
set local role authenticated;
select set_config('request.jwt.claim.sub','77777777-7777-4777-8777-777777777777',true);
do $test$
declare receipt jsonb; profile_key text:='reader_77777777-7777-4777-8777-777777777777';
begin
 receipt:=public.sync_vocab_master_v3(jsonb_build_object('version',3,'appState',jsonb_build_object('users',
  jsonb_build_object(profile_key,jsonb_build_object('words',jsonb_build_array(jsonb_build_object('id','monitor-word','english_word','monitor'),jsonb_build_object('id','ignored-word','english_word','ignored')),
  'ignoredReadingWordIds',jsonb_build_array('ignored-word'),
  'studyEvents',jsonb_build_array(
   jsonb_build_object('id','v3-correct-a','wordId','monitor-word','at',clock_timestamp()-interval '3 hours','result','correct','durableVersion',3),
   jsonb_build_object('id','v3-correct-b','wordId','monitor-word','at',clock_timestamp()-interval '2 hours','result','correct','durableVersion',3),
   jsonb_build_object('id','v3-ignored-answer','wordId','ignored-word','at',clock_timestamp()-interval '2 hours','result','correct','durableVersion',3)
  ))))),gen_random_uuid(),null);
 receipt:=public.read_vocab_delta_v4();
 if (receipt->'words'->0->>'correctCount')::int<>2 then raise exception 'V3 baseline fixture did not preserve two corrects'; end if;
 receipt:=public.sync_vocab_delta_v4(jsonb_build_object('events',jsonb_build_array(jsonb_build_object(
  'id','monitor-event','wordId','monitor-word','at',clock_timestamp()-interval '4 hours','result','incorrect','rewardPoints',0))),
  gen_random_uuid(),(receipt->>'epoch')::uuid,(receipt->>'revision')::bigint);
 if (receipt->'words'->0->>'correctCount')::int<>2 or (receipt->'words'->0->>'incorrectCount')::int<>1 then
  raise exception 'Late answer counters incorrect'; end if;
end $test$;
reset role;
do $test$
declare uid uuid:='77777777-7777-4777-8777-777777777777';
begin
 if not exists(select 1 from private.vocab_delta_words where user_id=uid and word_id='ignored-word' and deleted) then raise exception 'Missing migrated ignored placeholder'; end if;
 perform private.refresh_vocab_sync_alerts(uid);
 if exists(select 1 from private.vocab_sync_incidents where user_id=uid and scope='ledger' and resolved_at is null) then raise exception 'Healthy v4 caused stale v3 snapshot alarm'; end if;
 begin
  delete from private.vocab_delta_event_refs where user_id=uid;
  perform private.refresh_vocab_sync_alerts(uid);
  if not exists(select 1 from private.vocab_sync_incidents where user_id=uid and scope='ledger' and resolved_at is null) then raise exception 'Missing ref undetected'; end if;
  raise no_data_found;
 exception when no_data_found then null; end;
 begin
  update public.vocab_learning_events set payload=payload||'{"rewardPoints":15}'::jsonb where user_id=uid and event_id='v3-ignored-answer';
  perform private.refresh_vocab_sync_alerts(uid);
  if not exists(select 1 from private.vocab_sync_incidents where user_id=uid and scope='ledger' and resolved_at is null) then raise exception 'Payload corruption undetected'; end if;
  raise no_data_found;
 exception when no_data_found then null; end;
 begin
  delete from private.vocab_delta_events where user_id=uid;
  delete from public.vocab_learning_events where user_id=uid;
  perform private.refresh_vocab_sync_alerts(uid);
  if not exists(select 1 from private.vocab_sync_incidents where user_id=uid and scope='ledger' and resolved_at is null) then raise exception 'Missing journal undetected'; end if;
  raise no_data_found;
 exception when no_data_found then null; end;
 begin
  delete from private.vocab_delta_words where user_id=uid;
  perform private.refresh_vocab_sync_alerts(uid);
  if not exists(select 1 from private.vocab_sync_incidents where user_id=uid and scope='ledger' and resolved_at is null) then raise exception 'Missing word undetected'; end if;
  raise no_data_found;
 exception when no_data_found then null; end;
 begin
  update private.vocab_delta_words set payload=payload||'{"correctCount":999}'::jsonb where user_id=uid;
  perform private.refresh_vocab_sync_alerts(uid);
  if not exists(select 1 from private.vocab_sync_incidents where user_id=uid and scope='ledger' and resolved_at is null) then raise exception 'Wrong projection undetected'; end if;
  raise no_data_found;
 exception when no_data_found then null; end;
end $test$;
select 'PASS: healthy v4 ignores stale snapshot; missing ref/journal/word, changed payload, wrong counters detected' result;
rollback;
