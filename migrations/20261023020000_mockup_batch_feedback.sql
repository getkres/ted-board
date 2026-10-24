-- NEEDS TED REVIEW. Proposed only. migrations/ is not auto-applied.
-- Existing image-pin RPC and worker queue stay unchanged. Apply only after review.
begin;
set local lock_timeout = '5s';
set local statement_timeout = '30s';
lock table public.ted_mockup_pins in access exclusive mode;

do $$
begin
  if exists (select 1 from pg_catalog.pg_attribute
      where attrelid='public.ted_mockup_pins'::regclass
        and attname='batch_note' and not attisdropped)
     or to_regprocedure('public.ted_mockup_batch_note(text,uuid,text)') is not null
     or to_regprocedure('public.ted_mockup_batch_text_valid(jsonb)') is not null then
    raise exception 'Batch-note schema already exists. Review migration history before applying.';
  end if;
end;
$$;

alter table public.ted_mockup_pins add column batch_note boolean not null default false;

-- The 1200-character limit applies to Sebastian's batch messages. Ted's existing
-- reply RPC still allows 2000 characters. Image-pin history remains untouched.
create function public.ted_mockup_batch_text_valid(p_thread jsonb)
returns boolean language sql immutable strict parallel safe
set search_path=pg_catalog as $$
  select not exists (
    select 1 from pg_catalog.jsonb_array_elements(p_thread) as message
    where message->>'who'='seb'
      and (jsonb_typeof(message->'text') is distinct from 'string'
           or char_length(message->>'text')>1200)
  );
$$;
revoke all on function public.ted_mockup_batch_text_valid(jsonb) from public, anon, authenticated;
grant execute on function public.ted_mockup_batch_text_valid(jsonb) to service_role;
alter table public.ted_mockup_pins add constraint ted_mockup_batch_note_text_check
  check (not batch_note or public.ted_mockup_batch_text_valid(thread));

-- Wrap the existing pin transaction. Marker and receipt labeling are committed
-- together, before the worker can see the existing page=mockups, choice=pin row.
create function public.ted_mockup_batch_note(
  p_action text, p_mockup uuid default null, p_text text default ''
) returns jsonb language plpgsql security invoker set search_path=pg_catalog,public as $$
declare
  result jsonb;
  pin public.ted_mockup_pins;
  mockup public.ted_mockups;
  receipt_id bigint;
begin
  if p_action='capability' then return jsonb_build_object('enabled',true); end if;
  if p_action is distinct from 'pin' or p_mockup is null or p_text is null
     or char_length(trim(p_text))=0 or char_length(p_text)>1200 then
    raise exception 'Invalid batch comment' using errcode='22023';
  end if;
  -- Existing act RPC owns anchor locks, archive checks, rate limits, and receipt.
  result:=public.ted_mockup_act(p_action=>'pin',p_mockup=>p_mockup,
    p_x=>50,p_y=>50,p_text=>trim(p_text));
  receipt_id:=(result->>'decision_id')::bigint;
  update public.ted_mockup_pins set batch_note=true
    where id=(result->'pin'->>'id')::uuid and mockup_id=p_mockup returning * into pin;
  if not found or receipt_id is null then
    raise exception 'Pin transaction did not confirm batch feedback';
  end if;
  select * into mockup from public.ted_mockups where id=p_mockup;
  update public.ted_decisions set note=trim(p_text)
    || E'\nFeedback scope: whole-batch'
    || E'\nMockup: ' || mockup.title
    || E'\nProject: ' || mockup.project
    || E'\nBatch: ' || mockup.batch
    || E'\nMockup ID: ' || mockup.id
    || E'\nPin coords: n/a (whole batch)'
    where id=receipt_id and page='mockups' and choice='pin' and item_id=pin.id::text;
  if not found then raise exception 'Batch feedback receipt missing'; end if;
  return jsonb_build_object('pin',to_jsonb(pin),'decision_id',receipt_id);
end;
$$;
revoke all on function public.ted_mockup_batch_note(text,uuid,text) from public, anon, authenticated;
grant execute on function public.ted_mockup_batch_note(text,uuid,text) to service_role;

-- Existing table RLS and service-role grants remain. No verdict or build action.
notify pgrst, 'reload schema';
commit;
