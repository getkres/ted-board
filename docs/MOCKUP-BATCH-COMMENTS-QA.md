# Batch comments QA, October 24, 2026

The final revision passed all 23 groups in `node qa/run.cjs`, with Google Chrome
on the Mac mini. The suite intercepted fixture endpoints, and the offline guard
blocked any unmatched external request. No live feedback or database write was
sent. A local Chrome-only preload selected `channel:'chrome'` for every browser
launch. Safari and bundled Chromium were not used.

The new tests are `qa/batch-comments.cjs` (10 cases) and
`backend-integration/mockup-batch-comments.test.ts` (2 cases). Initial UI cases
failed before implementation. Author review found that lexical timestamp sorting
misordered equivalent formats with timezone offsets; its regression failed,
then passed after comparing parsed instants. A poll held across a successful
Send also retains the acknowledged note.

Coverage includes exact project and batch isolation, separating image pins,
Ted's reply history, escaped HTML-like text, batch pin posting, positive receipt
acknowledgements, empty and unsupported Send, failure and malformed-response draft
retention, double-submit prevention, batch navigation, polling focus and caret,
identity reset, archived history, all three batch layouts, and preserved compact
viewer heights. Posting sends an ordinary pin payload with a batch marker and
never sends an approval, verdict, pick, or build action. This fixture check does
not prove the private worker's behavior. The existing Archive and Restore suite
remains green and provides the dismissal behavior from PR #42.

Before and after screenshots use 375x844 and 1440x900 viewports. Layout checks
found no horizontal overflow, clipped text, gradients, prohibited punctuation,
or page errors. The [review board](mockup-batch-comments-review/index.html) places
all six process sheets beside the screenshots, with the chosen composition,
value study, construction, color choices, and critique. Its images and responsive
layout were checked in Google Chrome at both widths. Data is synthetic.

Additional verification: 17 grant-guard regression tests, JavaScript syntax,
Deno checking of the server seam, and diff whitespace checks passed. The normal
migration scanner found zero future files in its three configured roots, so the
new `migrations/` proposal was checked directly with its offline SQL guard.
Read-only live checks found no marker column and no migration history row for
version `20261023020000` before the unapplied proposal was reduced.

`migrations/` is never automatically applied by this repository. The checked
workflows perform offline checks only. GitHub Pages reports a legacy static
source at `main`, path `/`. The frontend and workflows contain no migration
runner or database application command. The job's reduced `apply.sql` exits
unless Ted explicitly selects its backup, apply, or rollback phase.

Review was performed by the author; no independent worker was delegated. SQL was
not executed, and no private handler was deployed. Ted must review the draft,
integrate and verify the existing atomic feedback transaction and reply worker,
and apply the reduced prerequisite before enabling batch comment posting.
