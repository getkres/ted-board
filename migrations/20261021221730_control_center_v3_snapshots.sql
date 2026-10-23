-- REVIEW ONLY. Ted applies this after taking the backup described in apply.sql.
begin;
set local lock_timeout = '5s';
set local statement_timeout = '30s';
create table if not exists public.ted_board_snapshots (
  kind text not null check (kind in ('decisions','routines','pods','roadmap')),
  key text not null check (length(key) between 1 and 100 and key ~ '^[a-zA-Z0-9][a-zA-Z0-9_./:-]*$'),
  payload jsonb not null check (jsonb_typeof(payload) = 'object' and octet_length(payload::text) <= 524288),
  generated_at timestamptz not null,
  primary key (kind,key)
);
-- IF NOT EXISTS must never silently adopt an incompatible relation.
do $$
declare actual text[];
begin
  select array_agg(attname::text || ':' || format_type(atttypid,atttypmod) || ':' || attnotnull::text order by attnum)
    into actual from pg_attribute where attrelid='public.ted_board_snapshots'::regclass and attnum>0 and not attisdropped;
  if actual is distinct from array['kind:text:true','key:text:true','payload:jsonb:true','generated_at:timestamp with time zone:true'] then
    raise exception 'Snapshot schema differs from reviewed contract. Stop and inspect.';
  end if;
  if not exists(select 1 from pg_constraint where conrelid='public.ted_board_snapshots'::regclass and contype='p' and conkey=array[1,2]::smallint[]) then
    raise exception 'Snapshot primary key is incompatible';
  end if;
end $$;
alter table public.ted_board_snapshots enable row level security;
revoke all on public.ted_board_snapshots from public,anon,authenticated;
grant select,insert,update on public.ted_board_snapshots to service_role;

-- Atomic snapshot replacement, with stale worker deliveries ignored.
create or replace function public.ted_board_snapshot_push(p_rows jsonb)
returns void language plpgsql security invoker set search_path = pg_catalog,public as $$
begin
  if jsonb_typeof(p_rows) is distinct from 'array' or jsonb_array_length(p_rows) not between 1 and 50 or octet_length(p_rows::text)>2097152 then
    raise exception 'Invalid snapshot envelope';
  end if;
  if exists(select 1 from jsonb_array_elements(p_rows) r
      where jsonb_typeof(r) is distinct from 'object'
        or r->>'kind' is null or r->>'kind' not in ('decisions','routines','pods','roadmap')
        or r->>'key' is null or length(r->>'key') not between 1 and 100 or r->>'key' !~ '^[a-zA-Z0-9][a-zA-Z0-9_./:-]*$'
        or jsonb_typeof(r->'payload') is distinct from 'object'
        or r->>'generated_at' is null or (r->>'generated_at')::timestamptz > now()+interval '5 minutes'
        or octet_length((r->'payload')::text)>524288) then
    raise exception 'Invalid snapshot row';
  end if;
  if exists(select 1 from jsonb_array_elements(p_rows) r group by r->>'kind',r->>'key' having count(*)>1) then
    raise exception 'Duplicate snapshot key';
  end if;
  insert into public.ted_board_snapshots(kind,key,payload,generated_at)
    select r->>'kind',r->>'key',r->'payload',(r->>'generated_at')::timestamptz from jsonb_array_elements(p_rows) r
  on conflict(kind,key) do update set payload=excluded.payload,generated_at=excluded.generated_at
  where excluded.generated_at>ted_board_snapshots.generated_at;
end $$;
revoke all on function public.ted_board_snapshot_push(jsonb) from public,anon,authenticated;
grant execute on function public.ted_board_snapshot_push(jsonb) to service_role;
commit;
