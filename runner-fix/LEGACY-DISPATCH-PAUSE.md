# Legacy admission pause

This separate preparation adds one pure helper import and one guard after result consumption in each legacy tick path. All Store.tick callers, including direct card.py create calls, retain queued work while paused. Existing worker PIDs are not signalled, adopted, or rewritten. Completed results still settle, failure publication still runs, and the heartbeat can flush its outbox. The absent marker preserves the current runtime behavior and current 3x load threshold.

The marker is `jobs/dispatch-pause.json`. Exactly `{"paused":false}` permits admission. Exactly `{"paused":true}` pauses it. Missing files permit admission. Malformed, unreadable, non-object, unknown-key, and symlink markers pause admission. This switch governs the legacy Store only; it is not the managed reconciler enable flag.

## Reconstruct and verify

Run from this checkout. Reconstruction refuses any changed baseline or dependency and never installs anything.

```sh
python3 runner-fix/prepare_legacy_dispatch_pause.py --root /Users/vahallo/ted-ops/ted-board --out /absolute/new/private/candidate
TED_LEGACY_PAUSE_RUNTIME=/absolute/new/private/candidate python3 runner-fix/legacy_dispatch_pause_test.py
python3 runner-fix/legacy_pause_control_test.py
```

The manifest pins the installed sessions.py plus card.py, claude_lanes.py, inbox_policy.py, and runner_failure_templates.json. Preserve any newer live bytes by regenerating and reviewing the packet, never by overwriting drift. Only sessions.py and the new dispatch_pause.py are installation files. Do not copy the dependency files over production.

## Operator-controlled installation and pause

Stop the scheduled producer during source replacement, keeping detached workers alive. Record its original enabled and loaded state first. The producer is co.ted.board-jobs, and each fresh heartbeat imports the new source. Already running Python processes keep imported code in memory, so a marker alone does not retrofit an old imported Store. Confirm no old heartbeat or direct card invocation remains before acknowledging the pause. Do not kill worker processes, and do not stop co.ted.board-live or the watchdog merely to pause admission.

Back up the exact current sessions.py, record all current dependency hashes, and preserve whether dispatch_pause.py was absent. Install the two verified candidate files using atomic replacement under `jobs/.sessions.lock`, rechecking manifest hashes while holding the lock. Do not restore sessions.json from an old backup. Production installation remains an explicit integrator action.

Once the reviewed source is installed, this command takes the same ledger lock, records the original marker bytes, mode, or absence to a new private backup, then writes the paused marker atomically. It refuses an existing backup. The command acknowledges only after any earlier tick holding the lock has finished.

```sh
python3 runner-fix/legacy_pause_control.py pause --root /Users/vahallo/ted-ops/ted-board --backup /absolute/private/unique-pause-state.json
```

Resume the fresh scheduled heartbeat in its original enabled and loaded state while the marker remains paused, so valid worker results keep settling. A direct card.py invocation also observes the guard. Watch running session PID identities, result receipts, queued counts, and recent errors. A queued session is not a drained worker. Never convert a still-running lease-less worker into a managed one.

## Resume or blocked-cutover rollback

If the cutover cannot complete, restore the original admission state before the final blocked handoff. This restores exactly the saved bytes, mode, or absence while holding the same ledger lock. It refuses a changed marker, preventing silent overwrite of another operator's pause. Retain the backup as a receipt.

```sh
python3 runner-fix/legacy_pause_control.py restore --root /Users/vahallo/ted-ops/ted-board --backup /absolute/private/unique-pause-state.json
```

An originally absent or false marker allows queued legacy turns to start on the next tick. An originally paused or malformed marker stays paused. Restore the original producer loaded and enabled state independently if it was changed. With admission restored and producer quiesced, source rollback can atomically restore the saved sessions.py and remove the helper only if its original state was absent. There is no reason to roll back session results, queues, PID state, or any database data.

No production source, state marker, scheduler, or SQL was changed while preparing this packet.
