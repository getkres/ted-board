# Keep worker failures out of Sebastian's inbox

Worker failures are Ted's operational work. The dispatcher records structured failure kinds, queues one idempotent board note per recovery chain, and sends no Telegram message. Ordinary timeout and missing-result work gets one durable recovery turn with "resume from your files", then holds for Ted. The existing twelve-hour worker timeout is preserved. Crashes, startup failures, approval execution, veto sends, user stops, and work with a newer queued request never receive an automatic retry. A suppressed retry is recorded in the note.

## Approach change: server-stamped runner templates

Vocabulary no longer authorizes inbox removal. `disposition()` has one allowed outcome: blocked Up next for an exact runner failure. Everything else remains in Needs you, including FYIs, archived-batch notices, superseded work, unrecognized requests, and unmarked legacy failures. The older cleanup estimates do not apply to this policy.

Every allowed departure requires all of these conditions:

- `decision_kind` is null, and no approval is pending. A `waiting_on_you` live state is conservatively treated as pending.
- The latest dated message is a unique Ted message with `runner_failure: true` stamped by the server. Ordinary `ted_reply` calls cannot set this flag, even when their text exactly matches a template. Malformed messages, tied timestamps, human replies, and missing dates are retained.
- Its entire text equals a template in `runner_failure_templates.json`, including the stable `[ted-runner-failure:v1:<kind>]` marker and its fixed recovery suffix. No substring, case-folded match, appended ask, or keyword is accepted.
- `live_status_at` is absent or valid and no newer than that message. A newer status or an invalid timestamp retains the card.
- Any supplied transition line equals that same message. The only departure target is blocked Up next.

The shared template file defines timeout, no_result, startup_failure, and crash notes, plus the retry, suppressed, and held suffixes. The dispatcher queues structured failure kind and recovery state. Its durable outbox calls the worker-authenticated `runner_failure` action, where the server selects the exact text, stamps the flag and timestamp, and deduplicates by failure token. A conditional message-array update avoids overwriting a concurrent reply. The action accepts no supplied text or flag. Normal Ted replies keep their existing path and remain unflagged. "Worker run finished" describes the terminated process, not successful completion of its task. A crash with return code 1 and empty output stays a crash and is never converted to no_result or retried. Legacy empty-result handling only fills an absent failure kind.

The steward additionally restores its original `protection(card, now)`, dated latest-worker-message, `report_only_reason()`, and `positive_completion()` gates before disposition. A recent answer, money metadata, active worker, or unresolved choice still holds the card. An older Sebastian-authored FYI also stays. The steward patch is rebased on PR 36 at `b0b6ae6afb5c897f5ad97827a6425986e6f11b4c`. Its card-only scope, raw response validation, protected scopes, kill switches, fresh snapshot lease, and single run boundary remain intact. PR 41 remains the sole mockup archive owner. A retained or failed `move_card()` is not counted as moved. PR 36 owns the stop-on-failure behavior: a failed move stops later actions and marks cached counts stale.

`live_status.update()` protects departures from Needs you before its failure branch. The failure publisher cannot treat a protected inbox decision as a confirmed recovery handoff. The reaper checks pending approvals before stale failed-worker state. Normal decision requests still use existing rule resolution. Decision category labels do not authorize removal from the inbox.

The handler validates the same latest-message template before accepting an inbox departure. Its atomic update also requires `.is('decision_kind', null)`, a non-pending live state, the source section, the snapshot timestamp, the observed live-status timestamp, and the exact message array. Board replies do not advance the card timestamp, so the message condition prevents a reply arriving between validation and update from being hidden. Conflicts return 409.

A missing ID is treated as deleted only after a nonempty, well-formed, untruncated card list confirms absence, or a write returns an explicit 404. An empty list, missing cards payload, malformed row, duplicate ID, undecodable envelope, or whole-feed 404 defers publication. A whole-feed 404 does not prove that a particular card was deleted. An absent ID at the 500-card cap also defers publication and preserves the queue and pending handoff. A card actually returned in a well-formed capped list is still positively known to exist. A positively confirmed deleted card clears failure publication and cancels queued recovery. Temporary transport failures still defer publication. A card already in Up next or Done satisfies the handoff without another write. Retry-start publication is retried only while the recorded worker is verified alive. Known refused or uncertain veto-send outcomes retain their required email review, revision guard, and recovery exclusion. No send authorization is relaxed.

## Review and installation

This package is staged only. It has not been installed or deployed. This review round uses only saved sources and offline fixtures, with no live steward run or inventory. It needs no SQL, migration, new table, new grant, or new routine. Existing mini schedules remain responsible for the dispatcher, reaper, and steward.

