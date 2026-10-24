# Mockup archive and restore

Batch cards, ordinary batch views, direction rounds, and comparison views have an Archive action. The frame viewer has an Archive action for its current frame. An archive disappears locally immediately, and the Undo toast cancels every queued archive during the five-second window. The request sends after that window, or on page exit, following the inbox queue pattern. A failed save returns the item with a retryable error. Pending archives survive normal polling and tab changes, and access-key resets cancel unsent requests.

Archived shows archived frames grouped by their original project and batch. A partially archived batch can appear in both the active list and Archived, each with its own frames. Restore returns only archived frames. Decisions, notes, pins, and decision history remain intact. Older picks retain their original approval through the existing pick receipts.

## Backend review gate

Archive controls require an explicit `archive_enabled: true` in the authenticated mockups GET response. The private handler patch accompanies the card report. It invokes the server-only integration module, retains the worker archive route, and reads existing legacy pick receipts for archived rows. Nothing has been deployed or applied to a database.

Page POST accepts exactly `{action:'archive'|'unarchive',project,batch,key}` or `{action:'archive'|'unarchive',project,mockup_id,key}`. The handler authenticates the page key before passing a page principal. Unknown fields, mixed selectors, missing projects, invalid IDs, and broad ID lists are rejected. No caller-selected status or verdict is accepted. Worker archive keeps its existing contract and credential.

`backend-integration/mockup-archive.ts` uses only the existing server-owned service-role client. It updates `ted_mockups.status`, reads existing pick receipts when restoring legacy approvals, paginates reads, bounds ID chunks, and filters every update by project and batch or frame. Restores also require archived status. It changes no grants or RLS policies, needs no migration, and exposes no client database access. Multi-chunk operations can partially complete on a transport or database failure, so the error asks for a refresh before retrying. Both actions are safe to retry for the same scope.

Ted must reconcile the private patch with the deployed handler, run the private credential and regression tests, review the frontend PR, and authorize deployment before enabling the capability. Keep operational files and the private handler out of this public repository.

## Offline checks

Run a static server on `127.0.0.1:8763`, then run `node qa/run.cjs`. Set `PLAYWRIGHT_MODULE` and `NODE_PATH` to an existing Playwright installation if needed. Every backend request is intercepted, and unmatched external requests are blocked.

The suite includes `node --test backend-integration/mockup-archive.test.ts` and `node --require ./qa/offline.cjs --test qa/mockup-archive.cjs`. Browser coverage includes five-second Undo, archive persistence, restore, single-frame scope, batch modes, failed requests, delayed polls, multiple queued archives, modal toast access, keyboard focus, and access-key isolation. It captures list, batch, viewer, Undo, and Archived at 375, 1440, and 2560 pixels, checking text clipping, horizontal overflow, and browser errors. Screenshots and the design process board accompany the local card report.

Run `python3 scripts/check_data_api_grants.py` and `python3 -m unittest discover -s tests -p 'test_data_api_grants.py'`. Run the guard against the local operational repository too. No new SQL or table grant is needed for this change.
