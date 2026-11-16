begin;
do $$
declare owner_id uuid; page jsonb; after_key text := ''; total integer := 0; expected integer;
begin
  select user_id into owner_id from reader_delta.entities where entity_type='vocabulary' and entity_id='population' limit 1;
  if owner_id is null then raise exception 'missing fixture account'; end if;
  perform set_config('request.jwt.claim.sub',owner_id::text,true);
  loop
    page := public.read_reader_vocabulary_for_review_v1(after_key,50);
    if jsonb_array_length(page->'entries') > 50 then raise exception 'unbounded page'; end if;
    total := total + jsonb_array_length(page->'entries');
    exit when not (page->>'hasMore')::boolean;
    if page->>'nextAfter' <= after_key then raise exception 'stalled cursor'; end if;
    after_key := page->>'nextAfter';
  end loop;
  if total < 2 then raise exception 'missing review words'; end if;
  page := public.read_reader_vocabulary_for_review_v1('populatio',1);
  if lower(page->'entries'->0->>'word') <> 'population' then raise exception 'population missing'; end if;
  page := public.read_reader_vocabulary_for_review_v1('tabl',1);
  if lower(page->'entries'->0->>'word') <> 'table' then raise exception 'table missing'; end if;
  perform set_config('request.jwt.claim.sub','00000000-0000-0000-0000-000000000001',true);
  page := public.read_reader_vocabulary_for_review_v1();
  if jsonb_array_length(page->'entries') <> 0 then raise exception 'cross-account leak'; end if;
  if has_function_privilege('anon','public.read_reader_vocabulary_for_review_v1(text,integer)','execute') then raise exception 'anonymous access'; end if;
  if not has_function_privilege('authenticated','public.read_reader_vocabulary_for_review_v1(text,integer)','execute') then raise exception 'authenticated access missing'; end if;
  begin
    perform public.read_reader_vocabulary_for_review_v1('',51);
    raise exception 'limit accepted';
  exception when others then if sqlerrm <> 'invalid page' then raise; end if; end;
  raise notice 'PASS: pagination, actual population/table, account isolation, grants, limits; % words',total;
end $$;
rollback;
