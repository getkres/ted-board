# Card reconciler implementation plan

Goal: make stalled work observable and recoverable through one durable reconciliation loop.
Architecture: pure snapshot planner, durable action journal, fenced session leases, private backend ledger, and authenticated Jobs view.
Tech stack: Python standard library, TypeScript, existing Supabase Edge Function, PostgreSQL, and static JavaScript.
Spec: DESIGN.md and the user's card brief.

Global constraints: no production application, no installation before Ted review, no spending, no sends, no em dash, Oxford comma, and mini-only routines.

Review focus: partial feeds must not erase work; leases must fence duplicate workers; side effects must never auto-retry; polling must not reset age; schema or handler absence must not look healthy.

1. Reconciliation core and durable driver
   - Write failing unit tests for owner and deadline defects, 2h/12h/24h escalation, dead-worker simulation, expired leases, bounded retry and dead-letter, redrive, priority, idempotent action replay, and approved-to-verified evidence.
   - Implement runner-fix/reconciler.py and runner-fix/reconciler_runtime.py with default dry-run, snapshot inputs, SQLite action receipts, and explicit enabled apply mode.
   - Verify with python3 -m unittest discover -s runner-fix -p '*reconciler*test.py'.
2. Private runner integration
   - Write lease and dispatch tests before modifying candidate copies. Add fenced 30-second lease renewal, consume results before expiry, priority admission, urgent reserve, and a single recovery owner.
   - Generate narrowly scoped patches against recorded private baselines. Preserve the archive hook and coordinate failure-routing dependencies.
   - Test patch reconstruction and candidate Store behavior in temporary directories with transports and subprocesses stubbed.
3. Backend and board
   - Prepare private apply.sql, backup.sql, and rollback.sql, with explicit grants, RLS, safe ownership defaults, and an authenticated worker-only publish contract.
   - Add a tested private handler integration patch and an aging Jobs view. Public repository gets only generic frontend, integration code, tests, patches, and documentation.
   - Run grants checks, backend tests, and relevant UI checks.
4. Evidence and handoff
   - Read the live feeds without calling heartbeat, controls, dispatcher ticks, archive, or writes. Run the candidate in dry-run, record action counts and exact local action list, and report any unavailable feed.
   - Obtain fresh review, fix meaningful findings with regression tests, rerun verification, create the PR, and write mini install, migration, soak, rollback, and Ted-review instructions.
   - Keep final state blocked while PR review, migration, or installation remains pending.
