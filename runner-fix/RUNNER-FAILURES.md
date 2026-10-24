# Keep worker failures out of Sebastian's inbox

Worker failures are Ted's operational work. The dispatcher records structured failure kinds, queues one idempotent board note per recovery chain, and sends no Telegram message. Ordinary timeout and missing-result work gets one durable recovery turn with "resume from your files", then holds for Ted. The existing twelve-hour worker timeout is preserved. Crashes, startup failures, approval execution, veto sends, user stops, and work with a newer queued request never receive an automatic retry. A suppressed retry is recorded in the note.

## Approach change: exact runner templates

Vocabulary no longer authorizes inbox removal. `disposition()` has one allowed outcome: blocked Up next for an exact runner failure. Everything else remains in Needs you, including FYIs, archived-batch notices, superseded work, unrecognized requests, and unmarked legacy failures. The older cleanup estimates do not apply to this policy.

Every allowed departure requires all of these conditions:

- `decision_kind` is null, and no approval is pending. A `waiting_on_you` live state is conservatively treated as pending.
- The latest dated message is a unique Ted reply published through the runner's existing worker-authenticated reply transport. Malformed messages, tied timestamps, human replies, and missing dates are retained.
- Its entire text equals a template in `runner_failure_templates.json`, including the stable `[ted-runner-failure:v1:<kind>]` marker and its fixed recovery suffix. No substring, case-folded match, appended ask, or keyword is accepted.
- Any supplied transition line equals that same message. The only departure target is blocked Up next.

The shared template file defines timeout, no_result, startup_failure, and crash notes, plus the retry, suppressed, and held suffixes. The dispatcher selects them from structured process results, never model prose. "Worker run finished" describes the terminated process, not successful completion of its task. A crash with return code 1 and empty output stays a crash and is never converted to no_result or retried. Legacy empty-result handling only fills an absent failure kind.

The steward additionally restores its original `protection(card, now)`, dated latest-worker-message, `report_only_reason()`, and `positive_completion()` gates before disposition. A recent answer, money metadata, active worker, or unresolved choice still holds the card. An older Sebastian-authored FYI also stays. Existing conservative mockup archive safeguards and overflow reporting remain intact. A retained `move_card()` result is not counted as moved, and an exception increments the failed count while later candidates continue.

`live_status.update()` protects departures from Needs you before its failure branch. The failure publisher cannot treat a protected inbox decision as a confirmed recovery handoff. The reaper checks pending approvals before stale failed-worker state. Normal decision requests still use existing rule resolution. Decision category labels do not authorize removal from the inbox.

The handler validates the same latest-message template before accepting an inbox departure. Its atomic update also requires `.is('decision_kind', null)`, a non-pending live state, the source section, the snapshot timestamp, and the exact message array. Board replies do not advance the card timestamp, so the message condition prevents a reply arriving between validation and update from being hidden. Conflicts return 409.

A confirmed deleted card clears failure publication and cancels queued recovery, whether it disappears before lookup or before the status write. Temporary transport failures still defer publication. A card already in Up next or Done satisfies the handoff without another write. Retry-start publication is retried only while the recorded worker is verified alive. Known refused or uncertain veto-send outcomes retain their required email review, revision guard, and recovery exclusion. No send authorization is relaxed.

## Review and installation

This package is staged only. It has not been installed or deployed. This review round uses only saved sources and offline fixtures, with no live steward run or inventory. It needs no SQL, migration, new table, new grant, or new routine. Existing mini schedules remain responsible for the dispatcher, reaper, and steward.

The six `failure-routing-*.patch` files plus `inbox_policy.py` and `runner_failure_templates.json` are the combined replacement for the older `board-live.patch` and `finished-jobs-*.patch` control-flow changes. Do not apply both sets. The successful worker handoff to Up next for Ted review is included. The baseline manifest pins the private source versions reviewed here. If any checksum differs, rebase and retest the candidate before approval. Do not force a patch.

Prepare candidate copies, without changing the live mini runtime:

