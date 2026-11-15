-- V4 normalized authoritative storage. Legacy snapshots are migration inputs only.
create table if not exists private.vocab_delta_state (
 user_id uuid primary key references auth.users(id), epoch uuid not null, revision bigint not null default 0,
 original_baseline_at timestamptz not null default '-infinity', profile jsonb not null, legacy_rewards jsonb not null default '{}'
);
create table if not exists private.vocab_delta_words (
 user_id uuid references auth.users(id), word_id text, payload jsonb not null, baseline jsonb not null,
 latest_at timestamptz, latest_event_id text, revision bigint not null default 0, deleted boolean not null default false, primary key(user_id,word_id)
);
create index if not exists vocab_delta_words_revision on private.vocab_delta_words(user_id,revision);
create table if not exists private.vocab_delta_events (
 user_id uuid, event_id text, word_id text not null, revision bigint not null,
 primary key(user_id,event_id), foreign key(user_id,event_id) references public.vocab_learning_events(user_id,event_id)
);
create index if not exists vocab_delta_events_revision on private.vocab_delta_events(user_id,revision);
create index if not exists vocab_delta_events_word on private.vocab_delta_events(user_id,word_id);
create table if not exists private.vocab_delta_event_refs (
 user_id uuid, event_id text, word_id text not null, payload_hash text not null, primary key(user_id,event_id)
);
alter table private.vocab_delta_event_refs enable row level security;
revoke all on private.vocab_delta_event_refs from public,anon,authenticated,service_role;
alter table private.vocab_delta_state enable row level security;
alter table private.vocab_delta_words enable row level security;
alter table private.vocab_delta_events enable row level security;
revoke all on private.vocab_delta_state,private.vocab_delta_words,private.vocab_delta_events from public,anon,authenticated,service_role;

create or replace function private.ensure_vocab_delta_v4(uid uuid) returns void
language plpgsql security definer set search_path=pg_catalog,public,private as $$
declare m jsonb; p jsonb; ep uuid; original_baseline jsonb; original_baseline_at timestamptz;
begin
 perform pg_advisory_xact_lock(hashtextextended(uid::text,0));
 if exists(select 1 from private.vocab_delta_state where user_id=uid) then return; end if;
 select vocab_master_progress into m from public.reader_sync_state where user_id=uid for update;
 p:=public.vocab_profile_v3(coalesce(m,'{}'),uid);
 select epoch,baseline_master,baseline_at into ep,original_baseline,original_baseline_at from public.vocab_sync_metadata where user_id=uid;
 original_baseline:=public.vocab_profile_v3(coalesce(original_baseline,'{}'),uid);
 insert into private.vocab_delta_state(user_id,epoch,original_baseline_at,profile,legacy_rewards)
 values(uid,coalesce(ep,gen_random_uuid()),coalesce(original_baseline_at,'-infinity'::timestamptz),(p-'words'-'studyEvents'-'rewardLedger')||jsonb_build_object('id','reader_'||uid),coalesce(p->'rewardLedger','{}'));
 insert into private.vocab_delta_event_refs(user_id,event_id,word_id,payload_hash)
 select uid,event_id,word_id,md5(payload::text) from public.vocab_learning_events where user_id=uid;
 insert into private.vocab_delta_words(user_id,word_id,payload,baseline,latest_at,latest_event_id)
 select uid,w->>'id',w,coalesce(b.value,'{}'::jsonb)||jsonb_build_object(
 'correctCount',coalesce((w->>'correctCount')::int,0)-stats.corrects,
 'incorrectCount',coalesce((w->>'incorrectCount')::int,0)-stats.incorrects),last_answer.occurred_at,last_answer.event_id
 from jsonb_array_elements(coalesce(p->'words','[]')) w
 left join jsonb_array_elements(coalesce(original_baseline->'words','[]')) b(value) on b.value->>'id'=w->>'id'
 cross join lateral (select count(*) filter(where result='correct')::int corrects,count(*) filter(where result='incorrect')::int incorrects
 from public.vocab_learning_events where user_id=uid and epoch=ep and word_id=w->>'id' and accounted_as='answer') stats
 left join lateral (select occurred_at,event_id from public.vocab_learning_events where user_id=uid and epoch=ep and word_id=w->>'id' and accounted_as='answer' order by occurred_at desc,event_id desc limit 1) last_answer on true;
 insert into private.vocab_delta_words(user_id,word_id,payload,baseline,deleted)
 select uid,ignored_id,jsonb_build_object('id',ignored_id),'{"correctCount":0,"incorrectCount":0,"consecutiveCorrect":0,"mistakeCleared":false}'::jsonb,true
 from jsonb_array_elements_text(coalesce(p->'ignoredReadingWordIds','[]')) ignored_id
 on conflict(user_id,word_id) do update set deleted=true;
