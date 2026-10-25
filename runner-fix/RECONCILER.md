# PR 45 isolated reconciler handoff

Prepared for Ted re-review. Nothing is installed, enabled, deployed, or database-applied. The specification for this revision is PR45-REVIEW-1024.md in the private job directory. This document supersedes the earlier combined-runner cutover instructions.

## Isolation boundary

The manifest pins the current legacy source bytes, and the separate baseline-dependency manifest pins the installed inbox policy plus both failure-template copies. Any drift requires a fresh reconstruction and review. The managed policy preserves the current exact runner-provenance rules and adds only the separate conservative managed hold classifier. The managed Claude lane helper is the exact new-module artifact from the landed standalone lane bundle.

The managed implementation lives in reconstructed `reconciler_sessions.py`, `reconciler_worker.py`, `reconciler_status.py`, `reconciler_card.py`, `reconciler_heartbeat.py`, `reconciler_handler.ts`, the pure planner, and the driver. Source-derived modules are reconstructed from pinned private sources and reviewed patches. They are never installed in place of the legacy implementations.

Each legacy file receives one marked guarded redirect. Removing that block restores every original source byte. The TypeScript handler also has one side-effect-free support import. Flag off retains the existing `claude` enqueue default, section moves, 64 total workers, existing legacy lane capacity and model limits, current load guard, and handler construction with empty or equal keys. It retains the existing capacity.json for legacy lanes, including its 3x load cutoff and 4/16 account-2 limits. Managed admission reads the separate reconciler-capacity.json file, with its independent 2x cutoff and capacity schema. Invalid enable configuration prints a fixed warning, returns disabled to legacy callers, and blocks explicit apply, including when the enable environment override is true.

The dedicated `co.ted.card-reconciler` launchd entry owns reconciliation at 120 seconds. The old board-live entry returns without lifecycle work in managed mode. Jobs heartbeat redirects to the isolated health publisher, with the installed Live Ted health behavior preserved. Watcher calls can enqueue through the managed Store but cannot dispatch or collect approvals. Watchdog recovery is refused, and the steward is read-only. No new routine has been installed by this job.

## Reconstruct and verify before installation

Run from the reviewed public worktree on the mini. Choose a new private output path. The steward source must identify the current installed release, not the older release from a prior handoff.

```sh
umask 077
python3 runner-fix/reconstruct_reconciler.py \
  --baseline "$TED_BOARD_ROOT" --output "$CANDIDATE" \
  --hourly-skill "$HOURLY_LEAD_SKILL" --steward-source "$STEWARD_SOURCE"

CI=true RECONCILER_CANDIDATE="$CANDIDATE" python3 -m unittest discover -s runner-fix -p '*reconciler*test.py'
TED_RUNTIME_SOURCE="$CANDIDATE" python3 runner-fix/lease_dispatch_test.py
TED_RUNTIME_SOURCE="$CANDIDATE" python3 runner-fix/managed_failure_routing_test.py
PYTHONPATH="$CANDIDATE${PYTHONPATH:+:$PYTHONPATH}" TED_RUNTIME_SOURCE="$CANDIDATE" python3 runner-fix/mockup_autoarchive_test.py
TED_RECONCILER_ENABLED=true RECONCILIATION_HANDLER_SOURCE="$CANDIDATE/backend/handler.ts" TED_RUNTIME_SOURCE="$CANDIDATE/backend" deno test --no-check --allow-read --allow-env backend-integration/reconciliation.test.ts backend-integration/snapshots.test.ts runner-fix/failure_handler_test.ts
deno check backend-integration/reconciliation.ts backend-integration/snapshots.ts "$CANDIDATE/backend/reconciler_handler.ts"
node --test tests/aging_wip_test.cjs
python3 scripts/check_data_api_grants.py
python3 scripts/check_data_api_grants.py --root "$TED_BOARD_ROOT"
python3 -m unittest discover -s tests -p 'test_data_api_grants.py'
```

The current installed legacy handler has two pre-existing TypeScript errors at the runner-failure `Object.hasOwn` calls, where parsed values have type unknown. The wrapper preserves those exact source bytes when the support import and route are removed, so its legacy branch retains that upstream typing limitation. The isolated managed handler adds explicit string guards and passes `deno check`; the wrapper is exercised by the offline `--no-check` tests. Do not claim the inherited legacy wrapper passes type checking.

