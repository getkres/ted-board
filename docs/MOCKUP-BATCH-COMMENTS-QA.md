# Not relevant anymore and batch comments QA, October 24, 2026

The final complete `qa/run.cjs` run passed all 24 verification groups in Google
Chrome on the Mac mini. Browser fixture routes and the offline network guard
prevented live requests. SQL tests used isolated in-memory PGlite PostgreSQL,
and watcher tests used fake transports and temporary queue files. No SQL was
applied to Supabase, and no live feedback was sent.

## Review fixes covered

- Batch covers and every batch layout use the exact Not relevant anymore label.
  Existing Archive tests verify immediate hiding, five-second Undo, one archive
  request, Restore, failures, identity isolation, and no verdict or build action.
  Dismissal asks for no reason.
- The complete composer is absent unless GET returns
  `capabilities.batch_comments:true`, even when the old flat flag is true.
  Rollout changes preserve existing session drafts. Enabled conversations remain
  isolated by exact project and batch, and archived history stays read-only.
- The actual private handler candidate intercepts marked batch pins before image
  coordinate validation. Its adapter calls the proposed atomic wrapper of the
  existing pin RPC. Invalid markers and missing SQL cannot become image pins.
- Image and batch notes produce real local mockups/pin receipts. The actual
  watcher candidate routes both into one temporary design queue, where the batch
  note is labeled `Feedback scope: whole-batch` and replies use its same pin ID.
  A regression reproduced the approved-anchor scope bug; the worker patch now
  preserves a batch-level note without changing art status or approving a build.
- Repeated polling does not rewrite unchanged Ted read markers. A new Ted reply
  causes one marker write.
- The proposed SQL check rejects a 1201-character Sebastian batch message while
  preserving Ted's existing 2000-character reply allowance. Local SQL tests also
  cover service-role-only function access, rate-limit rollback, missing capability
  probes, and a manual rollback that refuses to lose notes and retains its backup.

New coverage comprises 12 browser cases, 2 seam cases, and 8 private integration
cases. The private group explicitly skips in public clones without the required
private sources, fixture, apply.sql, and PGlite configuration. In the recorded
final run it executed all 8 cases, with zero skips. The handler and worker patches
were applied to temporary baseline copies and reproduced the private candidates.
The canonical server module matches the private candidate copy, and Deno and
Python checks passed.

Before and after screenshots include 375x844, 390x844, and 1440x900. Enabled and
held-rollout screenshots, compact viewer screenshots, and the process strip are
on the [offline review board](mockup-batch-comments-review/index.html). Layout
checks found no horizontal overflow, clipped text, gradients, prohibited
punctuation, or page errors. The board's images and layout were checked in Google
Chrome at 375 and 1440 pixels. All data is synthetic; no live upload occurred.

All 17 grant-guard regression tests passed, and the proposal passed the offline
SQL guard directly. The standard guard scans three other configured migration
roots, so its zero-file result is not counted as coverage of this proposal.
Whitespace, new-file punctuation, JavaScript syntax, and private-handler type
checks passed. The current proposal matches the apply phase in the job's SQL.

An earlier parallel browser run had a Chrome launch termination. An initial full
run also failed the existing pin-placement assertion in `qa/markup.cjs`. The
unchanged markup check passed by itself, and the final complete run then passed
all 24 groups. No markup production code or assertion was changed to mask it.
Both earlier failures remain in the private job evidence.

`migrations/` is not automatically applied to Supabase. Repository workflows run
offline Python checks, and Pages uses a legacy static source from `main`, path
`/`. Explicit local SQL tests use disposable memory only. The job's `apply.sql`
exits unless Ted selects backup, apply, or rollback manually.

Author review only, with no independent worker delegated. The PR is still held
for Ted's SQL review and private deployment. Full private handler and watcher
source remain local; the public PR contains the reusable adapter and scoped
rollout patches. No new routine, merge, or private deployment was performed.
