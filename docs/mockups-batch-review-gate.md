# Not relevant anymore and batch comments: NEEDS TED REVIEW

PR #35 uses Sebastian's exact **Not relevant anymore** label for the batch-level
controls, including batch covers. It reuses PR #42's Archive action, immediate
removal, five-second Undo, and Restore. No reason, verdict, decision receipt, or
build card is created by dismissal. Image Archive controls and PR #32's compact
viewer stay intact. This branch includes merged PR #42 at `6eed5cd`.

## Private rollout and conversation

The entire batch conversation and composer render only when authenticated GET
returns `capabilities.batch_comments:true`. The old flat flag is ignored. Held
rollouts show no composer or dead Send button. Existing session drafts survive a
capability change. Enabled batch, round, and compare pages show the conversation
under their controls, and archived batches retain read-only history.

Send uses `{action:'pin',mockup_id,batch_note:true,text}` on the existing feedback
endpoint. `handleMockupBatchNote` now intercepts the private handler before
`actionArgs` validates ordinary image pins. Invalid markers cannot fall through.
The adapter calls `ted_mockup_batch_note`, a proposed transactional wrapper around
the existing `ted_mockup_act` RPC. It commits the marker and a receipt labeled
`Feedback scope: whole-batch` together, using the same `page='mockups'`,
`choice='pin'`, and pin ID that the current watcher and reply CLI consume.

The private handler candidate is wired in this job's isolated worktree at
`mockups-backend/supabase/functions/ted-mockups/handler.ts`. Full private backend
and worker source remain local, per repository instructions. This public PR
carries the exact scoped changes in
`backend-integration/mockup-batch-handler.patch` and
`backend-integration/mockup-batch-worker.patch`, plus the reusable server module.
The worker patch preserves whole-batch scope when the anchor is approved art;
it does not reopen art, authorize changes to final art, or approve a build.

No handler or worker was deployed. Ted's private rollout must copy the reviewed
server module beside the handler and apply the handler patch in the private
board checkout. Apply the worker patch from the private `ted-ops` root. Both
patches have been checked against the local baselines. Review the SQL and deploy
the matching private code together; no routine is created by this change.

## Proposed SQL, backup, and rollback

Read-only checks confirmed the marker, migration history row, and batch RPC are
absent before revising this unapplied proposal. It adds:

- `ted_mockup_pins.batch_note boolean not null default false`.
- A 1200-character check for Sebastian's batch messages, with a small immutable
  JSON helper. Ted's existing 2000-character reply allowance remains.
- A service-role-only batch pin RPC that wraps the existing pin transaction,
  retaining anchor locks, archive checks, rate limits, and the worker receipt.

Existing table RLS and grants, the ordinary pin RPC, verdicts, and build actions
remain unchanged. The migration fails safely on a pre-existing batch schema.
The job's `apply.sql` contains the exact proposal and explicit backup, apply,
and rollback phases. It exits by default. The private backup snapshots pins and
records that the new functions were absent. Rollback refuses to discard batch
notes, drops the new wrapper, check, helper, and column in dependency order, and
preserves the backup. Ted reviews and applies it. Nothing was applied to Supabase.

**`migrations/` is never auto-applied to Supabase.** Workflows run offline
checks only, the grant checker reads SQL as text, and Pages is a legacy static
source from `main`, path `/`. No frontend or workflow invokes a migration runner.
This covers the checked repository and Pages configuration, not external jobs.

## Review evidence

The [offline review board](mockup-batch-comments-review/index.html) places the
process strip beside the synthetic finals, including the enabled and held
rollout states. Before and after screenshots include 375x844, 390x844, and
1440x900. No design batch was uploaded to live Mockups under the database gate.

Chrome tests cover exact wording, one-tap archive and Undo, hidden composers,
thread isolation, escaped text, posting acknowledgements, polling, session
drafts, key reset, and read-marker writes only when changed. Private integration
tests use isolated local PostgreSQL and the actual handler and watcher candidates:
image and batch notes reach the same temporary queue, whole-batch labels survive,
approved anchors retain their review state, 1201-character notes fail, Ted's
reply limit remains, and guarded rollback preserves data. Test transports and
queues are isolated, and no live send or database write occurs.

The PR remains blocked for Ted review, SQL application, and private deployment.
