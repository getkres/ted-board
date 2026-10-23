# Mockup batch feedback: NEEDS TED REVIEW

The card worker stopped at Sebastian's database gate. This PR proposes only the
storage prerequisite. It does not implement or enable the UI, change the private
backend, deploy a function, or apply SQL.

Read-only catalog checks against the target project confirmed that the live
`ted_mockups.verdict` is text, its check accepts only `approved`, `needs_work`,
and `scrapped`, and `ted_mockup_pins` has no batch-scope marker. The local private
handler also permits only those three verdicts. Its existing `archive` action is
worker-only, changes status only, and has no five-second undo.

The proposal extends that check with `not_relevant` and adds one boolean,
`ted_mockup_pins.batch_note`, defaulting to false. It leaves existing pins and
threads intact. The pin's existing mockup identifies its project and batch, so
batch notes can reuse pin IDs, thread entries, receipts, and `mockup_reply.py`.
Multiple note threads can be displayed together for the same exact batch.

The migration refuses a changed verdict constraint or a pre-existing marker.
Reconcile newer schema work rather than widening or dropping constraints blindly.
The private job's `apply.sql` contains separate backup, apply, and rollback phases.
Only Ted may run them after review. Preserve the private backup outside Git.

## Work remaining after the gate

1. Implement a transaction for batch and individual dismissal. Resolve exact
   project and batch or mockup ID server-side, lock rows in stable ID order,
   store `not_relevant` and `archived`, and retain previous values and a shared
   five-second undo token. Undo must reject expired or superseded changes and
   restore previous status and verdict atomically. Retries must be idempotent.
   Dismissal must create zero `ted_decisions` rows and zero build cards. Do not
   route it through approval, scrap, or the legacy worker-only archive action.
2. Implement batch-note posting through the authenticated existing pin and reply
   path. Select a valid anchor inside the exact project and batch, store
   `batch_note=true`, preserve rate limits, deduplicate retries, and issue the
   existing ordinary feedback receipt with explicit whole-batch context. Confirm
   that the private worker delivers it to Ted or the originating card and that
   `mockup_reply.py` replies to the same pin thread. Suppress these pins from
   image overlays and include their history in the batch thread.
3. Advertise separate capabilities only after both server transactions and
   routing are tested. The column alone must never advertise feature support.
4. Add batch dismissal next to whole-batch Good to go, immediate optimistic
   removal, a five-second undo, and failure restoration. Add the viewer verdict
   without increasing the compact header merged in PR #32. Put the batch
   textarea, Send button, and short conversation under its verdict buttons.
   Preserve drafts, focus, and identity isolation across polling and key changes.
5. Run QA for dismissal, undo, undo expiry and conflicts, per-image dismissal,
   batch-note posting and retries, thread display with Ted replies, and zero
   build-card creation. Capture before and after screenshots at 390x844 and
   1440x900. Keep existing type and colors, use flat fills, and use no gradients.

PR #32 is already merged. This branch starts from `origin/main` at `d2970d0`,
which includes that compact header. PR #34 owns the nearby mobile Decide work;
this proposal changes no frontend files and has no overlapping implementation.

The feature remains blocked until Ted reviews the SQL and the remaining
implementation and verification are completed. This PR is not ready to merge
as the completed card.