`legacy-baseline/` and `backend/legacy-handler-baseline.ts` are private test fixtures in the candidate. Do not deploy those fixtures. A missing RECONCILER_CANDIDATE fails the private CI suite. Public CI explicitly runs only the planner, runtime, review regressions, and packaging tests that it can reconstruct without installed private sources.

Read-only proof, with no Store construction or lifecycle mutation:

```sh
python3 "$CANDIDATE/reconciler_runtime.py" --root "$TED_BOARD_ROOT" \
  --policy-source "$CANDIDATE/inbox_policy.py" --dry-run \
  --output "$PRIVATE_EVIDENCE/dry-run.json"
```

## Database packet, for Ted only

Review the private `SQL-REVIEW-1024.md`, `apply.sql`, `backup.sql`, `rollback.sql`, and the three exact diffs under `sql-review-1024/`. The creating packet is additive and does not backfill or update existing card rows. It adds nullable deadline metadata and new worker-only ledger functions. RLS is enabled, service_role CRUD is explicit, and browser roles have no grants. The publisher initializes new metadata from observed history after cutover.

Ted must verify current migration history and definitions, validate transactions, concurrent CAS, role denial, and rollback in authorized staging, and create an actual protected backup before production application. A prepared backup procedure is not an actual backup. Do not rewrite an applied migration. This job executed no SQL or migration.

The backend handler redirect has its own opt-in environment flag, `TED_RECONCILER_ENABLED=true`. Flag off preserves the exact legacy route and permits empty or equal key construction, while ordinary legacy authorization remains unchanged. Flag on requires separate nonempty page and worker credentials before activating the authenticated reconciliation seam. Deploy the wrapper, isolated handler, reconciliation.ts, and existing backend siblings together through Ted's reviewed release process. No credentials belong in this bundle or its logs.

## Mini cutover, only after review and separate authorization

1. Confirm the host is the mini. Record the reviewed commit. Back up every installed file named in the reconstruction manifest, existing capacity and enable files, the current steward release, launchd plists, and the sessions ledger into a private timestamped directory. Preserve file modes and dedicated Claude account affinity. Do not use old cap-3 or cap-16 backups as the rollback baseline.
2. Start with the empty dispatch allowlist. Initial automatic starts require an exact card ID in dispatch.allow_card_ids. The dispatch.hold_card_ids list and metadata.reconciler_hold=true override permission, including queued automatic retries. Missing policy defaults to no first starts, and invalid policy holds all automatic work. A running direct card or active external job blocks a new start even when allowlisted. The planner, pre-enqueue adapter, and automatic first-turn spawn all recheck these gates. Existing explicit human queues remain separate. Inspect the fresh dry-run, which must propose zero first starts with the initial empty list, then opt in individual future cards only after checking current worker ownership. Pause the existing dispatch producers and settle all legacy attempts through the existing operator controls. Running or unsettled lease-less sessions block `--apply` before any remote mutation. A dead PID with a still-running ledger row still requires Ted to review and settle that old attempt. Do not call Store.tick() merely to drain, because the legacy method can start queued work. This packet does not adopt, kill, or retry legacy lease-less workers.
3. Reconstruct again against the current live hashes and repeat the offline checks. Refuse drift. Install the manifest's reviewed legacy redirects and isolated modules as one set while producers remain paused. Install the candidate backend files through the separate authorized deployment process. Leave the hourly skill unchanged. Do not stack earlier PR 40, PR 41, failure-routing, or old PR 45 runtime patches over this bundle.
4. Keep the local enable flag false during flag-off verification. Verify the legacy source comparison, default engine, section moves, model caps, missing-capacity behavior, and empty-key handler behavior again. Capacity and managed imports must have no effect on legacy operation.
5. Render `runner-fix/reconciler-launchd.plist` by replacing `__TED_BOARD_ROOT__` with the absolute private mini runtime path and `__TED_HOME__` with the mini operator home directory. Its explicit PATH must resolve gh before bootstrap. Validate the rendered plist with `plutil -lint`. Ted installs it as `~/Library/LaunchAgents/co.ted.card-reconciler.plist` on the mini only. It is a new dedicated entry, not a second lifecycle invocation from board-live. Do not bootstrap it before the database, backend, legacy drain, and local configuration checks are ready.
6. Ted enables the backend flag and atomically writes the reviewed local `jobs/reconciler-config.json` containing `{"enabled":true,"dispatch":{"allow_card_ids":[],"hold_card_ids":[]}}`, with mode 0600. Restart the existing processes so imported legacy functions cannot survive the flag change. Bootstrap the dedicated reconciler entry through the normal operator controls. Keep the independent archive flag off and preserve the existing Claude lane flag. In managed mode, the dedicated reconciler is also the sole archive caller. A later archive enablement must set that independent flag in the dedicated reconciler environment, with the legacy heartbeat archive flag off; setting only the old heartbeat environment has no managed effect. Lane activation is a separate Ted action.
7. Observe at least 15 minutes, plus the documented capacity soak: one loop owner, no duplicate starts or notes, unchanged legacy behavior when off, bounded first-run digest, 30-second renewals, no live-PID expiry kills, three distinct missed observations before recovery, stable deadlines, partial-feed warnings, and matching deployment and verification receipts. Verify actual live outcomes before closing the card.

