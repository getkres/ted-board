# Supabase table migrations

Every new public table must receive explicit Data API grants in its creating migration, immediately after `CREATE TABLE`, and must enable row level security. Supabase stops automatically granting API access to new public tables on October 30, 2026. RLS controls rows; grants permit API access. Existing grants remain unchanged.

Ted Board and mockup backends use service-role access through authenticated Edge Functions. Preserve this convention: grant CRUD only to `service_role`, keep RLS enabled, and revoke access from `public`, `anon`, and `authenticated`. Never add browser-role grants without a separately reviewed requirement and appropriate RLS policies.

Use this template, replacing `example` with the actual table name:

```sql
create table public.example (
  id uuid primary key default gen_random_uuid()
);
grant select, insert, update, delete on table public.example to service_role;
alter table public.example enable row level security;
revoke all on table public.example from public, anon, authenticated;
```

For a separately approved browser-facing table, the standard grant is:

```sql
grant select, insert, update, delete on table public.example to anon, authenticated, service_role;
```

Keep RLS enabled, and define reviewed policies for any browser operations. Never use default privileges as a substitute for a table-specific grant. Use literal top-level DDL and grants so the offline guard can inspect them. Dynamic or procedural table creation requires conversion to literal migration SQL. The guard conservatively rejects procedural `EXECUTE`, including dynamic queries that do not create tables, because it cannot establish their effects offline. Avoid custom `search_path`; explicitly qualify public table names.

Run `python3 scripts/check_data_api_grants.py` and `python3 -m unittest discover -s tests -p 'test_data_api_grants.py'` before committing. The guard requires explicit service-role CRUD and RLS for every new public table, checks each creating migration independently, and covers all three migration roots. Historical cutoffs are fixed in the script. Do not advance them to suppress failures.

The public repository contains only the static frontend and public documentation, plus this offline check. Backend migrations and operational files remain local. Run `python3 scripts/check_data_api_grants.py --root /path/to/local/ted-board` to check those trees before handing over SQL. CI checks any future migrations committed to the public repository and runs guard regression tests; it cannot inspect ignored local files.

Do not rewrite applied migrations. Verify unapplied status with read-only history before changing existing migration SQL. Database application, deployment, and remote SQL execution require separate authorization.
