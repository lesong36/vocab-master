-- Run as postgres after both P0 migrations. Synthetic rows are rolled back.
begin;
insert into auth.users(id,email) values('33333333-3333-4333-8333-333333333333','alert-test@example.invalid');
set local role authenticated;
select set_config('request.jwt.claim.sub','33333333-3333-4333-8333-333333333333',true);
select public.report_vocab_sync_health_v1('44444444-4444-4444-8444-444444444444',2,'1900-01-01','invalid_payload',false);
do $$ begin
 begin perform public.claim_vocab_sync_alerts_v1(); raise exception 'Authenticated claimed mail'; exception when insufficient_privilege then null; end;
 begin perform public.collect_vocab_sync_alerts_v1(); raise exception 'Authenticated monitored'; exception when insufficient_privilege then null; end;
 begin perform public.finish_vocab_sync_alert_v1(gen_random_uuid(),gen_random_uuid(),'provider',null); raise exception 'Authenticated finished mail'; exception when insufficient_privilege then null; end;
 begin perform public.report_vocab_sync_health_v1(gen_random_uuid(),-1,null,null,true); raise exception 'Negative count accepted'; exception when invalid_parameter_value then null; end;
 begin perform public.report_vocab_sync_health_v1(gen_random_uuid(),1,null,'secret arbitrary text',false); raise exception 'Arbitrary error accepted'; exception when invalid_parameter_value then null; end;
end $$;
reset role;
do $$ begin
 if (select count(*) from private.vocab_sync_incidents where user_id='33333333-3333-4333-8333-333333333333')<>1 then raise exception 'Permanent error not immediate'; end if;
 if (select first_pending_at<clock_timestamp()-interval '1 minute' from private.vocab_sync_health where user_id='33333333-3333-4333-8333-333333333333') then raise exception 'Trusted client time'; end if;
end $$;
set local role authenticated;
select public.report_vocab_sync_health_v1('55555555-5555-4555-8555-555555555555',3,null,'invalid_payload',false);
select public.report_vocab_sync_health_v1('66666666-6666-4666-8666-666666666666',0,null,null,true);
select public.report_vocab_sync_health_v1('44444444-4444-4444-8444-444444444444',0,null,null,true);
reset role;
do $$ declare d record; first_id uuid; first_token uuid; r jsonb; begin
 if (select count(*) from private.vocab_sync_deliveries where user_id='33333333-3333-4333-8333-333333333333')<>1 then raise exception 'Same fault mailed twice'; end if;
 if (select count(*) from private.vocab_sync_incidents where user_id='33333333-3333-4333-8333-333333333333' and resolved_at is null)<>1 then raise exception 'Healthy tab cleared other tab'; end if;
 select * into d from public.claim_vocab_sync_alerts_v1() where user_id='33333333-3333-4333-8333-333333333333';
 first_id:=d.id; first_token:=d.lease_token;
 if d.pending_count<>2 then raise exception 'Delivery body not frozen'; end if;
 if exists(select 1 from public.claim_vocab_sync_alerts_v1() where user_id=d.user_id) then raise exception 'Active lease reclaimed'; end if;
 begin perform public.finish_vocab_sync_alert_v1(d.id,gen_random_uuid(),'provider',null); raise exception 'Wrong lease accepted'; exception when invalid_parameter_value then null; end;
 begin perform public.finish_vocab_sync_alert_v1(d.id,d.lease_token,null,null); raise exception 'Missing provider accepted'; exception when invalid_parameter_value then null; end;
 perform public.finish_vocab_sync_alert_v1(d.id,d.lease_token,null,'provider_rejected');
 if (select sent_at is not null from private.vocab_sync_deliveries where id=d.id) then raise exception 'Rejected mail marked sent'; end if;
 update private.vocab_sync_deliveries set leased_at=clock_timestamp()-interval '6 minutes' where id=d.id;
 select * into d from public.claim_vocab_sync_alerts_v1() where id=first_id;
 if d.id<>first_id or d.lease_token=first_token or d.pending_count<>2 then raise exception 'Retry identity/body changed'; end if;
 perform public.finish_vocab_sync_alert_v1(d.id,d.lease_token,'provider-accepted',null);
