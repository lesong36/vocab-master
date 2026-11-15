-- Preserve deployed thresholds and notification cadence. Only switch the integrity source for v4 accounts.
CREATE OR REPLACE FUNCTION private.refresh_vocab_sync_alerts(p_user_id uuid DEFAULT NULL::uuid)
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'public', 'private'
AS $function$
declare r record; incident uuid; now_at timestamptz:=clock_timestamp(); active_scopes jsonb:='{}'; key text;
begin
 perform pg_advisory_xact_lock(hashtextextended('vocab-sync-alert-collector',0));
 for r in select eligible.user_id,'health:'||eligible.error_code scope,eligible.error_code,
 max(eligible.pending_count)::integer pending_count,min(eligible.started_at) started_at from (
 select h.user_id,
   case when h.error_code is not null and h.last_report_at>now_at-interval '30 minutes' then h.error_code else 'pending_backlog' end error_code,
   h.pending_count,
   case when h.error_code is not null and h.last_report_at>now_at-interval '30 minutes' then h.first_failure_at else h.first_pending_at end started_at
 from private.vocab_sync_health h
 where (p_user_id is null or h.user_id=p_user_id) and (
   (h.error_code is not null and h.last_report_at>now_at-interval '30 minutes' and
     (h.error_code<>'sync_failed' or h.first_failure_at<=now_at-interval '5 minutes'))
   or (h.pending_count>0 and h.first_pending_at<=now_at-interval '10 minutes'))
 ) eligible group by eligible.user_id,eligible.error_code
 union all
 select s.user_id,'ledger','journal_mismatch',0,now_at
 from (select user_id from public.reader_sync_state union select user_id from public.vocab_learning_events) tracked
 left join public.reader_sync_state original on original.user_id=tracked.user_id
 cross join lateral (select tracked.user_id,original.vocab_master_progress) s
 where (p_user_id is null or s.user_id=p_user_id)
 and not exists(select 1 from private.vocab_delta_state ds where ds.user_id=s.user_id)
 and ((select count(*) from jsonb_each(coalesce(s.vocab_master_progress#>'{appState,users}','{}')) p,
       jsonb_array_elements(coalesce(p.value->'studyEvents','[]')) e)
      <> (select count(*) from public.vocab_learning_events where user_id=s.user_id)
 or exists (
  (select e from jsonb_each(coalesce(s.vocab_master_progress#>'{appState,users}','{}')) p,
    jsonb_array_elements(coalesce(p.value->'studyEvents','[]')) e
   except select payload from public.vocab_learning_events where user_id=s.user_id)
  union all
  (select payload from public.vocab_learning_events where user_id=s.user_id
   except select e from jsonb_each(coalesce(s.vocab_master_progress#>'{appState,users}','{}')) p,
     jsonb_array_elements(coalesce(p.value->'studyEvents','[]')) e)
 ))
 union all
 select ds.user_id,'ledger','journal_mismatch',0,now_at
 from private.vocab_delta_state ds
 where (p_user_id is null or ds.user_id=p_user_id) and (
   exists (
     select 1 from private.vocab_delta_event_refs ref
     full join public.vocab_learning_events journal using(user_id,event_id)
     where coalesce(ref.user_id,journal.user_id)=ds.user_id
       and (ref.event_id is null or journal.event_id is null
         or ref.word_id is distinct from journal.word_id
         or ref.payload_hash is distinct from md5(journal.payload::text))
   )
   or exists (
     select 1 from private.vocab_delta_event_refs ref
     left join private.vocab_delta_words word on word.user_id=ref.user_id and word.word_id=ref.word_id
     where ref.user_id=ds.user_id and word.word_id is null
       and not coalesce(ds.profile->'ignoredReadingWordIds','[]'::jsonb) ? ref.word_id
   )
   or exists (
     select 1 from private.vocab_delta_words word
     left join lateral (
       select count(*) filter(where journal.result='correct') corrects,
         count(*) filter(where journal.result='incorrect') incorrects
       from public.vocab_learning_events journal
       where journal.user_id=word.user_id and journal.word_id=word.word_id
         and journal.epoch=ds.epoch and journal.accounted_as='answer'
     ) answers on true
     where word.user_id=ds.user_id and not word.deleted and (
       word.payload->>'id' is distinct from word.word_id
       or coalesce((word.payload->>'correctCount')::bigint,0) <>
          coalesce((word.baseline->>'correctCount')::bigint,0)+answers.corrects
       or coalesce((word.payload->>'incorrectCount')::bigint,0) <>
          coalesce((word.baseline->>'incorrectCount')::bigint,0)+answers.incorrects
     )
   )
 ) loop
  key:=r.user_id::text||'/'||r.scope;
  active_scopes:=active_scopes||jsonb_build_object(key,true);
  insert into private.vocab_sync_incidents(user_id,scope,error_code,pending_count,started_at)
   values(r.user_id,r.scope,r.error_code,r.pending_count,r.started_at)
   on conflict(user_id,scope) where resolved_at is null do update
    set error_code=excluded.error_code,pending_count=excluded.pending_count
   returning id into incident;
  insert into private.vocab_sync_deliveries(incident_id,user_id,kind,error_code,pending_count,started_at)
   select id,user_id,'alert',error_code,pending_count,started_at from private.vocab_sync_incidents where id=incident
   on conflict(incident_id,kind) do nothing;
 end loop;
 update private.vocab_sync_incidents i set resolved_at=now_at
 where resolved_at is null and (p_user_id is null or i.user_id=p_user_id)
  and not (active_scopes ? (i.user_id::text||'/'||i.scope));
 -- Expiry of a closed zero-pending browser is not a verified recovery.
 -- A later explicit healthy report can verify an already retired incident.
 update private.vocab_sync_incidents i set resolution_verified=true
 where resolved_at is not null and not resolution_verified and (p_user_id is null or i.user_id=p_user_id)
 and (i.scope='ledger' or (i.scope='health:pending_backlog' and not exists(
   select 1 from private.vocab_sync_health h where h.user_id=i.user_id and h.pending_count>0))
  or (i.scope like 'health:%' and i.scope<>'health:pending_backlog' and not exists(
   select 1 from private.vocab_sync_health h where h.user_id=i.user_id and h.error_code=substring(i.scope from 8))));
 -- Never send recovery before a provider has accepted the original alert.
 insert into private.vocab_sync_deliveries(incident_id,user_id,kind,error_code,pending_count,started_at)
  select id,user_id,'recovered',error_code,pending_count,started_at from private.vocab_sync_incidents
  where resolved_at is not null and resolution_verified and alert_sent_at is not null and (p_user_id is null or user_id=p_user_id)
  on conflict(incident_id,kind) do nothing;
end $function$;