end $$;
revoke all on function private.ensure_vocab_delta_v4(uuid) from public,anon,authenticated,service_role;

create or replace function private.vocab_delta_response_v4(uid uuid,after_rev bigint,acks jsonb default '[]') returns jsonb
language plpgsql security definer set search_path=pg_catalog,public,private as $$
declare s private.vocab_delta_state%rowtype; ws jsonb; es jsonb; ts jsonb; watermark bigint;
begin
 select * into strict s from private.vocab_delta_state where user_id=uid;
 if after_rev is null then watermark:=s.revision;
 else
 select coalesce(max(revision),s.revision) into watermark from (
  select distinct revision from (
   (select distinct revision from private.vocab_delta_words where user_id=uid and revision>after_rev order by revision limit 4)
   union all (select distinct revision from private.vocab_delta_events where user_id=uid and revision>after_rev order by revision limit 4)
   union all select s.revision where s.revision>after_rev
  ) changed order by revision limit 4
 ) page;
 end if;
 if after_rev is null then
 select coalesce(jsonb_agg(payload order by word_id) filter(where not deleted),'[]'),
 coalesce(jsonb_agg(word_id order by word_id) filter(where deleted),'[]') into ws,ts
 from private.vocab_delta_words where user_id=uid;
 else
 select coalesce(jsonb_agg(payload order by word_id) filter(where not deleted),'[]'),
 coalesce(jsonb_agg(word_id order by word_id) filter(where deleted),'[]') into ws,ts
 from private.vocab_delta_words where user_id=uid and revision>after_rev and revision<=watermark;
 end if;
 if after_rev is null then
 select coalesce(jsonb_agg(payload order by occurred_at,event_id),'[]') into es from public.vocab_learning_events where user_id=uid;
 else
 select coalesce(jsonb_agg(j.payload order by j.occurred_at,j.event_id),'[]') into es
 from private.vocab_delta_events d join public.vocab_learning_events j using(user_id,event_id)
 where d.user_id=uid and d.revision>after_rev and d.revision<=watermark;
 end if;
 return jsonb_build_object('full',after_rev is null,'epoch',s.epoch,'revision',watermark,'headRevision',s.revision,'words',ws,'events',es,
 'profile',case when after_rev is null then s.profile||jsonb_build_object('rewardLedger',s.legacy_rewards) else s.profile end,
 'tombstones',ts,'acknowledgedEventIds',acks,'hasMore',watermark<s.revision);
end $$;
revoke all on function private.vocab_delta_response_v4(uuid,bigint,jsonb) from public,anon,authenticated,service_role;

