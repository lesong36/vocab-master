-- Durable email alert queue. Apply after p0_learning_sync.sql; no credentials here.
begin;
create schema if not exists private;
revoke all on schema private from public, anon, authenticated;
create table if not exists private.vocab_sync_health (
 user_id uuid not null references auth.users(id), device_id uuid not null,
 pending_count integer not null check(pending_count between 0 and 1000000),
 first_pending_at timestamptz, error_code text, first_failure_at timestamptz,
 last_report_at timestamptz not null, primary key(user_id,device_id),
 check(error_code is null or error_code in ('invalid_payload','receipt_invalid','database_rejected','storage_failed','sync_failed'))
);
create table if not exists private.vocab_sync_incidents (
 id uuid primary key default gen_random_uuid(), user_id uuid not null references auth.users(id),
 scope text not null, error_code text not null, pending_count integer not null,
 started_at timestamptz not null, resolved_at timestamptz, resolution_verified boolean not null default false, alert_sent_at timestamptz
);
alter table private.vocab_sync_incidents add column if not exists resolution_verified boolean not null default false;
create unique index if not exists vocab_sync_one_open_incident on private.vocab_sync_incidents(user_id,scope) where resolved_at is null;
create table if not exists private.vocab_sync_deliveries (
 id uuid primary key default gen_random_uuid(), incident_id uuid references private.vocab_sync_incidents(id),
 user_id uuid not null references auth.users(id), kind text not null check(kind in ('alert','recovered','test')),
 error_code text, pending_count integer not null default 0, started_at timestamptz not null default clock_timestamp(),
 created_at timestamptz not null default clock_timestamp(), sent_at timestamptz,
 lease_token uuid, leased_at timestamptz, attempts integer not null default 0,
 provider_id text, failure_code text,
 unique(incident_id,kind)
);
create index if not exists vocab_sync_delivery_pending on private.vocab_sync_deliveries(created_at) where sent_at is null;
create table if not exists private.vocab_sync_monitor_runs (
 checked_at timestamptz not null default clock_timestamp(), outcome text not null
);
alter table private.vocab_sync_health enable row level security;
alter table private.vocab_sync_incidents enable row level security;
alter table private.vocab_sync_deliveries enable row level security;
alter table private.vocab_sync_monitor_runs enable row level security;
revoke all on private.vocab_sync_health,private.vocab_sync_incidents,private.vocab_sync_deliveries,private.vocab_sync_monitor_runs from public,anon,authenticated,service_role;

-- An absent browser is not proof that its pending answers reached the cloud.
-- Zero-pending errors expire after 30 minutes so a closed old tab cannot alert forever.
create or replace function private.refresh_vocab_sync_alerts(p_user_id uuid default null)
returns void language plpgsql security definer set search_path=pg_catalog,public,private as $$
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
 )) loop
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
end $$;
revoke all on function private.refresh_vocab_sync_alerts(uuid) from public,anon,authenticated,service_role;

create or replace function public.report_vocab_sync_health_v1(p_device_id uuid,p_pending_count integer,
 p_oldest_pending_at timestamptz,p_error_code text,p_healthy boolean)
returns jsonb language plpgsql security definer set search_path=pg_catalog,public,private as $$
declare uid uuid:=auth.uid(); now_at timestamptz:=clock_timestamp(); code text; prior private.vocab_sync_health;
begin
 if uid is null then raise exception 'Authentication required' using errcode='42501'; end if;
 if p_device_id is null or p_pending_count is null or p_pending_count<0 or p_pending_count>1000000
  or p_healthy is null or (p_error_code is not null and p_error_code not in
   ('invalid_payload','receipt_invalid','database_rejected','storage_failed','sync_failed')) then
  raise exception 'Invalid health report' using errcode='22023';
 end if;
 -- Client timestamps are diagnostic input only; all timeout decisions use server time.
 code:=case when p_healthy then null else p_error_code end;
 perform pg_advisory_xact_lock(hashtextextended('vocab-health:'||uid::text,0));
 select * into prior from private.vocab_sync_health where user_id=uid and device_id=p_device_id;
 if prior.device_id is not null and prior.pending_count=p_pending_count and prior.error_code is not distinct from code
  and prior.last_report_at>now_at-interval '60 seconds' then
  return jsonb_build_object('accepted',true,'throttled',true,'reportedAt',prior.last_report_at);
 end if;
 if prior.device_id is null then
  delete from private.vocab_sync_health where user_id=uid and pending_count=0 and error_code is null and last_report_at<now_at-interval '7 days';
  if (select count(*) from private.vocab_sync_health where user_id=uid)>=100 then
   raise exception 'Too many reporting devices' using errcode='54000';
  end if;
 end if;
 insert into private.vocab_sync_health(user_id,device_id,pending_count,first_pending_at,error_code,first_failure_at,last_report_at)
 values(uid,p_device_id,p_pending_count,case when p_pending_count>0 then now_at end,code,
  case when code is not null then now_at end,now_at)
 on conflict(user_id,device_id) do update set pending_count=excluded.pending_count,
  first_pending_at=case when excluded.pending_count=0 then null else coalesce(vocab_sync_health.first_pending_at,now_at) end,
  error_code=excluded.error_code,
  first_failure_at=case when excluded.error_code is null then null else coalesce(vocab_sync_health.first_failure_at,now_at) end,
  last_report_at=now_at;
 perform private.refresh_vocab_sync_alerts(uid);
 return jsonb_build_object('accepted',true,'reportedAt',now_at);
