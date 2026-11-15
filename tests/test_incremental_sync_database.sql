begin;
insert into auth.users(id,email,raw_user_meta_data) values('66666666-6666-4666-8666-666666666666','delta-v4@example.invalid','{"username":"delta_v4_666"}');
set local role authenticated;
select set_config('request.jwt.claim.sub','66666666-6666-4666-8666-666666666666',true);
do $$
declare b jsonb; r jsonb; ep uuid; rev bigint; changes jsonb; before_count integer;
begin
 b:=public.read_vocab_delta_v4(); ep:=(b->>'epoch')::uuid;
 changes:=jsonb_build_object('words',jsonb_build_array(jsonb_build_object('id','w','english_word','apple','correctCount',999)),
 'events',jsonb_build_array(jsonb_build_object('id','e1','wordId','w','at','2026-11-01T01:00:00Z','result','correct','rewardPoints',10)));
 r:=public.sync_vocab_delta_v4(changes,gen_random_uuid(),ep,0);
 if (r#>>'{words,0,correctCount}')::int<>1 or jsonb_array_length(r->'events')<>1 or not (r->'acknowledgedEventIds' ? 'e1') then raise exception 'Initial answer/counters/receipt wrong'; end if;
 rev:=(r->>'revision')::bigint;
 r:=public.sync_vocab_delta_v4(changes,gen_random_uuid(),ep,rev);
 if (r->>'revision')::bigint<>rev or jsonb_array_length(r->'events')<>0 then raise exception 'Retry repeated data'; end if;
 begin
 perform public.sync_vocab_delta_v4(jsonb_set(changes,'{events,0,result}','"incorrect"'),gen_random_uuid(),ep,rev);
 raise exception 'Forged event accepted'; exception when sqlstate '22023' then null; end;
 -- Late incorrect answer breaks an existing streak before a later correct event.
 changes:=jsonb_build_object('events',jsonb_build_array(jsonb_build_object('id','late','wordId','w','at','2026-11-01T00:00:00Z','result','incorrect','rewardPoints',0)));
 r:=public.sync_vocab_delta_v4(changes,gen_random_uuid(),ep,rev); rev:=(r->>'revision')::bigint;
 if (r#>>'{words,0,incorrectCount}')::int<>1 or (r#>>'{words,0,consecutiveCorrect}')::int<>1 then raise exception 'Late chronology broken'; end if;
 r:=public.read_vocab_delta_v4(rev,ep);
 if jsonb_array_length(r->'words')<>0 or jsonb_array_length(r->'events')<>0 then raise exception 'Empty poll returned growing history'; end if;
 r:=public.sync_vocab_delta_v4('{"tombstones":["w"]}',gen_random_uuid(),ep,rev);
 if not (r->'tombstones' ? 'w') then raise exception 'Tombstone absent'; end if;
 begin perform public.sync_vocab_delta_v4('{}',gen_random_uuid(),ep,0); raise exception 'Stale revision accepted'; exception when sqlstate 'P0001' then if sqlerrm='Stale revision accepted' then raise; end if; end;
 rev:=(r->>'revision')::bigint;
 r:=public.sync_vocab_delta_v4('{"tombstones":["never-imported"]}',gen_random_uuid(),ep,rev); rev:=(r->>'revision')::bigint;
 if not (r->'tombstones' ? 'never-imported') then raise exception 'Unknown tombstone not persisted'; end if;
 r:=public.sync_vocab_delta_v4('{"words":[{"id":"never-imported","english_word":"resurrect","correctCount":999}]}',gen_random_uuid(),ep,rev);
 if jsonb_array_length(r->'words')<>0 or (r->>'revision')::bigint<>rev then raise exception 'Tombstoned unknown word resurrected'; end if;
 begin
 perform public.sync_vocab_delta_v4('{"profile":{"rewardLedger":{"forged":999}}}',gen_random_uuid(),ep,rev);
 raise exception 'Reward patch accepted'; exception when sqlstate '22023' then null; end;
 begin
  perform public.sync_vocab_master_v3('{"appState":{"users":{}}}',gen_random_uuid(),null);
  raise exception 'Legacy RPC accepted'; exception when sqlstate '55000' then null; end;
 begin
  update public.reader_sync_state set vocab_master_progress=vocab_master_progress where user_id=auth.uid();
  raise exception 'Legacy direct write accepted'; exception when sqlstate '55000' then null; end;
 update public.reader_sync_state set updated_at=clock_timestamp() where user_id=auth.uid();
 r:=public.read_vocab_delta_v4();
 if jsonb_array_length(r->'words')<>0 or jsonb_array_length(r->'events')<>2 then raise exception 'Bootstrap lost history/deletion'; end if;
end $$;
reset role;
insert into auth.users(id,email,raw_user_meta_data) values('77777777-7777-4777-8777-777777777777','delta-migration@example.invalid','{"username":"delta_v4_777"}');
set local role authenticated;
select set_config('request.jwt.claim.sub','77777777-7777-4777-8777-777777777777',true);
do $$
declare m jsonb; r jsonb; ep uuid; rev bigint; events jsonb;
begin
 events:=jsonb_build_array(
 jsonb_build_object('id','old-a','wordId','w','at','2026-11-01T02:00:00Z','result','correct','durableVersion',3),
 jsonb_build_object('id','old-b','wordId','w','at','2026-11-01T04:00:00Z','result','correct','durableVersion',3));
 m:=jsonb_build_object('version',3,'appState',jsonb_build_object('users',jsonb_build_object('reader_77777777-7777-4777-8777-777777777777',jsonb_build_object('id','reader_77777777-7777-4777-8777-777777777777','words',jsonb_build_array(jsonb_build_object('id','w','english_word','apple')),'studyEvents',events,'ignoredReadingWordIds',jsonb_build_array('seed-ignored')))));
 r:=public.sync_vocab_master_v3(m,gen_random_uuid(),null);
 r:=public.read_vocab_delta_v4(); if not (r->'tombstones' ? 'seed-ignored') then raise exception 'Migrated ignored ID absent'; end if; ep:=(r->>'epoch')::uuid; rev:=(r->>'revision')::bigint;
 r:=public.sync_vocab_delta_v4(jsonb_build_object('events',jsonb_build_array(jsonb_build_object('id','late-before-migration','wordId','w','at','2026-11-01T03:00:00Z','result','incorrect'))),gen_random_uuid(),ep,rev);
 if (r#>>'{words,0,correctCount}')::int<>2 or (r#>>'{words,0,incorrectCount}')::int<>1 or (r#>>'{words,0,consecutiveCorrect}')::int<>1 then raise exception 'Pre-migration late answer chronology/counters broken'; end if;
 rev:=(r->>'revision')::bigint;
 r:=public.sync_vocab_delta_v4(jsonb_build_object('events',jsonb_build_array(jsonb_build_object('id','append-after-migration','wordId','w','at','2026-11-01T05:00:00Z','result','correct'))),gen_random_uuid(),ep,rev);
 if (r#>>'{words,0,correctCount}')::int<>3 or (r#>>'{words,0,consecutiveCorrect}')::int<>2 or not (r#>>'{words,0,mistakeCleared}')::boolean then raise exception 'Append after late correction broken'; end if;
end $$;
reset role;
insert into auth.users(id,email,raw_user_meta_data) values('99999999-9999-4999-8999-999999999999','delta-pages@example.invalid','{"username":"delta_v4_999"}');
set local role authenticated;
select set_config('request.jwt.claim.sub','99999999-9999-4999-8999-999999999999',true);
do $$
declare r jsonb; ep uuid; rev bigint:=0; cursor bigint:=0; received integer:=0; pages integer:=0; changes jsonb;
begin
 r:=public.read_vocab_delta_v4(); ep:=(r->>'epoch')::uuid;
 r:=public.sync_vocab_delta_v4('{"words":[{"id":"page-word"}]}',gen_random_uuid(),ep,0); rev:=(r->>'revision')::bigint;
 for n in 1..8 loop
 changes:=jsonb_build_object('events',jsonb_build_array(jsonb_build_object('id','page-'||n,'wordId','page-word','at','2026-11-01T00:00:00Z'::timestamptz+n*interval '1 second','result','correct')));
 r:=public.sync_vocab_delta_v4(changes,gen_random_uuid(),ep,rev); rev:=(r->>'revision')::bigint;
 end loop;
 loop
 r:=public.read_vocab_delta_v4(cursor,ep); pages:=pages+1;
 received:=received+jsonb_array_length(r->'events');
 if (r->>'revision')::bigint<=cursor then raise exception 'Cursor did not advance'; end if;
 cursor:=(r->>'revision')::bigint;
 exit when not (r->>'hasMore')::boolean;
 if pages>10 then raise exception 'Paging loop'; end if;
 end loop;
 if pages<>2 or received<>8 or cursor<>rev then raise exception 'Paged changes lost/duplicated'; end if;
 begin
 perform public.sync_vocab_delta_v4(jsonb_build_object('words',(select jsonb_agg(jsonb_build_object('id','oversize-'||n)) from generate_series(1,51)n)),gen_random_uuid(),ep,rev);
 raise exception '51 words accepted'; exception when sqlstate '22023' then null; end;
 begin
 perform public.sync_vocab_delta_v4(jsonb_build_object('profile',jsonb_build_object('huge',repeat('x',131073))),gen_random_uuid(),ep,rev);
 raise exception 'Oversize JSON accepted'; exception when sqlstate '22023' then null; end;
end $$;
reset role;
insert into auth.users(id,email,raw_user_meta_data) values('10101010-1010-4010-8010-101010101010','delta-old-evidence@example.invalid','{"username":"delta_v4_101"}');
update public.vocab_sync_metadata set baseline_at='2026-11-01T00:00:00Z' where user_id='10101010-1010-4010-8010-101010101010';
set local role authenticated;
select set_config('request.jwt.claim.sub','10101010-1010-4010-8010-101010101010',true);
do $$
declare r jsonb; ep uuid; rev bigint;
begin
 r:=public.read_vocab_delta_v4(); ep:=(r->>'epoch')::uuid;
 r:=public.sync_vocab_delta_v4('{"words":[{"id":"baseline-word"}]}',gen_random_uuid(),ep,0);rev:=(r->>'revision')::bigint;
 r:=public.sync_vocab_delta_v4('{"events":[{"id":"unmarked-old","wordId":"baseline-word","at":"2026-10-01T00:00:00Z","result":"correct","rewardPoints":10}]}',gen_random_uuid(),ep,rev);rev:=(r->>'revision')::bigint;
 if jsonb_array_length(r->'words')<>0 or not (r->'acknowledgedEventIds' ? 'unmarked-old') then raise exception 'Old baseline evidence projected as answer'; end if;
 if (select accounted_as from public.vocab_learning_events where user_id=auth.uid() and event_id='unmarked-old')<>'baseline' then raise exception 'Wrong evidence classification'; end if;
 r:=public.sync_vocab_delta_v4('{"events":[{"id":"durable-old","wordId":"baseline-word","at":"2026-10-01T00:00:01Z","result":"correct","durableVersion":3,"rewardPoints":10}]}',gen_random_uuid(),ep,rev);
 if (r#>>'{words,0,correctCount}')::int<>1 then raise exception 'Durable old-clock answer not counted exactly once'; end if;
end $$;
reset role;
-- Steady-state payload/latency with 10,000 already-confirmed answers.
insert into auth.users(id,email,raw_user_meta_data) values('88888888-8888-4888-8888-888888888888','delta-scale@example.invalid','{"username":"delta_v4_888"}');
select private.ensure_vocab_delta_v4('88888888-8888-4888-8888-888888888888');
insert into private.vocab_delta_words(user_id,word_id,payload,baseline,latest_at,latest_event_id)
values('88888888-8888-4888-8888-888888888888','scale-word','{"id":"scale-word","correctCount":10000,"incorrectCount":0,"consecutiveCorrect":10000}',
'{"id":"scale-word","correctCount":0,"incorrectCount":0,"consecutiveCorrect":0}', '2026-11-01T00:00:00Z','scale-10000');
insert into public.vocab_learning_events(user_id,event_id,epoch,word_id,occurred_at,result,payload,accounted_as)
select s.user_id,'scale-'||n,s.epoch,'scale-word','2026-10-31T00:00:00Z'::timestamptz+n*interval '1 second','correct',
jsonb_build_object('id','scale-'||n,'wordId','scale-word','at','2026-10-31T00:00:00Z'::timestamptz+n*interval '1 second','result','correct'),'answer'
from private.vocab_delta_state s cross join generate_series(1,10000)n where s.user_id='88888888-8888-4888-8888-888888888888';
set local role authenticated;
select set_config('request.jwt.claim.sub','88888888-8888-4888-8888-888888888888',true);
do $$
declare r jsonb; ep uuid; started timestamptz;
begin
 r:=public.read_vocab_delta_v4(0); ep:=(r->>'epoch')::uuid;
 started:=clock_timestamp();
 r:=public.sync_vocab_delta_v4('{"events":[{"id":"scale-new","wordId":"scale-word","at":"2026-11-02T00:00:00Z","result":"correct","rewardPoints":10}]}',gen_random_uuid(),ep,0);
 if jsonb_array_length(r->'events')<>1 or jsonb_array_length(r->'words')<>1 or (r#>>'{words,0,correctCount}')::int<>10001 or octet_length(r::text)>5000 then raise exception 'Steady-state delta grows with history'; end if;
 perform set_config('p0.delta_scale_ms',(extract(epoch from clock_timestamp()-started)*1000)::text,true);
end $$;
reset role;
select current_setting('p0.delta_scale_ms') scale_10000_answer_ms;
select current_setting('p0.delta_scale_ms') scale_10000_answer_ms, 'PASS: incremental answer, exact retry, forged ID, late chronology, empty poll, deletion, bootstrap history' result;
rollback;