```sh
python3 runner-fix/prepare_failure_candidate.py \
  --runtime-root /absolute/path/to/ted-board \
  --destination /absolute/path/to/new-private-candidate
TED_RUNTIME_SOURCE=/absolute/path/to/new-private-candidate python3 runner-fix/failure_routing_test.py
TED_RUNTIME_SOURCE=/absolute/path/to/new-private-candidate python3 runner-fix/review_feedback_test.py
TED_RUNTIME_SOURCE=/absolute/path/to/new-private-candidate python3 runner-fix/fail_closed_review_test.py
TED_RUNTIME_SOURCE=/absolute/path/to/new-private-candidate python3 runner-fix/marker_allowlist_test.py
python3 runner-fix/failure_package_test.py
TED_RUNTIME_SOURCE=/absolute/path/to/new-private-candidate python3 runner-fix/finished_jobs_test.py
TED_RUNTIME_SOURCE=/absolute/path/to/new-private-candidate python3 runner-fix/mockup_handoff_test.py
BOARD_LIVE_SOURCE=/absolute/path/to/new-private-candidate/board_live.py python3 runner-fix/reconcile_test.py
TED_RUNTIME_SOURCE=/absolute/path/to/new-private-candidate node --test runner-fix/failure_handler_test.ts runner-fix/finished_handler_test.ts runner-fix/marker_handler_test.ts
python3 scripts/check_data_api_grants.py
python3 -m unittest discover -s tests -p 'test_data_api_grants.py'
```

The Python tests block network and process execution, use temporary session stores, and exercise the real routing code. Handler tests use an in-memory database adapter. Node 24 or newer is required. No test sends an email, spends money, or runs SQL.

After Ted reviews the exact patch, installation and deployment require their own authorized execution:

1. On the mini, briefly pause the existing dispatcher, reaper, and steward schedules while retaining active worker processes. Take private, timestamped backups of the six modified files, the steward symlink target, and session state for audit. Do not launch another worker or create a new routine.
2. Deploy the reviewed handler and its shared `runner_failure_templates.json` dependency first. It preserves authentication and existing Needs you rule RPCs, validates the exact latest runner note, and applies conditional inbox guards.
3. Install `inbox_policy.py` and the identical `runner_failure_templates.json` at the mini runtime root, and install the reviewed Python candidates together. Stage the steward candidate in a new versioned steward directory with its existing `steward_review.py`, then switch the current symlink. Preserve the existing launch agent's PYTHONPATH to the runtime root. Keep private file permissions.
4. Run the offline tests against those installed paths. Before authorizing live cleanup, complete the disposable-card smoke check below in the existing steward launch environment. Resume the existing mini schedules only after that succeeds. Run a fresh steward dry-run, and inspect its exact proposed moves. Do not apply an older inventory.
5. Check a synthetic or already failed ordinary job through both attempts, confirm a single board note, and confirm a fresh legitimate decision remains in Needs you. Recount the live inbox and inspect failures in the existing local logs, without Telegram.

Rollback: pause the same existing schedules, restore the backed-up Python files and previous steward symlink first, remove the new helper and shared template only if no restored code imports them, and redeploy the backed-up handler last, with its original dependencies. Resume the schedules after offline verification. Preserve the current session state, recovery counts, receipts, and outbox. Restoring an old session snapshot can replay work, so keep the state backup for audit rather than automatic restoration. This task has made no production card corrections to roll back.

## Disposable-card installation smoke check

This step is for Ted's separately authorized installation, not this review job. Run it as the existing steward launchd user, using that job's actual environment, working directory, Python interpreter, and PYTHONPATH, with both the runtime root and installed steward target importable. An interactive shell with different credentials or import paths does not validate the service.

Prepare one explicitly disposable card in project `Runner smoke`, in Needs you, with null decision_kind, blocked live state, no pending approval or choices, and a fresh exact runner-generated failure note. Record that card's ID as `TED_STEWARD_SMOKE_CARD` in the smoke process environment. Never mark a real decision as a runner failure for this check. The following performs one guarded move through the installed `move_card()` path and fails on missing imports, missing keys, protection, or rejected authorization. It prints no credentials.

```sh
/Library/Developer/CommandLineTools/usr/bin/python3 - <<'PY'
import os
import time
import board_client
import live_status
import inbox_steward
cfg = board_client.load_env()
if not cfg.get('TED_DECISIONS_WORKER_KEY') or not cfg.get('TED_DECISIONS_KEY'):
    raise SystemExit('steward smoke failed: configured credentials missing')
card_id = os.environ['TED_STEWARD_SMOKE_CARD']
card = next(c for c in board_client.cards() if c.get('id') == card_id)
assert card.get('project') == 'Runner smoke' and card.get('section') == 'needs_you'
target, note = inbox_steward.classify_card(card, time.time())
assert target == 'up_next', 'disposable card failed the installed guard'
result = inbox_steward.move_card(card_id, target, note, card['updated_at'])
assert result.get('ok') is True and result['card']['section'] == 'up_next'
print('steward imports, configured credentials, and guarded disposable move passed')
PY
```

If it fails, keep cleanup disabled, fix the installed environment or candidate, and repeat only against the disposable card after inspecting its current state. A dry-run alone does not exercise `move_card()` authentication. This review did not create or move a smoke card.
