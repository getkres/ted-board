# Apply the four approved Control workflows

Prepared on 2026-10-19. This branch is a handoff. No production SQL, Edge Function, static page, or worker change has been applied.

## What is in the handoff

- Public branch: `feat/control-center-workflows` from `main`. It contains `index.html`, `cave.css`, `control-center.js`, `control-center.css`, `README.md`, and this document.
- Private bundle: `private-handoff/control-center-private.tar.gz` in the local worktree. It contains the payload files listed in `MANIFEST.sha256`: the SQL migration, the `ted-board` Edge Function, worker changes, private decision watcher changes, and focused tests. The bundle is deliberately absent from the public Git branch. SHA-256: `12e40fadb36182b7724e54975ea7791c03228eb7985e6f65d90143e768db2143`.
- Migration: `ted-board/supabase/migrations/20261019190000_control_center_workflows.sql` inside the bundle.
- Public source snapshots `ted-board/index.html` and `ted-board/control-center.js` are also included in the private bundle for review and tests. Publish the merged public branch, preserving pod and approval changes, rather than installing those whole snapshots.
- Screenshot set: `shots/control-center/`, with Veto, Rules, Sprint, and Batches at 375px and 1440px.
- Test log: `out/control-center-tests.txt`.

The existing 30-second `co.ted.board-jobs` heartbeat clears due vetoes, and the existing `co.ted.decisions` watcher routes clearance receipts. No new scheduled routine is needed. Keep both on the Mac mini.

## Apply on the Mac mini

1. Review this branch, the migration, the private bundle, and the test log. Back up the existing `ted_board_cards` and `ted_decisions` tables, the Edge Function, and the private worker files. Preserve the current watcher ledgers and job directories.
2. Copy `private-handoff/control-center-private.tar.gz` to the Mac mini and unpack it into a staging directory. Verify its SHA-256 against the value supplied with this handoff. Keep the staged files private.

   ```sh
   mkdir -p ~/ted-ops/control-center-stage
   tar -xzf ~/ted-ops/control-center-private.tar.gz -C ~/ted-ops/control-center-stage
   cd ~/ted-ops/control-center-stage
   shasum -a 256 -c MANIFEST.sha256
   ```
3. The control migration is idempotent and contains explicit `begin;` and `commit;`. Dry-run the migration on a copy of the target Supabase schema, then run only `ted-board/supabase/migrations/20261019190000_control_center_workflows.sql` against the `wqnrortftkffmbeugjky` project through the existing Supabase migration API and record it in migration history. It follows `20261017030000_ted_board_fresh.sql`. Do not run unrelated pending migrations. The script adds card metadata and revision tracking, private veto and rule tables, and guarded transactional RPCs. Check that the migration completed before continuing:

   ```sql
   select to_regclass('public.ted_board_vetoes') as vetoes,
          to_regclass('public.ted_board_rules') as rules,
          to_regclass('public.ted_board_rule_matches') as matches;
   select column_name from information_schema.columns
   where table_schema = 'public' and table_name = 'ted_board_cards'
     and column_name in ('decision_kind', 'amount_cents', 'currency',
                         'priority_value', 'effort_seconds', 'revision')
   order by column_name;
   ```

4. Pause the existing mini `co.ted.board-jobs` heartbeat and `co.ted.decisions` watcher for the short cutover. Start with the merged private tree containing the approval fixes and any pod changes already applied. Back up this merged tree. Apply `patches/sessions.py.patch`, `patches/session_worker.py.patch`, and `patches/handler.ts.patch` as hunks over it. These patches were generated against the pre-integration private baseline. Dry-run each one first:

   ```sh
   cd ~/ted-ops/ted-board
   patch --dry-run -p1 < ~/ted-ops/control-center-stage/patches/sessions.py.patch
   patch --dry-run -p1 < ~/ted-ops/control-center-stage/patches/session_worker.py.patch
   patch --dry-run -p1 < ~/ted-ops/control-center-stage/patches/handler.ts.patch
   ```

   If a dry-run conflicts, merge only its Control hunks into the current file and review the result. Preserve the approval branch's artifact and session guards, the pod pulse GET and POST paths, and the current `frontdoor.ts`. Apply each clean patch with `patch -p1` using the same input path. Never copy the staged whole `sessions.py`, `session_worker.py`, or `handler.ts` over the merged tree. Install the other reviewed Control additions and changes, including `veto_worker.py`, `control.ts`, and `veto-mail.ts`, while preserving newer unrelated changes. Install `ted-decisions/board_route.py` and `ted-decisions/watch.py` after comparison with the current watcher files. Keep local secrets, ledgers, card data, and job state. The new watcher must be installed before any `veto_cleared` receipt exists so its opaque receipt note stays out of Telegram and NOW.md.
5. The timed send gate requires three server secrets: `TED_VETO_GMAIL_CLIENT_ID`, `TED_VETO_GMAIL_CLIENT_SECRET`, and `TED_VETO_GMAIL_REFRESH_TOKEN`. They must belong to the actual `hello@getkres.com` mailbox and authorize `https://www.googleapis.com/auth/gmail.readonly` plus `https://www.googleapis.com/auth/gmail.send`. Provision them only through the existing private secret management workflow, after review. This handoff creates no OAuth client, credentials, token, or live configuration. Missing or invalid credentials fail closed before the send claim, so Stop remains available. No existing mini Keychain token is copied to the server.

   Deploy only the `ted-board` Edge Function from the completed merged directory with the mini's existing Supabase deployment credentials. Every deploy ships the whole function directory, so check that the approval fixes, Control routes, and any already applied pod routes are present together. Keep the existing page and worker keys unchanged. Restart the paused mini jobs after the function responds correctly. The new heartbeat requires `veto_clear_due`, and dedicated timed workers require `veto_send`.

   ```sh
   cd ~/ted-ops/ted-board
   ~/.local/share/supabase/supabase functions deploy ted-board \
     --project-ref wqnrortftkffmbeugjky \
     --no-verify-jwt \
     --workdir ~/ted-ops/ted-board
   ```