end $$;
set local role authenticated;
select public.report_vocab_sync_health_v1('55555555-5555-4555-8555-555555555555',0,null,null,true);
reset role;
do $$ begin
 if (select count(*) from private.vocab_sync_deliveries where user_id='33333333-3333-4333-8333-333333333333' and kind='recovered')<>1 then raise exception 'Recovery missing'; end if;
 perform public.collect_vocab_sync_alerts_v1(); perform public.collect_vocab_sync_alerts_v1();
 if (select count(*) from private.vocab_sync_deliveries where user_id='33333333-3333-4333-8333-333333333333' and kind='recovered')<>1 then raise exception 'Repeated recovery'; end if;
end $$;
-- Transient errors wait five minutes; pending work waits ten, using server first seen.
set local role authenticated;
select public.report_vocab_sync_health_v1('77777777-7777-4777-8777-777777777777',1,'1900-01-01','sync_failed',false);
reset role;
do $$ begin
 if exists(select 1 from private.vocab_sync_incidents where user_id='33333333-3333-4333-8333-333333333333' and scope='health:sync_failed') then raise exception 'Transient alerted too soon'; end if;
 update private.vocab_sync_health set first_failure_at=clock_timestamp()-interval '6 minutes' where device_id='77777777-7777-4777-8777-777777777777';
 perform public.collect_vocab_sync_alerts_v1();
 if not exists(select 1 from private.vocab_sync_incidents where user_id='33333333-3333-4333-8333-333333333333' and scope='health:sync_failed' and resolved_at is null) then raise exception 'Transient alert missing'; end if;
end $$;
set local role authenticated;
select public.report_vocab_sync_health_v1('77777777-7777-4777-8777-777777777777',1,null,null,true);
reset role;
do $$ begin
 if (select first_pending_at is null from private.vocab_sync_health where device_id='77777777-7777-4777-8777-777777777777') then raise exception 'Healthy with pending erased clock'; end if;
 update private.vocab_sync_health set first_pending_at=clock_timestamp()-interval '11 minutes',last_report_at=clock_timestamp()-interval '2 days' where device_id='77777777-7777-4777-8777-777777777777';
 perform public.collect_vocab_sync_alerts_v1();
 if not exists(select 1 from private.vocab_sync_incidents where scope='health:pending_backlog' and user_id='33333333-3333-4333-8333-333333333333' and resolved_at is null) then raise exception 'Closed pending tab lost alert'; end if;
end $$;
-- A closed tab with no pending events eventually expires, unlike pending tabs.
set local role authenticated;
select public.report_vocab_sync_health_v1('88888888-8888-4888-8888-888888888888',0,null,'database_rejected',false);
reset role;
do $$ declare d record; token uuid:=gen_random_uuid(); begin
 update private.vocab_sync_deliveries q set lease_token=token,leased_at=clock_timestamp()
 from private.vocab_sync_incidents i where q.incident_id=i.id and i.user_id='33333333-3333-4333-8333-333333333333'
 and i.scope='health:database_rejected' and q.kind='alert';
 select q.* into d from private.vocab_sync_deliveries q join private.vocab_sync_incidents i on i.id=q.incident_id
 where i.user_id='33333333-3333-4333-8333-333333333333' and i.scope='health:database_rejected' and q.kind='alert';
 perform public.finish_vocab_sync_alert_v1(d.id,token,'stale-alert-accepted',null);
end $$;
update private.vocab_sync_health set last_report_at=clock_timestamp()-interval '31 minutes' where device_id='88888888-8888-4888-8888-888888888888';
select public.collect_vocab_sync_alerts_v1();
do $$ begin
 if exists(select 1 from private.vocab_sync_incidents where user_id='33333333-3333-4333-8333-333333333333' and scope='health:database_rejected' and resolved_at is null) then raise exception 'Stale empty tab stayed failed'; end if;
 if exists(select 1 from private.vocab_sync_deliveries q join private.vocab_sync_incidents i on i.id=q.incident_id
  where i.scope='health:database_rejected' and i.user_id='33333333-3333-4333-8333-333333333333' and q.kind='recovered') then
  raise exception 'Expiry falsely claimed recovery'; end if;
