# Isolated card reconciler

The authority for this revision is Ted's fresh PR 45 review on 2026-10-24. Its required approach replaces broad legacy-runner edits with separate managed modules and one guarded redirect per legacy file.

## Flag-off contract

Every captured legacy source is preserved byte for byte after removing its one marked redirect. The handler has one additional support import whose module has no startup effects. The baseline retains the Claude enqueue default, original section moves, 64-worker total, existing legacy lane worker budgets and load guard, and construction with empty or equal handler keys. Legacy lanes retain their existing capacity.json, including the 3x load cutoff and 4/16 account-2 worker budgets. Managed admission reads the separate reconciler-capacity.json. Invalid enable configuration warns and returns disabled, while explicit apply fails even when the enable environment override is true. A flag change requires restarting the existing processes during the operator's reviewed cutover.

## Managed ownership

A dedicated mini-only launchd entry invokes the deterministic planner and driver every two minutes. The legacy board-live entry does not invoke that loop. Watcher enqueue uses the managed Store when enabled, but does not own dispatch, approvals, or recovery. Managed heartbeat preserves the installed Live Ted health flow. Watchdog recovery is refused, and the steward becomes read-only. The hourly skill is unchanged. All modules and redirects install as one reviewed set after a legacy drain.

The ledger observes source cards, local sessions, approval packets, SQL packets, PR evidence, and approved mockup batches. Every valid item has one owner and a next-action deadline. Only Ted-owned rows enter the ranked Ted queue. The planner hashes external job IDs and clamps action starts to the observation time. The server quarantines malformed rows and queue references as safe coverage identifiers, preserving valid work.

## Dispatch and recovery

Initial automatic dispatch identity uses the card and its first enqueue generation. A session that has run is never dispatched again merely because updated_at changed. Automatic enqueue cannot reset retry history. Automatic starts, including retries, have a durable lifetime limit of three per card. Exhaustion creates one Ted hold, and new human requests survive. Unsafe side effects, approval execution, uncertain sends, and uncertain SQL work do not use generic automatic retry.

Running lease-less sessions block apply before any remote mutation. The packet never adopts or kills those legacy attempts. Managed wrappers renew a fenced 150-second lease every 30 seconds. Recovery from lease expiry requires three distinct missed-renewal observations, a dead matching PID, unchanged and nonrecent event and log mtimes, a fully absent process group, and current result and fence rechecks. A live PID or changing file activity prevents recovery regardless of lease age. Process probes, explicit stops, and waits occur outside the session lock. Only an explicit user stop can signal a matching process.

A pass attempts at most 3 retries, 5 Ted routes or holds, 5 card creations, 5 delivery advances or closures, 10 dispatch proposals, and 10 escalations, oldest first. Managed Store also limits total launch attempts to 10 and retry launches to 3. The first complete publication replaces all initial escalation proposals with one deterministic digest and atomically receipts every covered proposal. Partial observations cannot complete that first-run marker. Deferred work remains unreceipted and eligible later.

## Partial coverage and authority

A 500-card response, unavailable card feed, or malformed card row marks coverage partial. Confirmed local managed recovery and wrapper renewal continue, while remote ledger publication, new dispatch, routing, approval collection, archive, and outbox flush wait for complete card coverage. This preserves the last authoritative ledger. Detached sessions remain held for Ted. Other required-feed failures remain explicit and cannot certify health.

Sensitive original spending, personal-copy, and authentication scope cannot be cleared by a cosmetic operational update. Worker failures and exhausted retries do not create new Sebastian asks. They remain in Ted's recovery queue. The existing reserved-decision approval flow remains separate.

## Delivery and database

Merged GitHub evidence opens deployment work. A matching deployment receipt opens independent verification. A matching verified commit and current card revision, ordered timestamps, and settled workers are required before closure. Missing local artifacts retain the known delivery stage and create a defect. A PR, a merge, or a staged install is not live delivery evidence.

The private SQL creating packet is additive: new columns, a new ledger, and new worker-only functions. It does not update existing card data or timestamps. New nullable deadlines are initialized by the reviewed publisher from observed history. The table has explicit service_role CRUD, enabled RLS, and revoked public, anon, and authenticated access. Rollback removes only newly introduced schema. Ted must verify history, validate staging, create a real backup, authorize application, and verify live outcomes. Nothing was applied by the preparation job.

Reconciler-capacity.json applies only in managed mode. Legacy capacity.json is preserved unchanged. It retains 64 total, the twice-CPU load ceiling, two urgent reserved slots, independent base Opus 2 and Sonnet 8 worker limits, review exemption from model worker limits, and the memory guard. Verified, enabled account 2 selects configured 4/16 limits. Actual provider throughput and host stability still require Ted's soak. A single mini remains a host-failure boundary.

Managed worker-failure notes are retained in the durable Ted-only ted_outbox and included in jobs/ted-review-queue.json. They are never delivered to source-card replies, including when the source already has a genuine Needs you decision. Existing legacy failure notes in the delivery outbox are quarantined before flush. A verified failed managed result can use bounded recovery after confirmed process absence; the three-miss requirement applies specifically to lease-expiry recovery. Failed legacy attempts without a lease are held for Ted, and they are never automatically retried.

An already-loaded managed dispatcher or worker does not fall back into legacy execution if its flag is disabled or becomes invalid. It freezes lifecycle work until the reviewed restart. New processes started with the flag off use the untouched legacy implementation. Managed explicit-stop handling only queues a request; signalling occurs in the dedicated driver outside the session lock.
