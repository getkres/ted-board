-- NEEDS TED REVIEW. Proposed only. migrations/ is not auto-applied.
-- Hold application until the batch-comment UI and private routing are reviewed.
-- Adds one scope marker to existing pin threads, with no RPC or verdict changes.
begin;
set local lock_timeout = '5s';
set local statement_timeout = '30s';
lock table public.ted_mockup_pins in access exclusive mode;

do $$
begin
  if exists (
    select 1 from pg_catalog.pg_attribute
    where attrelid = 'public.ted_mockup_pins'::regclass
      and attname = 'batch_note' and not attisdropped
  ) then
    raise exception 'batch_note already exists. Review migration history before applying.';
  end if;
end;
$$;

-- Existing pins remain image-scoped. A marked pin's existing mockup identifies
-- its exact project and batch, and its existing ID remains the reply address.
alter table public.ted_mockup_pins
  add column batch_note boolean not null default false;

-- Existing RLS and service-role-only grants remain. No new table or receipt.
notify pgrst, 'reload schema';
commit;