6. Publish the public branch only after the Edge Function and workers are healthy. GitHub Pages serves the root of `main`, so Ted can merge or otherwise publish the reviewed static files when ready. This handoff does not merge or publish them. Do not install a routine on the MacBook.

## Smoke checks after Ted applies it

- Load `GET ?resource=control` with the existing private page key. It should return `vetoes`, `rules`, and `server_time`. Check the Control tab at phone width and desktop width.
- In a staging copy, create a narrow rule, confirm which current cards the sentence would cover, edit it, toggle it off and on, and delete it. Confirm only selected examples are saved, stale or out-of-scope examples are rejected, and the match count changes only when a worker explicitly applies the rule to a distinct source card.
- In staging, uncheck one classified bundle row and confirm only the checked card receives one decision receipt. A spend row without a positive recorded amount and currency must remain held.
- In staging, mark a routine draft for veto with an exact `email_envelope` containing `to`, `cc`, `bcc`, and `subject`, plus a score worksheet at or above the active RULES.md threshold. `card.py veto-mark` reads this envelope from the attestation JSON. All three recipient fields are arrays of bare email addresses, and `to` must contain at least one address. Stop it, then confirm the card returns to Needs you. On a separate staging card, let the timer expire and confirm the receipt contains identifiers only, while the worker fetches the exact draft through `veto_details`. Check the seven excluded action classes never enter a timer. Confirm Stop works after expiry and after clearance, and confirm an unknown CC or BCC address blocks `veto_send` without claiming the proposal. The local tests exercise the send boundary with fake Gmail responses; do not smoke test real sends. Do not run an expiry smoke check that could send a real message.
- Run a five-minute sprint on staging cards and confirm it stops at 0:00 and reports cleared, skipped, and time used.

Veto expiry records clearance for the worker. The page and heartbeat do not send messages or spend money. A tagged veto queue turn bypasses the model, and `session_worker.py` invokes the dedicated Python `veto_worker.py`. That worker calls the keyed server `veto_send` action. The server loads the exact stored envelope and draft, authenticates Gmail as `hello@getkres.com`, searches Sent, and verifies actual `SENT`, From, and recipient headers for every To, CC, and BCC address. Incoming mail, worker attestations, and search result matches alone do not establish a known contact. The verification scan is bounded and fails closed if no matching message is proven. A changed card invalidates its pending clearance. The score worksheet calculates the RULES.md prior, cue, scope, and override adjustments. The server checks its arithmetic and threshold, but the worker supplies the prior class, evidence, and local ledger counts. Those facts still require judgment and are not independently verified by the server. The server leaves the proposal `cleared` throughout Gmail history verification. It atomically changes `cleared` to `sending` immediately before the Gmail send request, using the same proposal lock as Stop. Stop can win before that transition, including a click still carrying the pending revision from just before heartbeat clearance. The existing card poll refreshes the Veto state, and a repeated claim cannot send again. The exact verified envelope and draft must still match the stored proposal at the claim. Success records the Gmail message ID and `sent`; a failed or uncertain request records `uncertain`, or leaves `sending` if the result cannot be persisted. Reconcile Gmail Sent before any manual retry. There is no automatic send retry.

The Gmail request follows Google's [message list](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/list), [message metadata](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/get), and [message send](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/send) APIs. The mini's existing `inbox-cards/gmail.py` talks to the Claude Gmail MCP connector using a Keychain credential, while `kres-inbound/send_gate.py` uses a Claude turn. Neither supplies a server-owned recipient history store.

Rules select candidates by recorded scope, and a worker must decide whether a sentence applies before recording a match. Existing unclassified Needs you cards remain individually actionable but are held out of bundle approval.

Rulebook examples are card snapshots Sebastian selected as cases the rule would cover. They are separate from `match_count`, which increases only when a worker applies an enabled rule to a distinct source card. Editing a rule can replace or clear its confirmed examples.

Sebastian's 2026-10-19 approval is a narrow, later exception to the older RULES.md ban on automatic external messages. It covers only timed, routine drafts to an already known recipient after the worker confirms every veto exclusion. It does not change approval requirements for new external people or other external actions. The remaining RULES.md hard lines, including account creation, permanent deletes, safety loosening, secrets, and App Review release, stay outside this clearance.

A bundle uses one board gesture and writes one approval receipt per checked card. Those receipts do not themselves send email or spend money. The existing exact-artifact approval gate may still require a later review for each email or spend action after a worker prepares its exact recipient, text, payee, and amount.

## Backout

Revert the static page first. Restore the backed-up private worker and watcher files, then redeploy the prior `ted-board` Edge Function. Leave the additive SQL objects in place until Ted has reviewed any stored vetoes, rules, and receipts and has a separate data-preserving cleanup plan. Keep existing job state and watcher ledgers.


The reviewed cleanup SQL is included at `ted-board/supabase/rollback/control_center_workflows.sql`. It is idempotent, contains explicit `begin;` and `commit;`, drops only Control triggers, functions, and tables, and keeps card metadata columns plus existing decision receipts. Before using it, restore prior workers and the prior Edge Function, back up all Control tables, and review any in-flight send or uncertain result. This is a destructive optional cleanup after reconciliation, not part of the normal backout above.

For the merged public page, call `controlCenter.reset()` inside `resetForKeyChange()`. The reset clears Control data and ignores in-flight responses from the previous key. Preserve the pod branch's key reset and append the Control reload to its `hashchange` listener.
