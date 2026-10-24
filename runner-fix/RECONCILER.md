# Reconciler review and installation

Prepared changes, not installed software. The private SQL packet, production snapshot, exact dry-run actions, and REPORT.md stay in the card job directory. Ted must review the PR, validate the SQL against the live definitions and migration history, authorize the private cutover, and verify delivery before this card is done. No new routine is created.

## Review artifacts

- `docs/reconciler/RESEARCH.md`, `DESIGN.md`, and `PLAN.md` explain sources and engineering calls.
- `reconciler-core.patch`, `reconciler-runtime.patch`, `reconciler-admission.patch`, and `reconciler-inbox-policy.patch` create generic private runtime helpers. Existing runtime changes are narrow `reconciler-*.patch` files. No installed operational source is committed.
- `reconciliation-handler.patch` folds the worker-failure handler changes together with the authenticated ledger seam. Install `backend-integration/reconciliation.ts` next to the private handler, never as a replacement handler.
- `mockup-autoarchive.patch` is the exact helper from PR 41. Its independent enable flag remains off. The combined heartbeat patch runs its hook on the existing heartbeat in legacy mode, or in the sole reconciler pass in reconciler mode.
- The frozen failure-card policy, worker failure classification, one legacy retry, reaper, and steward fixes are folded into this bundle. Managed mode disables the legacy retry. Do not independently apply those older overlapping patches over this candidate.
- `reconciler-manifest.json` pins source and result hashes. The current baseline also preserves the installed Chrome-only rule, twelve-hour wrapper ceiling, and steward improvements discovered during integration. The shared failure policy supersedes the old steward's broad protection heuristic.

## Reconstruct without installation

Set these variables to existing private mini paths. `CANDIDATE` must be a new directory. These commands read sources and create an isolated candidate only.

```sh
umask 077
python3 runner-fix/reconstruct_reconciler.py \
  --baseline "$TED_BOARD_ROOT" \
  --output "$CANDIDATE" \
  --hourly-skill "$HOURLY_LEAD_SKILL" \
  --steward-source "$STEWARD_SOURCE"

RECONCILER_CANDIDATE="$CANDIDATE" python3 -m unittest discover -s runner-fix -p '*reconciler*test.py'
TED_RUNTIME_SOURCE="$CANDIDATE" python3 runner-fix/lease_dispatch_test.py
TED_RUNTIME_SOURCE="$CANDIDATE" python3 runner-fix/failure_routing_test.py
TED_RUNTIME_SOURCE="$CANDIDATE" python3 runner-fix/mockup_autoarchive_test.py
RECONCILIATION_HANDLER_SOURCE="$CANDIDATE/backend/handler.ts" node --test backend-integration/reconciliation.test.ts backend-integration/snapshots.test.ts
TED_RUNTIME_SOURCE="$CANDIDATE/backend" node --test runner-fix/failure_handler_test.ts
node --test tests/aging_wip_test.cjs
PLAYWRIGHT_MODULE="$EXISTING_PLAYWRIGHT" node tests/aging_wip_ui.cjs
python3 scripts/check_data_api_grants.py
python3 -m unittest discover -s tests -p 'test_data_api_grants.py'
```

The Chrome fixture uses installed Google Chrome. Core tests reconstruct the reviewed helper patches in a temporary directory, so uncommitted source cannot substitute for the published artifact. Private integration tests require the reconstructed candidate. Hash drift causes reconstruction to refuse before creating output. Rebase, test, and review a changed source rather than forcing a patch.

## Read-only proof

```sh
python3 "$CANDIDATE/reconciler_runtime.py" \
  --root "$TED_BOARD_ROOT" \
  --policy-source "$CANDIDATE/inbox_policy.py" \
  --dry-run --output "$PRIVATE_EVIDENCE/dry-run-live.json"
```

Default mode is dry-run. It uses board and mockup GETs, bounded GitHub CLI reads, and atomic local JSON reads. It does not construct Store, call heartbeat or controls, renew leases, publish the ledger, start workers, archive, send, or apply SQL. Output is private, mode 0600. Missing schema is an explicit coverage defect. A newly installed but unpublished schema is distinguishable and permits its first publish.

## Database plan, for Ted only

1. Read current migration history and definitions. The new packet asserts its objects and metadata columns do not exist, and expected card types match. It does not rewrite an applied migration. Record that review before assigning the new migration name.
2. In an authorized disposable database or staging environment, run the private `backup.sql`, `apply.sql`, and `rollback.sql` with stop-on-error enabled and a private umask. Verify schema rollback, grants, RLS, denied browser-role access, stale generation rejection, equal-generation replay, conflicting replay, source-card CAS, concurrent publications, deadline stability, and verified closure evidence. These SQL behaviors have static checks and adapter tests, but have not been database-executed by this card.
3. Back up production schema and all card rows using `backup.sql` before application. Protect the CSV and schema outputs as private data. `apply.sql` runs in one transaction; a schema assertion or CAS failure aborts it. Save the approved SQL and checksums as a new private migration only after history review.
4. Ted applies the approved packet, deploys the combined authenticated handler and seam, and checks Jobs GET. Before the first publication, `reconciliation_error` must be `not_published`, rather than `schema_unavailable`. Page keys must fail all reconciliation writes. Worker-only RPCs use service_role; RLS is enabled, and public, anon, and authenticated have no table or function privileges.
5. Rollback is separately authorized. Stop the reconciler first, preserve its state and new metadata as evidence, run the reviewed private rollback, and restore the saved pre-change schema and data if necessary. Never delete the whole cards table or overwrite later card content from the backup.

## Mini cutover, after review

