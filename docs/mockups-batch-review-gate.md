# Batch comments: NEEDS TED REVIEW

PR #35 now contains the batch conversation UI and its reduced storage proposal.
Merged PR #42 supplies Archive, five-second Undo, and Restore at batch and image
level. This PR adds no dismissal verdict, archive action, or build approval.
It builds on `origin/main` at `6eed5cd`, including PR #42 and the compact header
from PR #32.

## UI and request path

Batch, round, and version-compare pages show the conversation and composer below
their batch controls. The existing type, colors, and flat fills remain. Archived
batches show their history and require Restore before posting. Notes are filtered
by the anchor mockup's exact project and batch, including archived anchors in a
partially active batch. Image pins stay separate from batch history.

Send uses the existing feedback endpoint and pin action:
`{action:'pin',mockup_id,batch_note:true,text}`. The selected anchor belongs to
the displayed batch. A confirmed response must include the same mockup ID, a
marked pin with the saved text in its thread, and a positive feedback receipt ID.
Only then does the UI clear the draft and say Sent to Ted. A failed or malformed
response keeps the draft and asks for refresh before resending. There is no
automatic retry. Drafts survive ordinary polling and batch navigation within the
current access-key session, and polling preserves the textarea focus and caret.
Access-key reset clears drafts and rejects late responses.

`batch_comments_enabled:true` is required to send. Missing support keeps the
composer available for a local draft and leaves Send disabled. Column existence
alone must never advertise support. `backend-integration/mockup-batch-comments.ts`
is an authenticated server seam with an explicit durable store hook, not a
replacement or deployment of the private backend. See the private integration
requirements in `backend-integration/README.md`.

## Reduced SQL and manual gate

The only schema change is `ted_mockup_pins.batch_note boolean not null default
false`. Existing pins, threads, reply IDs, RLS, and service-role grants remain.
The migration refuses a pre-existing marker. Read-only checks on October 24 found
that the marker is absent and version `20261023020000` is absent from
`supabase_migrations.schema_migrations`, so this is an unapplied proposal.

The private card job contains `apply.sql` with opt-in backup, apply, and rollback
phases. It exits by default. The backup snapshots pins in a private schema.
Rollback refuses to discard any batch notes and preserves its backup. Ted must
hold application until the UI, private receipt transaction, and routing are
reviewed together. This worker applies no SQL.

**`migrations/` is never auto-applied by this repository.** At this revision the
only workflows run offline Python checks. The grant checker reads SQL as text;
it has no database connection or execution path. GitHub Pages is configured as a
legacy static deployment from `main`, path `/`. Neither the frontend nor a
workflow invokes a migration runner, Supabase db push, or psql. SQL files here
are inert proposals; Ted applies reviewed SQL separately. This is a statement
about the checked repository and Pages configuration, not unknown external jobs.

## Review artifacts and remaining rollout

The [offline review board](mockup-batch-comments-review/index.html) places the
master copies, eight thumbnails, notan, construction, color studies, and clean
drawing next to the synthetic final screenshots. Its Notes card records the
value-grouping technique and critique. Nothing was uploaded to live Mockups.

Offline Chrome QA covers sending, history with Ted replies, exact scope, HTML-like
text, failed and malformed acknowledgements, capability gating, polling, drafts,
identity reset, archived history, every batch layout, and 375- and 1440-pixel
screens. Existing Archive and Restore tests remain in the full suite. Fixture
requests confirm that posting comments does not invoke approval or build actions.
That is not a substitute for private worker and receipt verification.

Before live delivery, Ted must review this draft, integrate the marker into the
existing atomic pin and feedback receipt transaction, verify the ordinary pin
routing and `mockup_reply.py` reply path, apply the reduced SQL with backup, and
deploy the private handler. Enable the capability only after those checks pass.
Do not treat merging static UI or applying the column alone as feature delivery.