## Managed safety behavior

Capacity.json applies only to the managed path. It retains 64 total, load above twice CPU count as the stop threshold, separate base Opus 2 and Sonnet 8 worker limits, two urgent reserved slots, and the memory guard. Reviews are exempt from model worker caps, and they still consume global capacity. Enabled, verified account 2 selects the configured 4/16 worker limits. Missing capacity blocks managed admission and leaves legacy behavior intact.

A pass attempts at most 3 retries, 5 Ted routes or recovery holds, 5 card creations, 5 delivery advances or closures, 10 dispatch proposals, and 10 escalations, oldest first. Managed starts are also limited to 10 total and 3 retries. Initial escalation proposals become one deterministic ranked digest with atomic covered receipts. Partial card feeds cannot mark that initial digest complete. Limited or failed work retains no success receipt.

Initial dispatch identity uses the card and its first enqueue generation. A session that has run is never automatically dispatched again because a card's updated_at changed. Automatic enqueue preserves retry history. Automatic starts have a per-card lifetime budget of three, including retries; exhaustion dead-letters to Ted, with new human requests retained. Explicit Ted redrive remains a separate repair action, and unsafe side effects retain their original approval flow.

A lease-less running session blocks apply. Expiry alone never signals a process. Recovery from lease expiry requires three distinct missed-renewal observations, a dead matching PID, unchanged and nonrecent event and log mtimes, an absent process group, and rechecks of the current fence and result. Probes, signals, and waits run outside the session lock. Only an explicit user stop can signal a matching process, and lease renewal can continue during that operation.

A 500-card response, malformed card row, or unavailable card feed marks coverage partial. The loop continues bounded confirmed local recovery and wrapper renewal. It skips remote ledger publication, remote routing, new dispatch, approval collection, archive, and outbox flush until the card feed is complete. Detached work remains held for Ted. The browser shows the last authoritative ledger as stale instead of accepting a partial replacement.

Malformed ledger rows and invalid queue references are quarantined as safe coverage identifiers. Valid rows remain publishable. Only Ted-owned rows enter ted_queue, external job IDs are hashed, and action start dates cannot exceed the observation time. Worker failures, unsafe artifacts, exhausted retries, and uncertain side effects do not create a Needs you transition. Personal copy, spending, and authentication holds remain documented in the private routing review.

## Rollback

Ted pauses producers, settles every acknowledged stop request while the dedicated reconciler is still available, drains or reviews managed attempts, and preserves receipts, health observations, queues, and new metadata. Before disabling managed mode, confirm no `stop_requested` row remains and no dead-lettered row carries an automatically executable queue. Preserve newer human requests separately for operator review, rather than allowing legacy dispatch to start them during rollback. Stop the dedicated reconciler entry after that drain. Disable both opt-in flags, restore the freshly backed-up legacy files, steward release, prior backend, capacity and enable files, and existing plists as a reviewed set, and restart only the services that were paused. Do not overwrite a ledger that has processed newer turns with a stale backup. Dedicated Claude conversations cannot be moved to another account as part of rollback. Database rollback is separately authorized and uses the private reviewed packet after exporting any new metadata that must be retained.

The mini remains a single-host failure boundary. No independent paid monitor was created. A stale browser ledger is a warning, not proof of live delivery.

Managed worker-failure notes are retained in the durable Ted-only ted_outbox and included in jobs/ted-review-queue.json. They are never delivered to source-card replies, including when the source already has a genuine Needs you decision. Existing legacy failure notes in the delivery outbox are quarantined before flush. A verified failed managed result can use bounded recovery after confirmed process absence; the three-miss requirement applies specifically to lease-expiry recovery. Failed legacy attempts without a lease are held for Ted, and they are never automatically retried.