1. Confirm the machine is the mini. Back up the installed runtime, current steward release, hourly skill, existing launchd plists, and sessions store into a private directory. Record the source hashes and current worker identities. Do not install a routine on the MacBook.
2. Use an explicit maintenance window to pause the existing dispatch producers, including board-jobs and the decisions watcher. Drain or checkpoint and stop old wrappers through existing guarded controls. Confirm no old running worker remains. Old workers lack leases and cannot be silently adopted. The first pre-migration dry-run deliberately reports them as lease defects.
3. Install the reconstructed helpers and patched sessions.py, session_worker.py, board_live.py, jobs_heartbeat.py, job_watchdog.py, live_status.py, and card.py together. Install the candidate steward using the existing versioned steward release process, and replace the hourly skill only after reviewing its diff. Keep private file modes. Do not apply PR 41 or the failure card's overlapping runtime patches a second time.
4. Keep the durable flag absent or false during validation. The existing board-live agent remains at 120 seconds; board-jobs remains at 30 seconds. Do not create another timer. Verify that the private handler and database contract are ready, rerun the candidate tests, and run another live dry-run.
5. Ted enables the reviewed mode by atomically writing `jobs/reconciler-config.json` with `{"enabled":true}` and mode 0600, then restarts the existing processes so old imported Python modules cannot survive cutover. The shared reader also accepts `TED_RECONCILER_ENABLED=true`. A malformed existing config fails closed. The decisions watcher can still enqueue, but Store.tick and approval collection require the reconciler's explicit argument before doing lifecycle work.
6. The existing board-live entry point calls `reconciler_runtime.py --apply`. A nonblocking run lock prevents overlapping passes. Heartbeat publishes health without dispatching. The old reaper is bypassed; watchdog enforcement refuses recovery; the steward becomes read-only. Archive writes require the separate reviewed `TED_MOCKUP_AUTOARCHIVE_ENABLED=true` gate and PR 41's authorization. Leave it off during the reconciler soak.
7. Observe at least 15 minutes: no duplicate worker or note, 30-second fenced renewals, 150-second expiry, stable deadlines across polls, two-minute pass completion, review queue freshness, clear partial-feed banners, bounded retries, retained user requests, and no operational failure entering needs_you. Repeat an offline simulated dead worker, expired lease, and retry exhaustion before enabling recovery for valuable work.

## Capacity and priority

The measured mini has 18 CPUs and 64 GiB RAM. Admission preserves the current ceiling of 16, reserves two slots for urgent work, lowers capacity to eight above load/CPU 1, pauses above 1.5, and pauses below 8 GiB reclaimable memory or on failed observation. The ordinary Claude family is capped at two, including Sonnet; review turns count as Claude. Caps are ceilings, not a provider-rate benchmark. Record throttles and actual peak memory during the soak before changing them.

Explicit structured priority wins. Unanswered latest Sebastian messages enter the urgent lane; a bounded launch/client-revenue text fallback enters the revenue lane. Ted can correct classification in private `jobs/priority-overrides.json`, for example `{"CARD":{"priority_class":"urgent","explicit_ask":true}}`. Age orders each lane. This classification is routing evidence, not proof of financial value.

## Delivery, review, and recovery

A PR URL proves a PR exists. Only authoritative GitHub merged-commit evidence advances delivery. `workflow.json` deployment receipts require `verified:true`, `deployed_at`, and the merged-commit `revision`. Independent verification requires `ok:true`, `verified_at`, the same `revision`, and the current source `card_revision` before automatic closure. Receipt time cannot precede merge or deployment, or be in the future. Active or failed workers hold closure for Ted. Missing evidence opens the next Ted obligation and its deadline; it never marks work live.

Ordinary recovery has two automatic retries, with exponential backoff and deterministic jitter. Result consumption wins over lease failure, but stale fenced results do not. Restart requires verified absence of the matching worker group. Orphan children or unavailable process observation hold the attempt for Ted. Review, send, spend, SQL execution, veto delivery, and uncertain side effects never auto-retry. Exhaustion creates a durable dead-letter hold and one Ted note, preserving newly queued requests.

Ted redrives only after fixing the cause:

```sh
python3 "$TED_BOARD_ROOT/reconciler_runtime.py" --apply --redrive CARD --reason 'the verified repair'
```

Side effects must return through their original approval flow. Review age is never refreshed by heartbeats. The hourly loop reads the ranked, card-deduplicated queue before its quiet gate, drains at least two, and continues through overdue reviews. The 2h and 12h escalations update that queue and a banner, not a note storm. Only an already classified reserved Sebastian decision can receive the 24h reminder, and this loop never creates a new Sebastian ask.

## Runtime rollback

Pause producers, drain managed workers, remove the durable enable flag and any true enable environment, and restore the private runtime, steward release, and hourly-skill backups as a single reviewed set. Restart the existing services. Keep SQLite receipts, sessions retry history, review queue, and SQL backups for diagnosis. Restore the old backend only with its matching schema plan. Verify a fresh board read and health publication before releasing the maintenance window.

The single mini remains a host-failure boundary. The Jobs view marks a stale reconciler unhealthy, but a power or network outage cannot page through that same failed host. Adding an independent monitor or purchased service is outside this patch and has not been authorized.

Final review refinements: matching results are rechecked under the session lock immediately before recovery. User stops remain durable and settle process absence without retrying the cancelled turn. Missing delivery files preserve the known stage and raise a coverage defect. An unavailable Jobs/ledger observation blocks publication, and classified card priorities are synchronized into existing session admission before dispatch. Coverage-only banners do not claim an invented twelve-hour delay.
