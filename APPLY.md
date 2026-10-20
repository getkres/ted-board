# Apply the integrated Ted Board changes from 2026-10-19

This is the single handoff for `integrate-1019`. It combines the approval and mockup fixes, Control Center, and Pod pulse in that order. The static PR is a release candidate. No production database change, backend deployment, merge to `main`, or launchd change has been performed. Ted must review and apply the private database handoff before the operational cutover and public merge.

## Artifacts and verification

- Public branch: `integrate-1019`, created from `main` and merged from `fix/approval-mockup-batches-1019`, `feat/control-center-workflows`, and `feat/pod-pulse`, in that order.
- Private local bundle: `private-handoff/integrate-1019-private.tar.gz`. It is ignored by public Git. SHA-256: `0bca8a9a4e42d263ffc00792b5a85cd51d224555510c9ccd0a1f8e11894e7a46`.
- The bundle contains one `patches/merged-private.patch` for every existing private file changed by the three branches. That patch includes both `sessions.py` and the complete combined `ted-board/handler.ts`. The bundle also contains new source files, four forward SQL files, four rollback SQL files, the read-only `audit/BACKLOG-APPROVED.md`, a mini-only launchd plist, and `MANIFEST.sha256`.
- The patch was dry-run and replayed against copies of the current operational baseline. Every replayed file matched this integration worktree byte for byte. Recheck it against the target tree before applying it.
- The 375px screenshots are in `screenshots/integrate-1019/` for Kres + clients, Fictora, Bookish, and Control. They use local fixture content.

## Release verification, 2026-10-20

C1 is present in `39300e5`: Stop remains available after countdown expiry and clearance. C3 returns a stale bundle approval to Needs you, while preserving a newer decision. C4 has explicit transactions, repeatable migration objects, and a tested drop script. C5 removes the unreachable duplicate-revision check, while retaining pending-proposal uniqueness before the card update. C6 resets Control state on a key change and discards responses from the previous key. These fixes were already present in the integration sources and have been verified again.

Fresh isolated runs passed 151 board Python tests, 18 decisions Python tests, and 129 Deno TypeScript tests across the board and mockups backend. The Node approval test and both approval SQL fixture checks also passed. Control passed 18 browser scenarios, pod pulse passed 8 scenario groups, and mockup batches passed desktop and phone checks. The initial broad Deno invocation picked up a Node-only SQL fixture and failed on its Node import; explicit TypeScript selection and a separate Node run passed. The board, Jobs, Fresh Ted, live-status, and current viewer browser checks also passed. A legacy viewer fixture was updated from obsolete click-to-pin and Fit assumptions and then passed on desktop and phone, with no product change.

The private patch was dry-run and replayed against copies of the current operational files. All 16 patched files matched the integration sources, including both worker policy and approval changes in `sessions.py` and all three feature sets in `handler.ts`. Operational files have not been installed while the schema gate is pending. Never install either file wholesale.

The private job handoff contains exact `apply.sql`, `rollback.sql`, `backup.sh`, `checks-before.sql`, and `checks-after.sql`, plus the verified private bundle and fresh test output. The combined forward SQL applies twice in an isolated database while retaining rules. Its rollback runs twice while preserving cards and decision receipts. The backup procedure requires Ted's private database connection and has not been executed. This verifies the scripts against fixtures; Ted must inspect the production preflight results and backup before applying them.

## Application order on `sebastians-mac-mini`

1. Review this branch and bundle, then back up the operational `~/ted-ops/ted-board` and `~/ted-ops/ted-decisions` source trees, current Supabase functions, relevant tables, watcher ledgers, and job state. Do not replace secrets or live data with staging files. Pause the existing `co.ted.board-jobs`, `co.ted.board-live`, and `co.ted.decisions` jobs for the cutover.
2. Transfer the bundle to the mini, unpack it in a private staging directory, and verify its checksum and manifest. Run the patch dry run from `~/ted-ops`, so `a/ted-board/...` and `a/ted-decisions/...` resolve correctly:

   ```sh
   mkdir -p ~/ted-ops/integrate-1019-stage
   tar -xzf integrate-1019-private.tar.gz -C ~/ted-ops/integrate-1019-stage
   cd ~/ted-ops/integrate-1019-stage
   shasum -a 256 -c MANIFEST.sha256
   cd ~/ted-ops
   patch --dry-run -p1 < ~/ted-ops/integrate-1019-stage/patches/merged-private.patch
   ```

   If the dry run conflicts with intervening edits, stop and review the affected hunks against this worktree. Never copy a whole `handler.ts` or `sessions.py` over the target tree. After a clean dry run, apply the same patch with `patch -p1`. The patch covers the board worker, mockups handler, `ted-board` Edge Function, and decisions watcher together.
