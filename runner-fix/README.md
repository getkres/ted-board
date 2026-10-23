# Runner status reconciliation

The mini dispatcher is `Store.tick()` in the private `sessions.py` runtime. The jobs heartbeat calls it every 30 seconds. It runs at most three card sessions, and each session has a wrapper and a model child. A section count is not a process count. A queued session can have only `BRIEF.md` until a slot opens.

Two paths inflated Ted doing:

- The live reaper published blocked status for terminal sessions but left their cards in Ted doing.
- Mockup approval published a build card directly in Ted doing without enqueueing a session.

`board-live.patch` moves terminal blockers to Needs you, with a reason for rule review. It preserves running workers, queued turns, report freshness checks, process identity checks, the six-hour orphan grace period, and conditional API updates. Completed reports still move to Done.

`mockup-route.patch` puts new approved build cards in Up next until a worker handoff. It preserves existing builds in progress and their refreshes. Publishing art does not launch a worker.

The operational runtime is intentionally excluded from this public repository. These small patches contain only the changed control flow, and they make the installed mini changes reviewable without publishing the full private runtime. Apply them to the current mini runtime after backing up both files. Never apply them on the laptop.

```sh
patch --dry-run "$TED_BOARD_ROOT/board_live.py" < runner-fix/board-live.patch
patch --dry-run "$TED_DECISIONS_ROOT/mockup_route.py" < runner-fix/mockup-route.patch
patch "$TED_BOARD_ROOT/board_live.py" < runner-fix/board-live.patch
patch "$TED_DECISIONS_ROOT/mockup_route.py" < runner-fix/mockup-route.patch
python3 runner-fix/reconcile_test.py
python3 runner-fix/mockup_handoff_test.py
python3 "$TED_BOARD_ROOT/tests/live_status_test.py"
```

Set `TED_BOARD_ROOT` and `TED_DECISIONS_ROOT` to the existing mini checkout directories. The tests default to the installed runtime. `BOARD_LIVE_SOURCE` and `MOCKUP_ROUTE_SOURCE` can point at candidate copies before installation. Tests use temporary jobs and replace network publication with local doubles.

After installation, run the existing `board_live.py` entry point, or let its existing 120-second launchd routine reconcile. Read fresh board cards and verify worker identities under the session lock before recounting. Use the board API for live card corrections. No SQL, schema migration, new routine, external send, or new worker is required.

The current Jobs view shows running and queued card workers across all board sections, plus stale cards in Ted doing. A manual move to Up next or Done does not hide an active or queued session. Retained project section headings show counts only for their cards. Untracked processes stay separate. A heartbeat older than two minutes cannot certify a running or queued job. Both views remain explicit when worker data has not loaded.

```sh
node tests/board_status_test.cjs
node tests/board_status_ui.cjs
```

The browser check requires an installed Playwright module and Chromium. It uses intercepted API fixtures and verifies the current Jobs view, manual card moves, polling, stale heartbeats, and mobile and desktop layout. The existing board QA suite covers retained workflows and draft preservation.
