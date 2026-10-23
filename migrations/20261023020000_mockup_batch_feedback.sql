-- NEEDS TED REVIEW. Proposed only, never applied by the card worker.
-- This storage prerequisite does not enable either feature or change an RPC.
begin;
set local lock_timeout = '5s';
set local statement_timeout = '30s';
lock table public.ted_mockups, public.ted_mockup_pins in access exclusive mode;

-- Abort if the reviewed live schema has changed. Do not overwrite another
-- change, such as the separately proposed good_with_fix verdict support.
do $$
begin
  if (
    select pg_get_constraintdef(oid)
    from pg_catalog.pg_constraint
    where conrelid = 'public.ted_mockups'::regclass
      and conname = 'ted_mockups_verdict_check'
  ) is distinct from
    'CHECK (((verdict IS NULL) OR (verdict = ANY (ARRAY[''approved''::text, ''needs_work''::text, ''scrapped''::text]))))'
  then
    raise exception 'Verdict constraint changed. Reconcile this proposal before applying.';
  end if;
  if exists (
    select 1 from pg_catalog.pg_attribute
    where attrelid = 'public.ted_mockup_pins'::regclass
      and attname = 'batch_note' and not attisdropped
  ) then
    raise exception 'batch_note already exists. Review migration history before applying.';
  end if;
end;
$$;

alter table public.ted_mockups drop constraint ted_mockups_verdict_check;
alter table public.ted_mockups add constraint ted_mockups_verdict_check
  check (verdict is null or verdict in ('approved', 'needs_work', 'scrapped', 'not_relevant'));

-- A batch note stays on an existing pin thread, anchored to one mockup in the
-- exact project and batch. Existing pins remain image-scoped. Ted's reply CLI
-- can keep addressing the same pin ID and its existing thread.
alter table public.ted_mockup_pins
  add column batch_note boolean not null default false;

-- No grants, policies, receipt writes, triggers, RPC changes, or build actions.
-- Both tables keep their existing service-role-only access and RLS settings.
notify pgrst, 'reload schema';
commit;
