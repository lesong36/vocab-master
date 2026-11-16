-- Read-only bridge. Receiving a word never writes VocabMaster learning data.
create or replace function public.read_reader_vocabulary_for_review_v1(p_after text default '', p_limit integer default 50)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  account_id uuid := auth.uid();
  result jsonb;
begin
  if account_id is null then raise exception 'authentication required'; end if;
  if p_after is null or p_limit is null or p_limit < 1 or p_limit > 50 then raise exception 'invalid page'; end if;
  with candidates as (
    select lower(btrim(item->>'word')) as key, item as payload, 0 as priority, false as deleted
    from public.reader_sync_state s cross join lateral jsonb_array_elements(s.vocabulary) item
    where s.user_id = account_id
      and not exists (select 1 from reader_delta.accounts a where a.user_id = account_id and a.migrated)
    union all
    select lower(btrim(e.entity_id)), e.payload, 1, e.deleted
    from reader_delta.entities e where e.user_id = account_id and e.entity_type = 'vocabulary'
  ), latest as (
    select distinct on (key) key, payload, deleted from candidates
    where key is not null and key <> '' order by key, priority desc
  ), page as (
    select key,payload from latest where not deleted and key > p_after order by key limit p_limit + 1
  ), visible as (select * from page order by key limit p_limit)
  select jsonb_build_object(
    'entries',coalesce((select jsonb_agg(payload order by key) from visible),'[]'::jsonb),
    'nextAfter',coalesce((select max(key) from visible),p_after),
    'hasMore',(select count(*) > p_limit from page)
  ) into result;
  return result;
end;
$$;
revoke all on function public.read_reader_vocabulary_for_review_v1(text,integer) from public, anon;
grant execute on function public.read_reader_vocabulary_for_review_v1(text,integer) to authenticated;
