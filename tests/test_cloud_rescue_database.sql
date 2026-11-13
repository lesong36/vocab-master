-- Production-safe synthetic test: every fixture write is rolled back.
begin;
insert into auth.users(id,email,raw_user_meta_data) values('55555555-5555-4555-8555-555555555555','cloud-rescue-test@example.invalid','{"username":"cloud_rescue_test_555"}'::jsonb);
set local role authenticated;
select set_config('request.jwt.claim.sub','55555555-5555-4555-8555-555555555555',true);
do $$
declare initial jsonb; first_receipt jsonb; retry_receipt jsonb; master jsonb; ep uuid;
begin
 initial:=public.sync_vocab_master_v3('{"version":3,"appState":{"users":{}}}'::jsonb,gen_random_uuid(),null);
 ep:=(initial->>'epoch')::uuid;
 master:=jsonb_build_object('version',3,'appState',jsonb_build_object('version',1,'currentUserId','reader_55555555-5555-4555-8555-555555555555','users',jsonb_build_object('reader_55555555-5555-4555-8555-555555555555',jsonb_build_object(
 'id','reader_55555555-5555-4555-8555-555555555555','words',jsonb_build_array(jsonb_build_object('id','plastic','english_word','plastic','correctCount',1,'incorrectCount',0)),
 'studyEvents',jsonb_build_array(jsonb_build_object('id','aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa','wordId','plastic','at',clock_timestamp(),'result','correct','durableVersion',3,'rewardPoints',10,'wordDefinition',jsonb_build_object('id','plastic','english_word','plastic','section','阅读生词本')))
 ))));
 first_receipt:=public.sync_vocab_master_v3(master,'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',ep);
 retry_receipt:=public.sync_vocab_master_v3(master,'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',ep);
 if not coalesce(first_receipt->'acknowledgedEventIds' ? 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',false) or not coalesce(retry_receipt->'acknowledgedEventIds' ? 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',false) then raise exception 'Missing durable receipt'; end if;
 if (select count(*) from public.vocab_learning_events where user_id=auth.uid() and event_id='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa')<>1 then raise exception 'Event replay duplicated'; end if;
 if (retry_receipt#>>'{master,appState,users,reader_55555555-5555-4555-8555-555555555555,words,0,correctCount}')::int is distinct from 1 then raise exception 'Answer counted twice'; end if;
 if (retry_receipt#>>'{master,appState,users,reader_55555555-5555-4555-8555-555555555555,rewardLedger,aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa}')::int is distinct from 10 then raise exception 'Reward was not exactly 10'; end if;
end $$;
reset role;
select 'PASS: authenticated cloud receipt, immutable event deduplication, one correct answer, exactly 10 points' as result;
rollback;