end $$;
revoke all on function public.report_vocab_sync_health_v1(uuid,integer,timestamptz,text,boolean) from public,anon;
grant execute on function public.report_vocab_sync_health_v1(uuid,integer,timestamptz,text,boolean) to authenticated;

create or replace function public.collect_vocab_sync_alerts_v1()
returns jsonb language plpgsql security definer set search_path=pg_catalog,public,private as $$
begin
 perform private.refresh_vocab_sync_alerts(null);
 insert into private.vocab_sync_monitor_runs(outcome) values('checked');
 delete from private.vocab_sync_monitor_runs where checked_at<clock_timestamp()-interval '30 days';
 return jsonb_build_object('checkedAt',clock_timestamp());
end $$;
create or replace function public.claim_vocab_sync_alerts_v1()
returns table(id uuid,lease_token uuid,user_id uuid,kind text,error_code text,pending_count integer,started_at timestamptz,incident_id uuid)
language sql security definer set search_path=pg_catalog,public,private as $$
 with pending as (
  select d.id from private.vocab_sync_deliveries d where d.sent_at is null
   and (d.leased_at is null or d.leased_at<clock_timestamp()-interval '5 minutes')
  order by d.attempts,d.created_at,d.id limit 2 for update skip locked
 ), claimed as (
  update private.vocab_sync_deliveries d set lease_token=gen_random_uuid(),leased_at=clock_timestamp(),attempts=attempts+1
  from pending p where d.id=p.id returning d.*
 ) select id,lease_token,user_id,kind,error_code,pending_count,started_at,incident_id from claimed;
$$;
create or replace function public.finish_vocab_sync_alert_v1(p_delivery_id uuid,p_lease_token uuid,p_provider_id text,p_failure_code text)
returns jsonb language plpgsql security definer set search_path=pg_catalog,public,private as $$
declare d private.vocab_sync_deliveries; now_at timestamptz:=clock_timestamp();
begin
 select * into d from private.vocab_sync_deliveries where id=p_delivery_id for update;
 if d.id is null or d.lease_token is distinct from p_lease_token or p_lease_token is null or d.sent_at is not null then
  raise exception 'Invalid delivery lease' using errcode='22023'; end if;
 if p_failure_code is null and nullif(btrim(p_provider_id),'') is null then
  raise exception 'Provider acceptance required' using errcode='22023'; end if;
 update private.vocab_sync_deliveries set sent_at=case when p_failure_code is null then now_at end,
  provider_id=case when p_failure_code is null then left(p_provider_id,200) end,
  failure_code=case when p_failure_code is not null then left(p_failure_code,100) end
 where id=d.id;
 if p_failure_code is null and d.kind='alert' then
  update private.vocab_sync_incidents set alert_sent_at=now_at where id=d.incident_id;
  -- An incident might recover while an alert request is in flight.
  insert into private.vocab_sync_deliveries(incident_id,user_id,kind,error_code,pending_count,started_at)
   select id,user_id,'recovered',error_code,pending_count,started_at from private.vocab_sync_incidents
   where id=d.incident_id and resolved_at is not null and resolution_verified
   on conflict(incident_id,kind) do nothing;
 end if;
 return jsonb_build_object('accepted',p_failure_code is null);
end $$;
revoke all on function public.collect_vocab_sync_alerts_v1(),public.claim_vocab_sync_alerts_v1(),public.finish_vocab_sync_alert_v1(uuid,uuid,text,text) from public,anon,authenticated;
grant execute on function public.collect_vocab_sync_alerts_v1(),public.claim_vocab_sync_alerts_v1(),public.finish_vocab_sync_alert_v1(uuid,uuid,text,text) to service_role;
commit;