An already-loaded managed dispatcher or worker does not fall back into legacy execution if its flag is disabled or becomes invalid. It freezes lifecycle work until the reviewed restart. New processes started with the flag off use the untouched legacy implementation. Managed explicit-stop handling only queues a request; signalling occurs in the dedicated driver outside the session lock.

## Explicit settlement of dead-lettered reviews

An uncertain approval keeps its reviewing slot until Ted verifies the actual external outcome. No automatic path marks that action done or retries its effects. After confirming the outcome, the mini operator can settle the exact dead-lettered approval locally:

```sh
python3 "$TED_BOARD_ROOT/reconciler_runtime.py" --root "$TED_BOARD_ROOT" --apply \
  --settle-review CARD_ID --approval-id APPROVAL_ID --review-outcome failed \
  --reason 'verified that the approved action did not complete'
```

Use outcome done only after verifying the exact approved effect completed. The command requires managed enablement, the exact current dead-lettered review identity, and confirmed absence of the original matching process and process group. It never signals a process or executes the approved action. It records Ted's outcome, releases only that approval slot, clears review and active-turn metadata, and preserves dedicated lane affinity. A failed outcome remains dead-lettered until a separate explicit redrive or fresh approval. A live reviewer, changed turn, stale approval ID, missing lease identity, or unavailable process observation refuses settlement. The operator reason and settlement receipt remain private.

## Final integration baseline and route fencing

Reconstruction now requires the separately reviewed legacy admission pause helper and the current lane runtime. The sessions.py wrapper retains both post-result pause guards, and removing its marked reconciler route restores every byte of that reviewed baseline. The session_worker.py wrapper likewise preserves current dedicated-session routing. The managed lane helper is pinned to the current installed helper, including dedicated-session identity and fallback rules. Do not overwrite a newer live source with these captured bytes; any hash mismatch requires regeneration and review.

For a legacy drain, preserve and briefly quiesce both co.ted.board-jobs and co.ted.decisions during source installation. The decisions watch imports board_route, whose dispatch calls Store.tick. Install the pause dependency before sessions.py, confirm no old imported heartbeat, watch.py, or direct card caller remains, and activate the marker under the shared ledger lock with an exact prior-state backup. Restore the original producer loaded and disabled states while admission remains paused so valid results settle. The separate Fresh Ted conversation rollover is outside the card Store. Restore the original marker state before a blocked cutover handoff; never restore an old session ledger or adopt a live lease-less worker.

Operational Needs you routing now sends expected_revision and the exact observed messages array as well as expected_updated_at and expected_section. The backend requires a positive safe integer revision and a messages array, then forwards p_expected_revision and p_expected_messages to the six-argument route RPC. The planner holds protected decision kinds, waiting_on_you cards, and known active approvals or vetoes. SQL rechecks those protections and all four observation guards under its card lock, including separately inserted approval and veto rows. Verified closure also carries the exact planned positive safe expected_revision and timestamp, so a metadata revision change cannot close stale evidence even when updated_at is preserved. Its RPC now has three arguments. Active approval and veto protection uses explicit terminal-state allowlists; unknown future states stay held. The privately reviewed SQL packet and this backend contract must deploy together.

A dead-lettered or stopped review is never recollected automatically, and a requested stop also prevents artifact recollection. Unsafe artifacts retain human requests while discarding automatic and retry queue items. The explicit review-settlement command remains required to release an uncertain review. When another pass holds the reconciler lock, operator settlement and redrive commands return nonzero with a fixed refusal, and the normal loop may skip quietly. Spawn-time first-dispatch checks hold external running, untracked, queued, and waiting-approval rows while excluding only the matching queued local heartbeat row. A running, untracked, or waiting-approval matching-ID row still holds a first spawn.

The planner protects real card pending-control fields already used by inbox_policy: pending_approval, approval_pending, pending_decision, veto_pending, pending_approval_kinds, and nested approval or veto status objects. Unknown nested statuses hold. An optional snapshot veto list is also conservative input, but observe does not fetch a separate veto feed; private SQL rechecks every database control row under the card lock. Preserve live capacity.json on install and rollback. Only reconciler-capacity.json is delivered by the managed manifest. The live legacy capacity file is a pinned unchanged dependency.