PR 36 must merge before PR 44. This package pins its reviewed steward and unchanged `steward_review.py` dependency. If PR 36 changes, reconstruct it and refresh these hashes before review. No merge or installation is performed by this job.

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
TED_RUNTIME_SOURCE=/absolute/path/to/new-private-candidate python3 runner-fix/review_hardening_test.py
TED_RUNTIME_SOURCE=/absolute/path/to/new-private-candidate python3 runner-fix/pr36_compatibility_test.py
python3 runner-fix/failure_package_test.py
TED_RUNTIME_SOURCE=/absolute/path/to/new-private-candidate python3 runner-fix/finished_jobs_test.py
TED_RUNTIME_SOURCE=/absolute/path/to/new-private-candidate python3 runner-fix/mockup_handoff_test.py
BOARD_LIVE_SOURCE=/absolute/path/to/new-private-candidate/board_live.py python3 runner-fix/reconcile_test.py
TED_RUNTIME_SOURCE=/absolute/path/to/new-private-candidate node --test runner-fix/failure_handler_test.ts runner-fix/finished_handler_test.ts runner-fix/marker_handler_test.ts runner-fix/failure_publication_test.ts
python3 scripts/check_data_api_grants.py
python3 -m unittest discover -s tests -p 'test_data_api_grants.py'
```

The Python tests block network and process execution, use temporary session stores, and exercise the real routing code. The PR 36 compatibility suite uses its merged test source at `runner-fix/inbox-steward/steward_test.py`, or the exact reviewed file given by `TED_PR36_TEST_SOURCE`. It keeps 27 scope and lifecycle tests unchanged, replacing only their old admitted-report fixture with a server-stamped runner fixture. Handler tests use an in-memory database adapter. Node 24 or newer is required. No test sends an email, spends money, or runs SQL.

After Ted reviews the exact patch, installation and deployment require their own authorized execution:

1. On the mini, briefly pause the existing dispatcher, reaper, and steward schedules while retaining active worker processes. Take private, timestamped backups of the six modified files, the steward symlink target, and session state for audit. Do not launch another worker or create a new routine.
2. Deploy the reviewed handler and its shared `runner_failure_templates.json` dependency first. It preserves authentication and existing Needs you rule RPCs, validates the exact latest runner note, and applies conditional inbox guards.
3. Install `inbox_policy.py` and the identical `runner_failure_templates.json` at the mini runtime root, and install the reviewed Python candidates together. Stage the steward candidate in a new versioned steward directory with its existing `steward_review.py`, then switch the current symlink. Preserve the existing launch agent's PYTHONPATH to the runtime root. Keep private file permissions.
4. Run the offline tests against those installed paths. Preserve PR 36's disabled markers, raw cards-envelope validation, and Needs you filter before the 500-card cap. Its current GET contract does not require an `ok` field; missing cards, error-bearing envelopes, and pulse errors still fail closed. Do not replace an ambiguous response with an empty inbox. Before authorizing live cleanup, complete the disposable-card smoke check below in the existing steward launch environment. Resume the existing mini schedules only after that succeeds. Run a fresh steward dry-run, and inspect its exact proposed moves. Do not apply an older inventory.
5. Check a synthetic or already failed ordinary job through both attempts, confirm a single board note, and confirm a fresh legitimate decision remains in Needs you. Recount the live inbox and inspect failures in the existing local logs, without Telegram.

Rollback: pause the same existing schedules, restore the backed-up Python files and previous steward symlink first, remove the new helper and shared template only if no restored code imports them, and redeploy the backed-up handler last, with its original dependencies. Resume the schedules after offline verification. Preserve the current session state, recovery counts, receipts, and outbox. Restoring an old session snapshot can replay work, so keep the state backup for audit rather than automatic restoration. This task has made no production card corrections to roll back.

## Disposable-card installation smoke check

This step is for Ted's separately authorized installation, not this review job. Run it as the existing steward launchd user, using that job's actual environment, working directory, Python interpreter, and PYTHONPATH, with both the runtime root and installed steward target importable. An interactive shell with different credentials or import paths does not validate the service.

Prepare one explicitly disposable card in project `Runner smoke`, in Needs you, with null decision_kind, blocked live state, no pending approval or choices, and a fresh server-stamped failure note from the structured runner publication path. Record that card's ID as `TED_STEWARD_SMOKE_CARD` in the smoke process environment. Never mark a real decision as a runner failure for this check. The following performs one guarded move through the installed `move_card()` path and fails on missing imports, missing keys, protection, or rejected authorization. It prints no credentials.

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
cards = inbox_steward.fetch_cards()
card = next(c for c in cards if c.get('id') == card_id)
assert card.get('project') == 'Runner smoke' and card.get('section') == 'needs_you'
target, note = inbox_steward.classify_card(card, time.time())
assert target == 'up_next', 'disposable card failed the installed guard'
state = inbox_steward.WriteState(inbox_steward.ROOT.resolve(), cards=cards, observed_at=time.monotonic())
lease = inbox_steward.RUN.set(state)
try:
    result = inbox_steward.move_card(card_id, target, note)
    assert result.get('ok') is True and result['card']['section'] == 'up_next'
finally:
    inbox_steward.RUN.reset(lease)
print('steward imports, configured credentials, and guarded disposable move passed')
PY
```

If it fails, keep cleanup disabled, fix the installed environment or candidate, and repeat only against the disposable card after inspecting its current state. A dry-run alone does not exercise `move_card()` authentication. This review did not create or move a smoke card.

Approval execution retry exclusion: in the prepared private `sessions.py`, the failure handoff sets `retry` only when the kind is timeout or no_result, `s.get('reviewing')` is false, and there is no active veto revision. Approval execution sets `s['reviewing']` before its worker starts and clears it only after this failure decision. The final source line references are recorded in this job's REPORT.md. Tests cover both retry-eligible failure kinds for email, spend, and database approvals.
