-- Run with psql -v ON_ERROR_STOP=1 as postgres after db/p0_learning_sync.sql.
-- All fixture writes are rolled back. No real learner row is changed.
begin;
insert into auth.users(id,email) values('11111111-1111-4111-8111-111111111111','p0-test@example.invalid'),
 ('22222222-2222-4222-8222-222222222222','p0-other@example.invalid');
insert into public.reader_sync_state(user_id,vocab_master_progress) values
 ('11111111-1111-4111-8111-111111111111',jsonb_build_object('version',3,'appState',jsonb_build_object('version',1,
 'currentUserId','reader_11111111-1111-4111-8111-111111111111','users',jsonb_build_object(
 'reader_11111111-1111-4111-8111-111111111111',jsonb_build_object('id','reader_11111111-1111-4111-8111-111111111111',
 'updatedAt',clock_timestamp(),'selectedSections','[]'::jsonb,'words',jsonb_build_array(jsonb_build_object('id','w1',
 'english_word','apple','section','三上 Unit1','correctCount',3,'incorrectCount',2,'consecutiveCorrect',0,'mistakeCleared',false)),
 'studyEvents',jsonb_build_array(jsonb_build_object('id','seed','wordId','w1','at',clock_timestamp()-interval '1 day','result','incorrect')))))));
