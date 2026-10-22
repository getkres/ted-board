-- PROPOSED D5 SCHEMA ONLY. Review against private backend before applying.
-- This does not change the existing verdict RPC, receipts, or Undo semantics.
-- Take a schema and data backup first. No database commands were run for this build.
begin;
set local lock_timeout = '5s';
set local statement_timeout = '30s';
do $$
declare col record; definition text; constraint_row record;
begin
  if to_regclass('public.ted_mockups') is null or to_regclass('public.ted_mockup_pins') is null then
    raise exception 'Required mockup tables are missing. Stop and inspect private migrations.';
  end if;
  if not exists(select 1 from pg_attribute where attrelid='public.ted_mockups'::regclass and attname='id' and atttypid='uuid'::regtype and not attisdropped)
     or not exists(select 1 from pg_attribute where attrelid='public.ted_mockup_pins'::regclass and attname='id' and atttypid='uuid'::regtype and not attisdropped) then
    raise exception 'Expected UUID mockup and pin IDs';
  end if;
  select a.attnum,t.typtype,t.typname,n.nspname into col from pg_attribute a join pg_type t on t.oid=a.atttypid join pg_namespace n on n.oid=t.typnamespace
    where a.attrelid='public.ted_mockups'::regclass and a.attname='verdict' and not a.attisdropped;
  if not found then raise exception 'Apply the existing private verdict migration first'; end if;
  if col.typtype='e' then
    execute format('alter type %I.%I add value if not exists %L',col.nspname,col.typname,'good_with_fix');
  elsif col.typname in ('text','varchar') then
    -- Only modify constraints scoped exclusively to verdict. Multi-column constraints
    -- may encode receipt invariants and must be inspected by the private backend owner.
    if exists(select 1 from pg_constraint where conrelid='public.ted_mockups'::regclass and contype='c' and col.attnum=any(conkey) and array_length(conkey,1)>1) then
      raise exception 'Multi-column verdict constraint requires a reviewed private migration';
    end if;
    for constraint_row in select conname,pg_get_expr(conbin,conrelid) as expression from pg_constraint
      where conrelid='public.ted_mockups'::regclass and contype='c' and conkey=array[col.attnum]::smallint[]
    loop
      if position('good_with_fix' in constraint_row.expression)=0 then
        execute format('alter table public.ted_mockups drop constraint %I',constraint_row.conname);
        execute format('alter table public.ted_mockups add constraint %I check ((%s) or verdict = %L)',constraint_row.conname,constraint_row.expression,'good_with_fix');
      end if;
    end loop;
  else raise exception 'Unsupported verdict type: inspect private schema before extending';
  end if;
end $$;
alter table public.ted_mockups add column if not exists kind text;
alter table public.ted_mockups add column if not exists lineage text;
alter table public.ted_mockups add column if not exists version integer;
-- No batch table is documented, so uploader repeats this metadata on each batch row.
alter table public.ted_mockups add column if not exists review_chain jsonb;
do $$
begin
  if exists(select 1 from pg_attribute where attrelid='public.ted_mockups'::regclass and not attisdropped and
    ((attname in ('kind','lineage') and atttypid<>'text'::regtype) or (attname='version' and atttypid<>'integer'::regtype) or (attname='review_chain' and atttypid<>'jsonb'::regtype))) then
    raise exception 'Existing D5 column types are incompatible';
  end if;
  if not exists(select 1 from pg_constraint where conrelid='public.ted_mockups'::regclass and conname='ted_mockups_v3_metadata_check') then
    alter table public.ted_mockups add constraint ted_mockups_v3_metadata_check check (
      (kind is null or kind in ('set','stack','round')) and (lineage is null or length(lineage) between 1 and 200)
      and (version is null or version>0) and (review_chain is null or (jsonb_typeof(review_chain)='array' and octet_length(review_chain::text)<=65536))
    );
  end if;
end $$;
create table if not exists public.ted_mockup_strokes (
  id uuid primary key default gen_random_uuid(),
  mockup_id uuid not null references public.ted_mockups(id),
  pin_id uuid references public.ted_mockup_pins(id),
  frame_id text,
  tool text not null check (tool in ('draw','arrow','box','text')),
  svg_path text not null check (length(svg_path) between 1 and 50000 and svg_path ~ '^[MmLlHhVvCcSsQqTtAaZz0-9eE+.,[:space:]-]+$'),
  color text not null check (color in ('#c52b35','#1f6b4f','#181818')),
  text_content text check (text_content is null or length(text_content)<=1200),
  created_at timestamptz not null default now()
);
do $$
declare actual text[];
begin
  select array_agg(attname::text || ':' || format_type(atttypid,atttypmod) order by attnum) into actual
    from pg_attribute where attrelid='public.ted_mockup_strokes'::regclass and attnum>0 and not attisdropped;
  if actual is distinct from array['id:uuid','mockup_id:uuid','pin_id:uuid','frame_id:text','tool:text','svg_path:text','color:text','text_content:text','created_at:timestamp with time zone'] then
    raise exception 'Existing strokes table differs from reviewed contract';
  end if;
end $$;
create index if not exists ted_mockup_strokes_mockup_created_idx on public.ted_mockup_strokes(mockup_id,created_at);
create index if not exists ted_mockup_strokes_pin_idx on public.ted_mockup_strokes(pin_id) where pin_id is not null;
alter table public.ted_mockup_strokes enable row level security;
revoke all on public.ted_mockup_strokes from public,anon,authenticated;
grant select,insert,update,delete on public.ted_mockup_strokes to service_role;
commit;
