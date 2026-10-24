# Decide review follow-up

PR 34 remains a draft for Ted. Main includes merged viewer-header PR 32, and the branch was explicitly rebased against it. No merge or deployment is included.

The review corrections cover all seven requested behaviors:

1. Dismissal records include only the approval ID submitted by an actual approval or rejection. Pending approvals block non-approval commits, including a queued Tell Ted note. Such a card remains available after the five-second window and reload.
2. Decide waits for cards and jobs, including approvals, before rendering actions. The 2500 ms delayed-response test exercises both Approve and No and checks the approval payloads.
3. Update grouping requires explicit informational metadata or an eligible completed card. Any decision_kind, approval record, amount_cents value, or nonempty options prevents grouping. An untagged staging-migration message stays a decision. Successful worker completion is enforced by the staged dispatcher, worker, reconciliation, client, and handler patches described in `runner-fix/FINISHED-JOBS.md`.
4. Queue entries snapshot the card instead of retaining a mutable reference. Commit requires the current card to remain actionable, with the same section, answer, and ask. List actions also cancel matching queued work.
5. Choice cards show their own options. The synthetic No or kill shortcut is limited to yes-or-no asks without recorded options. Pending approvals use the approval rejection endpoint.
6. Card and approval loading errors appear inside Decide with working Refresh and Access controls. Tests verify recovery to an actionable card and access to the private-link form.
7. Hidden visibility and pagehide flush queued work with keepalive fetches. Phase guards and cleared timers prevent duplicate submission. Every save in an updates pile starts before the first response resolves.

The browser regression group contains 29 tests. The complete browser suite runs 18 verification groups in each theme. All requests use synthetic fixtures, and the suite runner preloads `qa/offline.cjs` to reject unmatched requests outside localhost. An unmatched external request fails the QA process. No production QA POST is permitted.

Run a static server on localhost port 8763, point PLAYWRIGHT_MODULE at an installed Playwright module if necessary, and run:

```sh
QA_THEME=light QA_OUT=/absolute/path/to/evidence/light node qa/run.cjs
QA_THEME=dark QA_OUT=/absolute/path/to/evidence/dark node qa/run.cjs
python3 scripts/check_data_api_grants.py
python3 -m unittest discover -s tests -p 'test_data_api_grants.py'
node --test tests/board_status_test.cjs
node --require ./qa/offline.cjs tests/board_status_ui.cjs
```

Runtime candidates passed six worker and dispatcher tests, one handler test, four reconciliation tests, four existing mockup-handoff tests, and fourteen existing live-status tests. The grant guard and its seventeen regression tests pass. JavaScript, inline-script, Python syntax, and diff checks pass.

The original twenty Decide tests passed before changes. The review regressions were observed failing before their fixes. Intermediate runs exposed a completion-wait race in the partial-save test, which now waits on actual completion, and the grouped unload-save bug, which received a separate failing regression and fix.

Review was an author self-review. The card explicitly prohibited delegating independent workers. Physical iPhone Safari, actual tab termination across browsers, production API writes, runtime installation, and Edge Function deployment remain unexercised or pending review. Lifecycle events and keepalive payloads were verified in intercepted Chromium tests.