end $$;
set local role authenticated;
select public.report_vocab_sync_health_v1('88888888-8888-4888-8888-888888888888',0,null,null,true);
reset role;
do $$ begin
 if not exists(select 1 from private.vocab_sync_deliveries q join private.vocab_sync_incidents i on i.id=q.incident_id
  where i.scope='health:database_rejected' and i.user_id='33333333-3333-4333-8333-333333333333' and q.kind='recovered') then
  raise exception 'Explicit healthy did not verify retired incident'; end if;
end $$;
-- Monitor catches loss even with no browser report; journal and snapshot are independent.
insert into public.reader_sync_state(user_id,vocab_master_progress) values('33333333-3333-4333-8333-333333333333',
 jsonb_build_object('appState',jsonb_build_object('users',jsonb_build_object('reader_33333333-3333-4333-8333-333333333333',
 jsonb_build_object('words','[]'::jsonb,'studyEvents','[]'::jsonb)))));
alter table public.reader_sync_state disable trigger vocab_guard_snapshot_v3;
update public.reader_sync_state set vocab_master_progress=jsonb_set(vocab_master_progress,
 '{appState,users,reader_33333333-3333-4333-8333-333333333333,studyEvents}','[{"id":"missing-journal"}]')
 where user_id='33333333-3333-4333-8333-333333333333';
select public.collect_vocab_sync_alerts_v1();
do $$ begin
 if not exists(select 1 from private.vocab_sync_incidents where user_id='33333333-3333-4333-8333-333333333333' and scope='ledger' and resolved_at is null) then raise exception 'Independent mismatch missed'; end if;
 if not exists(select 1 from private.vocab_sync_monitor_runs) then raise exception 'No monitor audit'; end if;
end $$;
-- Pruning never removes stale errors as if the browser reported healthy.
update private.vocab_sync_health set error_code='storage_failed',first_failure_at=clock_timestamp()-interval '8 days',
 last_report_at=clock_timestamp()-interval '8 days' where device_id='88888888-8888-4888-8888-888888888888';
set local role authenticated;
select public.report_vocab_sync_health_v1('99999999-9999-4999-8999-999999999999',0,null,null,true);
reset role;
do $$ begin
 if not exists(select 1 from private.vocab_sync_health where device_id='88888888-8888-4888-8888-888888888888') then
  raise exception 'Stale error pruned into false recovery'; end if;
end $$;
-- Unchanged heartbeats are throttled; arbitrary devices are bounded.
set local role authenticated;
do $$ declare r jsonb; begin
 perform public.report_vocab_sync_health_v1('66666666-6666-4666-8666-666666666666',0,null,null,true);
 r:=public.report_vocab_sync_health_v1('66666666-6666-4666-8666-666666666666',0,null,null,true);
 if r->>'throttled'<>'true' then raise exception 'Unchanged report not throttled'; end if;
end $$;
reset role;
insert into private.vocab_sync_health(user_id,device_id,pending_count,last_report_at)
 select '33333333-3333-4333-8333-333333333333',gen_random_uuid(),0,clock_timestamp() from generate_series(1,94);
set local role authenticated;
do $$ begin
 begin perform public.report_vocab_sync_health_v1(gen_random_uuid(),0,null,null,true); raise exception 'Device cap missing'; exception when program_limit_exceeded then null; end;
end $$;
reset role;
set local role anon;
do $$ begin
 begin perform public.report_vocab_sync_health_v1(gen_random_uuid(),0,null,null,true); raise exception 'Anon reported'; exception when insufficient_privilege then null; end;
end $$;
reset role;
set local role service_role;
select public.collect_vocab_sync_alerts_v1();
select count(*) from public.claim_vocab_sync_alerts_v1();
reset role;
rollback;