create or replace function public.read_vocab_delta_v4(p_after_revision bigint default null,p_expected_epoch uuid default null) returns jsonb
language plpgsql security definer set search_path=pg_catalog,public,private as $$
declare uid uuid:=auth.uid(); s private.vocab_delta_state%rowtype;
begin
 if uid is null then raise insufficient_privilege; end if;
 perform private.ensure_vocab_delta_v4(uid);
 select * into s from private.vocab_delta_state where user_id=uid;
 if p_expected_epoch is not null and p_expected_epoch<>s.epoch then raise exception 'Epoch changed' using detail='VMEPOCH'; end if;
 if p_after_revision>s.revision or p_after_revision<0 then raise exception 'Invalid cursor' using detail='VMREVISION'; end if;
 return private.vocab_delta_response_v4(uid,p_after_revision);
end $$;

create or replace function public.sync_vocab_delta_v4(p_changes jsonb,p_mutation_id uuid,p_expected_epoch uuid,p_expected_revision bigint default null) returns jsonb
language plpgsql security definer set search_path=pg_catalog,public,private as $$
declare uid uuid:=auth.uid(); s private.vocab_delta_state%rowtype; w jsonb; e jsonb; old_event jsonb; current_word jsonb; base jsonb; projected jsonb; r bigint;
 new_ids text[]:='{}'; v_latest_at timestamptz; latest_id text; first_at timestamptz; first_id text; append_only boolean; touched text[]:='{}'; wid text; reward integer; corrects integer; incorrects integer; streak integer; cleared boolean; acks jsonb:='[]'; changed boolean:=false; meta jsonb; counts_as_answer boolean;