3. Install only the four new source files from the bundle into their matching paths: `ted-board/pod_pulse.py`, `ted-board/veto_worker.py`, `ted-board/supabase/functions/ted-board/control.ts`, and `ted-board/supabase/functions/ted-board/veto-mail.ts`. Remove the obsolete operational `pod_pulse_config.json` after confirming no caller uses it. Keep the existing page key, worker key, credentials, job data, and ledgers.
4. Ted must review, back up, and apply the four complete forward SQL files to Supabase project `wqnrortftkffmbeugjky` in numeric order. Each file is idempotent and explicitly wrapped in `begin;` and `commit;`. Use the reviewed migration process, record each migration, and confirm each succeeds before moving to the next. The approval transition SQL requires the existing board live status columns. The mockup batch SQL requires the existing `mockup-zoom/verdicts-apply.sql` RPC. The rollback scripts have matching numbers in `rollback/` and are for a separately reviewed backout, after preserving any new data and reconciling any in-flight send.

   | Order | Forward SQL | Main effect |
   | --- | --- | --- |
   | 1 | `sql/01_approval_card_transitions.sql` | Approval result lines and Needs you recovery, including `rejected, back to you`. |
   | 2 | `sql/02_mockup_approval_batches.sql` | Whole-batch approval and five-second Undo. |
   | 3 | `sql/03_control_center_workflows.sql` | Revision guards, rules, bundles, vetoes, and guarded sends. |
   | 4 | `sql/04_pod_pulse.sql` | Private, replaceable pod snapshot table. |

5. Before enabling timed sends, provision the server secrets `TED_VETO_GMAIL_CLIENT_ID`, `TED_VETO_GMAIL_CLIENT_SECRET`, and `TED_VETO_GMAIL_REFRESH_TOKEN` through the existing secret workflow. They must belong to `hello@getkres.com` and permit Gmail read and send scopes. Missing or invalid credentials fail closed before the send claim. The server checks actual Sent history for every To, CC, and BCC recipient. A worker assertion or matching search result alone does not satisfy the known-recipient gate. Do not use a real send as a smoke test.
6. Run the combined Python, Deno, SQL fixture, and local browser suites in an isolated `integrate-1019` checkout with its public HTML, JavaScript, and CSS alongside the patched private sources. This worktree is the reference test checkout. Keep the operational public assets unpublished until step 8. Confirm the `ted-board` function directory has the approval changes in `frontdoor.ts`, the Control routes and send gate, and the Pod pulse GET and worker POST paths. Then perform exactly one `ted-board` Edge Function deploy from that merged directory. Deploy `ted-mockups` once from its merged directory. Both commands are for the later approved cutover, and neither was run during integration:

   ```sh
   /Users/vahallo/.local/share/supabase/supabase functions deploy ted-board --project-ref wqnrortftkffmbeugjky --no-verify-jwt --workdir /Users/vahallo/ted-ops/ted-board
   /Users/vahallo/.local/share/supabase/supabase functions deploy ted-mockups --project-ref wqnrortftkffmbeugjky --no-verify-jwt --workdir /Users/vahallo/ted-ops/ted-board/mockups-backend
   ```

7. On the mini, run `python3 pod_pulse.py --check` first. It reads `~/kres/company/pods/PULSE-MAP.json` directly and should show luvo and thomas-yang, labeled BLD, under Kres + clients, fictora under Fictora, and bookish under Bookish. After checking, run `python3 pod_pulse.py` once to publish the complete snapshot with the existing worker key. Schedule the new publisher hourly only on the mini after the cutover, using the bundle's `launchd/co.ted.pod-pulse.plist`. It uses the unique label `co.ted.pod-pulse`, `RunAtLoad`, and `StartInterval` 3600. Confirm that the label does not already exist before bootstrapping it.
8. Restart the paused existing mini jobs after the backend, watcher, and snapshot respond correctly. Publish the public static branch only after the private cutover passes its checks. This integration request stops before every action in this section.

## Behavior to confirm in staging

- Rejecting an approval moves its card to Needs you with `rejected, back to you`. An approved card refreshes immediately, even if a prior load was in flight. Whole-batch mockup approval produces one receipt for the batch, and Undo remains available for five seconds.
- A stale bundle approval returns its card to Needs you with `approval went stale, tap again` when that receipt still owns the answer. A newer decision and its pending job are preserved.
- Stop remains enabled after the displayed countdown reaches zero and after clearance, until the server begins the send. The dedicated worker uses the server `veto_send` gate, and the server verifies every recipient against mail previously sent from `hello@getkres.com`. An uncertain result requires manual Gmail Sent reconciliation. There is no automatic retry.
- The pod strip appears only in matching project tabs. `PULSE-MAP.json` is the sole pod list, so removing a pod from the map removes its published row on the next successful run.

## Backout

First stop the new pod publisher and pause the affected existing jobs on the mini. Restore the backed-up static page, workers, watcher, and Edge Function trees, then deploy the prior `ted-board` and `ted-mockups` functions. Preserve ledgers and job state. The four numbered rollback SQL files are idempotent and transactional, but may remove stored Control data or a pod snapshot. Review and back up that data, reconcile every in-flight or uncertain send, and apply the matching rollback only when the impact is understood.
