# Keep worker failures out of Sebastian's inbox

Worker failures are Ted's operational work. A timeout, missing final result, startup failure, crash, or unsafe artifact goes to Up next with live state blocked. The dispatcher queues one board note per failed turn and recovery chain, using the existing idempotent board reply transport. It sends no Telegram message.

Timeout and missing-result ordinary work gets one durable recovery turn with the instruction "resume from your files". The existing twelve-hour worker timeout is preserved. The recovery count is saved with the active turn. A second failure holds for Ted. Approval execution, veto sends, user stops, crashes, startup failures, and work with a newer queued user request never receive an automatic retry. A queued message suppressing recovery is recorded in the failure note. Failed turns cannot collect stale approval files. A missed failure publication holds the retry until the board handoff is confirmed. A card already in Up next or Done satisfies that handoff without another write. A missed retry-start publication is retried while that worker is verified alive.

A confirmed deleted card clears failure publication and cancels its queued recovery. This handles both an absent card at lookup and deletion before the status write, without starting another worker. Ordinary transport failures still defer publication. The internal failure publisher opts into a distinct missing-card signal; other callers retain best-effort behavior.

Known refused or uncertain veto-send outcomes retain their required Sebastian email review and revision guard, and never start recovery work. A wrapper crash or missing result still goes to Ted. No send gate, recipient check, exclusion, or server authorization is relaxed.

`inbox_policy.py` is shared by the dispatcher, live-status client, reaper, and steward. It recognizes concrete asks about spending, email sends, contracts or legal decisions, pricing, explicitly gated production writes, taste picks on a fresh mockup batch, and copy Sebastian writes. Every sentence is checked for ask wording before failure or supersession can authorize a move. This includes asks sharing one sentence with a failure. Unknown asks remain in Needs you as ambiguous. Existing rule resolution still runs for retained asks. A database artifact alone does not make a Sebastian decision.

The steward originally lacked worker-failure, archived-batch, and explicit supersession rules. Its protections retained many legacy notices. Those protections are restored and remain authoritative. A steward move now requires an empty `decision_kind`, no sentence matching `ASK` or `decision()`, and a passing `protection(card, now)` check. It checks the title, body, live status, and recorded message text. A recent answer, pending approval, money metadata, active worker, or unresolved choice keeps the card in place. Only an otherwise unprotected card can receive a positive failure, archived-batch, supersession, or pure-FYI move. Archived or superseded work with any ask remains retained.

"Worker timed out; approve sending the email?", "Worker failed, approve the 400 dollar spend to retry?", and "Superseded by v2. Pick which headline you want for the lander." are retained. Failure and operational context in an earlier sentence also cannot hide a later ask. A startup failure mentioning a timeout remains a startup failure and cannot trigger recovery. Existing conservative mockup archive rules and overflow reporting remain in place. Transport failures and malformed mockup responses increment the reaper's deferred count once per affected card, and reconciliation continues for other cards.

Taste checks use project-scoped batch names or image IDs. An entirely archived linked batch cannot generate a taste or copy request. A fresh open image without a verdict can. Prices mentioned in a different sentence from the ask do not turn a copy review into pricing approval. Board moves use the observed section and exact update timestamp, and return a conflict if the card changed.

## Review and installation

This package is staged only. It has not been installed, deployed, or run against production cards. It needs no SQL, migration, new table, new grant, or new routine. Existing mini schedules remain responsible for the dispatcher, reaper, and steward.

The six `failure-routing-*.patch` files and `inbox_policy.py` are the combined replacement for the older `board-live.patch` and `finished-jobs-*.patch` control-flow changes. Do not apply both sets. The successful worker handoff to Up next for Ted review is included. The baseline manifest pins the private source versions reviewed here. If any checksum differs, rebase and retest the candidate before approval. Do not force a patch.

Prepare candidate copies, without changing the live mini runtime:

```sh
python3 runner-fix/prepare_failure_candidate.py \
  --runtime-root /absolute/path/to/ted-board \
  --destination /absolute/path/to/new-private-candidate
TED_RUNTIME_SOURCE=/absolute/path/to/new-private-candidate python3 runner-fix/failure_routing_test.py
TED_RUNTIME_SOURCE=/absolute/path/to/new-private-candidate python3 runner-fix/review_feedback_test.py
TED_RUNTIME_SOURCE=/absolute/path/to/new-private-candidate python3 runner-fix/fail_closed_review_test.py
python3 runner-fix/failure_package_test.py
TED_RUNTIME_SOURCE=/absolute/path/to/new-private-candidate python3 runner-fix/finished_jobs_test.py
TED_RUNTIME_SOURCE=/absolute/path/to/new-private-candidate python3 runner-fix/mockup_handoff_test.py
BOARD_LIVE_SOURCE=/absolute/path/to/new-private-candidate/board_live.py python3 runner-fix/reconcile_test.py
TED_RUNTIME_SOURCE=/absolute/path/to/new-private-candidate node --test runner-fix/failure_handler_test.ts runner-fix/finished_handler_test.ts
python3 scripts/check_data_api_grants.py
python3 -m unittest discover -s tests -p 'test_data_api_grants.py'
```

The Python tests block network and process execution, use temporary session stores, and exercise the real routing code. Handler tests use an in-memory database adapter. Node 24 or newer is required. No test sends an email, spends money, or runs SQL.

After Ted reviews the exact patch, installation and deployment require their own authorized execution:

1. On the mini, briefly pause the existing dispatcher, reaper, and steward schedules while retaining active worker processes. Take private, timestamped backups of the six modified files, the steward symlink target, and session state for audit. Do not launch another worker or create a new routine.
2. Deploy the reviewed handler first. It allows Up next, a restricted Up next to running recovery, and timestamp-guarded inbox cleanup. It preserves authentication and existing Needs you rule RPCs.
3. Install `inbox_policy.py` at the mini runtime root, and install the reviewed Python candidates together. Stage the steward candidate in a new versioned steward directory with its existing `steward_review.py`, then switch the current symlink. Preserve the existing launch agent's PYTHONPATH to the runtime root. Keep private file permissions.
4. Run the offline tests against those installed paths, and resume the existing mini schedules. Run the steward in dry-run mode and inspect its exact current proposed moves before authorizing live cleanup. Do not apply the saved inventory blindly.
5. Check a synthetic or already failed ordinary job through both attempts, confirm a single board note, and confirm a fresh legitimate decision remains in Needs you. Recount the live inbox and inspect failures in the existing local logs, without Telegram.

Rollback: pause the same existing schedules, restore the backed-up Python files and previous steward symlink, remove the new helper only if no restored code imports it, and redeploy the backed-up handler. Resume the schedules after offline verification. Preserve the current session state, recovery counts, receipts, and outbox. Restoring an old session snapshot can replay work, so keep the state backup for audit rather than automatic restoration. This task has made no production card corrections to roll back.