set local role authenticated;
select set_config('request.jwt.claim.sub','11111111-1111-4111-8111-111111111111',true);
do $$
declare r jsonb; master jsonb; e jsonb; ep uuid; rev bigint; t timestamptz:=clock_timestamp();
begin
  select vocab_master_progress into master from public.reader_sync_state;
  select epoch,revision into ep,rev from public.vocab_sync_metadata;
  if (master#>>'{appState,users,reader_11111111-1111-4111-8111-111111111111,words,0,incorrectCount}')::int<>2 then
    raise exception 'Baseline event was counted twice'; end if;
  -- Structured cursor is valid jsonb; the historical NUL cursor is rejected by PostgreSQL.
  begin
    perform '{"readingQueueCursor":"date\u0000word"}'::jsonb;
    raise exception 'PostgreSQL unexpectedly accepted NUL';
  exception when sqlstate '22P05' then null; end;
  perform '{"readingQueueCursor":{"importedAt":"date","wordId":"word"}}'::jsonb;
  -- Read-only refresh must leave revision and archived rows unchanged.
  r:=public.sync_vocab_master_v3('{"appState":{"users":{}}}'::jsonb,gen_random_uuid(),null);
  if (r->>'revision')::bigint<>rev then raise exception 'Read changed revision'; end if;
  -- A new answer increments baseline once, despite untrusted client count 99.
  master:=jsonb_set(master,'{appState,users,reader_11111111-1111-4111-8111-111111111111,words,0,correctCount}','99');
  e:=jsonb_build_object('id','new-correct','wordId','w1','at',t,'result','correct','rewardPoints',10);
  master:=jsonb_set(master,'{appState,users,reader_11111111-1111-4111-8111-111111111111,studyEvents}',jsonb_build_array(e));
  r:=public.sync_vocab_master_v3(master,gen_random_uuid(),ep);
  if (r#>>'{master,appState,users,reader_11111111-1111-4111-8111-111111111111,words,0,correctCount}')::int<>4 then
    raise exception 'Snapshot count trusted or answer not counted'; end if;
  r:=public.sync_vocab_master_v3(master,gen_random_uuid(),ep);
  if (r#>>'{master,appState,users,reader_11111111-1111-4111-8111-111111111111,words,0,correctCount}')::int<>4 then
    raise exception 'Repeated event counted twice'; end if;
  if jsonb_array_length(r#>'{master,appState,users,reader_11111111-1111-4111-8111-111111111111,studyEvents}')<>2 then
    raise exception 'Missing old event was deleted'; end if;
  -- Existing ID with another result cannot mutate the journal.
  begin
    perform public.sync_vocab_master_v3(jsonb_set(master,
      '{appState,users,reader_11111111-1111-4111-8111-111111111111,studyEvents,0,result}','"incorrect"'),gen_random_uuid(),ep);
    raise exception 'Altered duplicate accepted';
  exception when sqlstate '22023' then null; end;
  -- Legacy direct write cannot reduce counters or discard event history.
  master:=jsonb_set(master,'{appState,users,reader_11111111-1111-4111-8111-111111111111,words,0,correctCount}','0');
  master:=jsonb_set(master,'{appState,users,reader_11111111-1111-4111-8111-111111111111,studyEvents}','[]');
  update public.reader_sync_state set vocab_master_progress=master;
  select vocab_master_progress into r from public.reader_sync_state;
  if (r#>>'{appState,users,reader_11111111-1111-4111-8111-111111111111,words,0,correctCount}')::int<>4 then
    raise exception 'Legacy counter regression'; end if;
  -- Legacy UPSERT must count its fresh event exactly once, after conflict resolution.
  master:=jsonb_set(master,'{appState,users,reader_11111111-1111-4111-8111-111111111111,studyEvents}',
    jsonb_build_array(jsonb_build_object('id','upsert-correct','wordId','w1','at',t-interval '1 second','result','correct')));
  insert into public.reader_sync_state(user_id,vocab_master_progress) values
    ('11111111-1111-4111-8111-111111111111',master)
    on conflict(user_id) do update set vocab_master_progress=excluded.vocab_master_progress;
  if (select (vocab_master_progress#>>'{appState,users,reader_11111111-1111-4111-8111-111111111111,words,0,correctCount}')::int
      from public.reader_sync_state)<>5 then raise exception 'Legacy UPSERT lost or duplicated fresh answer'; end if;
  -- Two chronological correct answers with an offline mistake between them:
  -- late arrival must break the streak.
  master:=jsonb_set(master,'{appState,users,reader_11111111-1111-4111-8111-111111111111,studyEvents}',
    jsonb_build_array(jsonb_build_object('id','later-correct','wordId','w1','at',t+interval '2 seconds','result','correct')));
  perform public.sync_vocab_master_v3(master,gen_random_uuid(),ep);
  master:=jsonb_set(master,'{appState,users,reader_11111111-1111-4111-8111-111111111111,studyEvents}',
    jsonb_build_array(jsonb_build_object('id','offline-mistake','wordId','w1','at',t+interval '1 second','result','incorrect')));
  r:=public.sync_vocab_master_v3(master,gen_random_uuid(),ep);
  if (r#>>'{master,appState,users,reader_11111111-1111-4111-8111-111111111111,words,0,consecutiveCorrect}')::int<>1 or
    (r#>>'{master,appState,users,reader_11111111-1111-4111-8111-111111111111,words,0,mistakeCleared}')::boolean then
    raise exception 'Offline chronology did not break streak'; end if;
  -- Omitted word snapshots cannot remove existing words, even with empty events.
  master:=jsonb_set(master,'{appState,users,reader_11111111-1111-4111-8111-111111111111,words}','[]');
  master:=jsonb_set(master,'{appState,users,reader_11111111-1111-4111-8111-111111111111,studyEvents}','[]');
  r:=public.sync_vocab_master_v3(master,gen_random_uuid(),ep);
  if jsonb_array_length(r#>'{master,appState,users,reader_11111111-1111-4111-8111-111111111111,words}')<>1 then
    raise exception 'Omitted words were lost'; end if;
  -- An explicitly new durable v3 answer survives an offline/older clock date.
  master:=r->'master';
  master:=jsonb_set(master,'{appState,users,reader_11111111-1111-4111-8111-111111111111,studyEvents}',
    jsonb_build_array(jsonb_build_object('id','old-clock-new-answer','wordId','w1',
      'at',t-interval '2 days','result','incorrect','durableVersion',3)));
  r:=public.sync_vocab_master_v3(master,gen_random_uuid(),ep);
  if (r#>>'{master,appState,users,reader_11111111-1111-4111-8111-111111111111,words,0,incorrectCount}')::int<>4 then
    raise exception 'Durable older-clock answer acknowledged without counting'; end if;
  -- Wrong epoch, missing authentication and privileged table writes are denied.
  begin perform public.sync_vocab_master_v3(master,gen_random_uuid(),gen_random_uuid()); raise exception 'Epoch mismatch accepted';
    exception when sqlstate 'P0001' then if sqlerrm='Epoch mismatch accepted' then raise; end if; end;
  begin delete from public.vocab_learning_events; raise exception 'Journal deletion allowed';
    exception when insufficient_privilege then null; end;
  begin delete from public.vocab_snapshot_archive; raise exception 'Archive deletion allowed';
    exception when insufficient_privilege then null; end;
  perform set_config('request.jwt.claim.sub','22222222-2222-4222-8222-222222222222',true);
  if exists(select 1 from public.vocab_learning_events) or exists(select 1 from public.vocab_snapshot_archive) then
    raise exception 'Cross-account evidence leaked'; end if;
  r:=public.sync_vocab_master_v3('{"appState":{"users":{}}}'::jsonb,gen_random_uuid(),null);
  if jsonb_array_length(r#>'{master,appState,users,reader_22222222-2222-4222-8222-222222222222,words}')<>0 then
    raise exception 'New account inherited another learner progress'; end if;
  perform set_config('request.jwt.claim.sub','',true);
  begin perform public.sync_vocab_master_v3(master,gen_random_uuid(),null); raise exception 'Anonymous sync accepted';
    exception when insufficient_privilege then null; end;
end $$;
reset role;
-- Admin correction rotates epoch, archives complete pre-correction master,
-- keeps real events, and sets an audited new baseline without max-clamping.
do $$
declare r jsonb; old_epoch uuid; count_before integer;
begin
  select epoch into old_epoch from public.vocab_sync_metadata where user_id='11111111-1111-4111-8111-111111111111';
  select count(*) into count_before from public.vocab_learning_events where user_id='11111111-1111-4111-8111-111111111111';
  r:=private.vocab_admin_rebaseline('11111111-1111-4111-8111-111111111111',
    '{"w1":{"correctCount":0,"incorrectCount":0,"consecutiveCorrect":0,"mistakeCleared":false}}',
    'Remove verified invalid imported recovery counters');
  if (r->>'epoch')::uuid=old_epoch then raise exception 'Admin correction kept old epoch'; end if;
  if count_before<>(select count(*) from public.vocab_learning_events where user_id='11111111-1111-4111-8111-111111111111') then
    raise exception 'Admin correction deleted evidence'; end if;
  if (select (vocab_master_progress#>>'{appState,users,reader_11111111-1111-4111-8111-111111111111,words,0,incorrectCount}')::int
      from public.reader_sync_state where user_id='11111111-1111-4111-8111-111111111111')<>0 then
    raise exception 'Admin correction max-clamped old count'; end if;
  if not exists(select 1 from public.vocab_snapshot_archive where user_id='11111111-1111-4111-8111-111111111111'
    and reason='Remove verified invalid imported recovery counters' and full_master is not null) then
    raise exception 'Admin correction did not archive full original'; end if;
end $$;
set local role authenticated;
select set_config('request.jwt.claim.sub','11111111-1111-4111-8111-111111111111',true);
do $$
declare master jsonb; r jsonb; ep uuid;
begin
  select vocab_master_progress into master from public.reader_sync_state;
  select epoch into ep from public.vocab_sync_metadata;
  master:=jsonb_set(master,'{appState,users,reader_11111111-1111-4111-8111-111111111111,words,0,incorrectCount}','60');
  r:=public.sync_vocab_master_v3(master,gen_random_uuid(),ep);
  if (r#>>'{master,appState,users,reader_11111111-1111-4111-8111-111111111111,words,0,incorrectCount}')::int<>0 then
    raise exception 'Stale legacy counters resurrected after correction'; end if;
  begin perform public.restore_vocab_master_baseline_v3('11111111-1111-4111-8111-111111111111',master,'Unauthorized reset');
    raise exception 'Client rebaseline allowed'; exception when insufficient_privilege then null; end;
end $$;
reset role;
-- The shared row can be created by another application after deployment.
insert into auth.users(id,email) values('33333333-3333-4333-8333-333333333333','empty-row@example.invalid');
alter table public.reader_sync_state disable trigger vocab_guard_snapshot_v3;
insert into public.reader_sync_state(user_id,vocab_master_progress) values('33333333-3333-4333-8333-333333333333',null);
alter table public.reader_sync_state enable trigger vocab_guard_snapshot_v3;
set local role authenticated;
select set_config('request.jwt.claim.sub','33333333-3333-4333-8333-333333333333',true);
do $$
declare r jsonb;
begin
  r:=public.sync_vocab_master_v3(jsonb_build_object('appState',jsonb_build_object('users',jsonb_build_object('reader_fixture',
    jsonb_build_object('words',jsonb_build_array(jsonb_build_object('id','w','correctCount',60,'incorrectCount',60)),
      'studyEvents',jsonb_build_array(jsonb_build_object('id','first-answer','wordId','w','at',clock_timestamp(),
        'result','correct','durableVersion',3)))))),gen_random_uuid(),null);
  if (r#>>'{master,appState,users,reader_33333333-3333-4333-8333-333333333333,words,0,correctCount}')::int<>1 then
    raise exception 'Existing empty shared row dropped first answer or trusted snapshot'; end if;
end $$;
reset role;
-- Event journal and canonical history retain more than the old 5000-event cap.
insert into auth.users(id,email) values('44444444-4444-4444-8444-444444444444','large-history@example.invalid');
insert into public.reader_sync_state(user_id,vocab_master_progress)
select '44444444-4444-4444-8444-444444444444',jsonb_build_object('appState',jsonb_build_object('users',jsonb_build_object(
 'reader_fixture',jsonb_build_object('words',jsonb_build_array(jsonb_build_object('id','w','correctCount',17)),
 'studyEvents',(select jsonb_agg(jsonb_build_object('id','large-'||n,'wordId','w','result','correct',
   'at',clock_timestamp()-interval '1 day'+n*interval '1 microsecond')) from generate_series(1,5001) n)))));
do $$
begin
  if (select count(*) from public.vocab_learning_events where user_id='44444444-4444-4444-8444-444444444444')<>5001 or
     (select jsonb_array_length(vocab_master_progress#>'{appState,users,reader_44444444-4444-4444-8444-444444444444,studyEvents}')
      from public.reader_sync_state where user_id='44444444-4444-4444-8444-444444444444')<>5001 then
    raise exception 'History was silently truncated'; end if;
end $$;
rollback;
