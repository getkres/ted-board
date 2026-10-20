# Data API grant audit, October 20, 2026

Supabase will stop automatically exposing new public tables to its Data API on October 30, 2026. Explicit table grants and RLS are separate requirements. [Supabase announcement](https://supabase.com/changelog/45329-breaking-change-tables-not-exposed-to-data-and-graphql-api-automatically).

## Existing migration inventory

The public Git repository contains the frontend and documentation. All three backend trees below are ignored local operational files. They were inspected in the canonical local checkout, without publishing them or executing SQL.

| Migration root | Files audited | Fixed newest-existing cutoff |
| --- | ---: | --- |
| `supabase/migrations` | 5 | `20261017030000` |
| `mockups-backend/supabase/migrations` | 1 | `20261016160000` |
| `mockups-verification/supabase/migrations` | 1 | `20261016160000` |

All eight distinct public tables created in these seven files have explicit service-role table grants, enabled RLS, and client-role revocations. None depends on default table grants for its intended service-role access.

| Creating migration | Public tables | Explicit access |
| --- | --- | --- |
| `20261016050000_ted_board.sql` | `ted_board_cards` | `GRANT ALL` to `service_role` |
| `20261017020000_frontdoor.sql` | `ted_board_sessions`, `ted_board_approvals`, `ted_board_commands`, and `ted_board_deliveries` | `GRANT ALL` to `service_role` |
| `20261017030000_ted_board_fresh.sql` | `ted_board_fresh` | `GRANT ALL` to `service_role` |
| `20261016160000_ted_mockups.sql`, both copies | `ted_mockups` and `ted_mockup_pins` | `GRANT ALL` to `service_role` |

The other two main-root migrations modify functions and do not create tables. Service-role-only access is intentional: clients call Edge Functions, and backend table access is not granted directly to browser roles. No historical migrations were rewritten.

## Other creation sites

- No reusable migration generator, scaffold, or schema-emitting helper was found in the canonical Ted Board source. The SQL template in [AGENTS.md](../AGENTS.md) is the canonical rule for future work.
- `frontdoor/fresh-sql-test.sql` repeats `ted_board_fresh`, already with explicit service-role grants and RLS.
- `mockups-verification/tests/record-migration.sql` records the existing mockup migration text, including its grants and RLS. It is a historical fixture, not a new schema template. It was read only.
- `mockup-zoom/all-clear-apply.sql` creates `ted_mockup_batch_operations`, already with explicit service-role grants and RLS. It is a standalone operational SQL artifact, not a versioned migration, and was not executed or edited.
- Other job bundles, snapshots, and worktrees are separate in-flight or historical work. A discovered `20261020000006_pod_pulse.sql` in the `pod-pulse` and `integrate-1019` worktrees explicitly grants `SELECT`, `INSERT`, and `UPDATE` to `service_role` and enables RLS. It does not rely on defaults for those operations, but it omits an explicit `DELETE` grant, which the new standard CRUD check would flag. Its remote applied state was not verified, so it was not changed here. These separate worktrees remain untouched.

## Check and coverage

`python3 scripts/check_data_api_grants.py` inspects numeric migration versions strictly newer than the fixed cutoffs above. Each creating file must explicitly grant service-role CRUD and enable RLS for each public table. It handles unqualified names as public, quoted names, multiple table targets, split grants, later revokes, and later RLS disable statements. Comments, strings, and function-body grants cannot satisfy a table grant. Procedural table DDL is rejected for manual conversion to literal migration SQL.

The implementation is a lightweight offline SQL check, not a PostgreSQL parser. Use literal top-level statements, schema-qualified names, ordinary per-table grants, and the documented template. It conservatively rejects procedural `EXECUTE`, even for dynamic queries that do not create tables, because their effects cannot be established offline. It also rejects procedural ACL/RLS changes, search-path changes, and top-level `set_config` calls, including unrelated configuration changes that need manual review. It does not establish remote ACLs, policy correctness, sequence privileges, or API configuration. Every table in a creating migration is checked independently of other files, so a later migration cannot silently supply a missing grant.

The GitHub workflow runs the guard regression tests and checks any future committed migrations. Because backend trees are local-only, public CI currently sees zero migration files. Before handing over local SQL, run:

```sh
python3 scripts/check_data_api_grants.py --root /path/to/local/ted-board
```

Current canonical local trees contain zero migrations beyond their cutoffs. Separate in-flight worktrees can be checked with the same `--root` option.

## Verification and boundaries

- Guard regression tests passed.
- Existing canonical local Python suite: 69 tests passed.
- Existing canonical local Deno suites: 77 tests passed, including backend mockup and verification tests. These use fixtures and require only file-read permissions.
- Static JavaScript syntax and Python compilation checks passed. No existing lint configuration or package runner is tracked in the public repository.
- Docker is unavailable on this machine, so no local database reset was run.
- No remote SQL, migration application, deployment, upload, or merge was performed. Remote history and ACLs remain unverified. Since the backend migration files are not tracked in the public Git history, Git cannot establish which are applied. No existing migration was positively verified as unapplied, so none was edited.