begin
 if uid is null then raise insufficient_privilege; end if;
 if p_mutation_id is null or jsonb_typeof(p_changes)<>'object' then raise exception 'Invalid mutation' using errcode='22023'; end if;
 if octet_length(p_changes::text)>131072 or jsonb_array_length(coalesce(p_changes->'words','[]'))>50 or jsonb_array_length(coalesce(p_changes->'events','[]'))>50 or jsonb_array_length(coalesce(p_changes->'tombstones','[]'))>50 then raise exception 'Delta batch too large' using errcode='22023'; end if;
 perform private.ensure_vocab_delta_v4(uid);
 select * into strict s from private.vocab_delta_state where user_id=uid for update;
 if p_expected_epoch is distinct from s.epoch then raise exception 'Epoch changed' using detail='VMEPOCH'; end if;
 if p_expected_revision is null or p_expected_revision<>s.revision then raise exception 'Revision changed' using detail='VMREVISION'; end if;
 r:=s.revision+1;
 for w in select value from jsonb_array_elements(coalesce(p_changes->'words','[]')) loop
  wid:=w->>'id'; if nullif(wid,'') is null then raise exception 'Missing word ID' using errcode='22023'; end if;
  if exists(select 1 from private.vocab_delta_words where user_id=uid and word_id=wid and deleted) then continue; end if;
  select payload into current_word from private.vocab_delta_words where user_id=uid and word_id=wid;
  -- Incoming counters cannot create learning evidence.
  projected:=coalesce(current_word,'{}')||(w-'correctCount'-'incorrectCount'-'consecutiveCorrect'-'mistakeCleared');
  if current_word is null then projected:=projected||'{"correctCount":0,"incorrectCount":0,"consecutiveCorrect":0,"mistakeCleared":false}'::jsonb; end if;
  if projected is distinct from current_word then
   insert into private.vocab_delta_words(user_id,word_id,payload,baseline,revision) values(uid,wid,projected,projected,r)
   on conflict(user_id,word_id) do update set payload=excluded.payload,revision=r;
   changed:=true;
  end if;
 end loop;
 for e in select value from jsonb_array_elements(coalesce(p_changes->'events','[]')) loop
  if nullif(e->>'id','') is null or nullif(e->>'wordId','') is null or e->>'result' not in ('correct','incorrect') or nullif(e->>'at','') is null then raise exception 'Invalid event' using errcode='22023'; end if;
  if (e->>'at')::timestamptz>clock_timestamp()+interval '5 minutes' then raise exception 'Future event' using errcode='22023'; end if;
  reward:=coalesce((e->>'rewardPoints')::int,0); if reward<0 or reward>15 then raise exception 'Invalid reward' using errcode='22023'; end if;
  select payload into old_event from public.vocab_learning_events where user_id=uid and event_id=e->>'id';
  if old_event is not null then
   if (old_event->>'wordId',old_event->>'at',old_event->>'result',coalesce(old_event->>'rewardPoints','0')) is distinct from (e->>'wordId',e->>'at',e->>'result',coalesce(e->>'rewardPoints','0')) then raise exception 'Event identity conflict' using errcode='22023'; end if;
  else
   if not exists(select 1 from private.vocab_delta_words where user_id=uid and word_id=e->>'wordId' and not deleted) then raise exception 'Answer references missing word' using errcode='22023'; end if;
   counts_as_answer:=coalesce(e->>'durableVersion','')='3' or (e->>'at')::timestamptz>s.original_baseline_at;
   insert into public.vocab_learning_events(user_id,event_id,epoch,word_id,occurred_at,result,payload,accounted_as)
   values(uid,e->>'id',s.epoch,e->>'wordId',(e->>'at')::timestamptz,e->>'result',e,case when counts_as_answer then 'answer' else 'baseline' end);
   insert into private.vocab_delta_events values(uid,e->>'id',e->>'wordId',r);
   insert into private.vocab_delta_event_refs values(uid,e->>'id',e->>'wordId',md5(e::text));
   if counts_as_answer then touched:=array_append(touched,e->>'wordId'); new_ids:=array_append(new_ids,e->>'id'); end if;
   changed:=true;
  end if;
  acks:=acks||jsonb_build_array(e->>'id');
 end loop;
 for wid in select distinct unnest(touched) loop
  select payload,baseline,w.latest_at,w.latest_event_id into projected,base,v_latest_at,latest_id from private.vocab_delta_words w where user_id=uid and word_id=wid;
  select occurred_at,event_id into first_at,first_id from public.vocab_learning_events where user_id=uid and word_id=wid and event_id=any(new_ids) order by occurred_at,event_id limit 1;
  append_only:=v_latest_at is null or (first_at,first_id)>(v_latest_at,latest_id);
  if append_only then base:=projected; end if;
  corrects:=coalesce((base->>'correctCount')::int,0); incorrects:=coalesce((base->>'incorrectCount')::int,0);
  streak:=coalesce((base->>'consecutiveCorrect')::int,0); cleared:=coalesce((base->>'mistakeCleared')::boolean,false);
  if append_only then
  for e in select j.payload from public.vocab_learning_events j where j.user_id=uid and j.event_id=any(new_ids) and j.word_id=wid order by j.occurred_at,j.event_id loop
   if e->>'result'='incorrect' then incorrects:=incorrects+1; streak:=0; cleared:=false;
   else corrects:=corrects+1; streak:=streak+1; if incorrects>0 and streak>=2 then cleared:=true; end if; end if;
   v_latest_at:=e->>'at'; latest_id:=e->>'id';
   projected:=projected||jsonb_strip_nulls(jsonb_build_object('readingIntroducedAt',e#>'{wordState,readingIntroducedAt}','readingMasteredAt',e#>'{wordState,readingMasteredAt}','readingNextDueAt',e#>'{wordState,readingNextDueAt}','readingReviewStage',e#>'{wordState,readingReviewStage}'))||jsonb_build_object('vocabMasterProgressUpdatedAt',e->>'at');
  end loop;
  else
  for e in select j.payload from public.vocab_learning_events j where j.user_id=uid and j.word_id=wid and j.epoch=s.epoch and j.accounted_as='answer' order by j.occurred_at,j.event_id loop
   if e->>'result'='incorrect' then incorrects:=incorrects+1; streak:=0; cleared:=false;
   else corrects:=corrects+1; streak:=streak+1; if incorrects>0 and streak>=2 then cleared:=true; end if; end if;
   v_latest_at:=e->>'at'; latest_id:=e->>'id';
   projected:=projected||jsonb_strip_nulls(jsonb_build_object('readingIntroducedAt',e#>'{wordState,readingIntroducedAt}','readingMasteredAt',e#>'{wordState,readingMasteredAt}','readingNextDueAt',e#>'{wordState,readingNextDueAt}','readingReviewStage',e#>'{wordState,readingReviewStage}'))||jsonb_build_object('vocabMasterProgressUpdatedAt',e->>'at');
  end loop;
  end if;
  update private.vocab_delta_words set latest_at=v_latest_at,latest_event_id=latest_id,payload=projected||jsonb_build_object('correctCount',corrects,'incorrectCount',incorrects,'consecutiveCorrect',streak,'mistakeCleared',cleared),revision=r where user_id=uid and word_id=wid;
 end loop;
 for wid in select jsonb_array_elements_text(coalesce(p_changes->'tombstones','[]')) loop
  if nullif(wid,'') is null then raise exception 'Missing tombstone ID' using errcode='22023'; end if;
  insert into private.vocab_delta_words(user_id,word_id,payload,baseline,revision,deleted)
  values(uid,wid,jsonb_build_object('id',wid),'{"correctCount":0,"incorrectCount":0,"consecutiveCorrect":0,"mistakeCleared":false}'::jsonb,r,true)
  on conflict(user_id,word_id) do update set deleted=true,revision=r where not private.vocab_delta_words.deleted;
  if found then changed:=true; end if;
 end loop;
 if p_changes ? 'profile' then
  meta:=p_changes->'profile';
  if jsonb_typeof(meta)<>'object' or meta ?| array['words','studyEvents','rewardLedger','id'] then raise exception 'Invalid profile patch' using errcode='22023'; end if;
  if (s.profile||meta) is distinct from s.profile then update private.vocab_delta_state set profile=profile||meta where user_id=uid; changed:=true; end if;
 end if;
 if changed then update private.vocab_delta_state set revision=r where user_id=uid; end if;
 return private.vocab_delta_response_v4(uid,p_expected_revision,acks);
end $$;
revoke all on function public.read_vocab_delta_v4(bigint,uuid),public.sync_vocab_delta_v4(jsonb,uuid,uuid,bigint) from public,anon;
grant execute on function public.read_vocab_delta_v4(bigint,uuid),public.sync_vocab_delta_v4(jsonb,uuid,uuid,bigint) to authenticated;

create or replace function public.has_vocab_delta_v4() returns boolean
language sql security definer set search_path=pg_catalog,public,private as $$
 select exists(select 1 from private.vocab_delta_state where user_id=auth.uid())
$$;
revoke all on function public.has_vocab_delta_v4() from public,anon;
grant execute on function public.has_vocab_delta_v4() to authenticated;

-- Existing clients must refresh rather than write stale monolithic snapshots.
do $upgrade$
declare definition text;
begin
 definition:=pg_get_functiondef('public.vocab_guard_snapshot_v3()'::regprocedure);
 if position('V4 incremental storage is authoritative' in definition)=0 then
definition:=replace(definition,E'begin\n',$inject$begin
 -- V4 incremental storage is authoritative.
 if exists(select 1 from private.vocab_delta_state where user_id=new.user_id) then raise exception 'Refresh to use incremental sync' using errcode='55000',detail='VMUPGRADE'; end if;
$inject$);
  execute definition;
 end if;
 definition:=pg_get_functiondef('public.sync_vocab_master_v3(jsonb,uuid,uuid)'::regprocedure);
 if position('V4 incremental storage is authoritative' in definition)=0 then
definition:=replace(definition,E'begin\n',$inject$begin
 -- V4 incremental storage is authoritative.
 if public.has_vocab_delta_v4() then raise exception 'Refresh to use incremental sync' using errcode='55000',detail='VMUPGRADE'; end if;
$inject$);
  execute definition;
 end if;
end $upgrade$;
