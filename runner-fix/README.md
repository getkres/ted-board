# Runner status reconciliation

Current routing and installation instructions are in [RUNNER-FAILURES.md](RUNNER-FAILURES.md). Its combined patches supersede `board-live.patch` and `finished-jobs-*.patch`. Worker failures and verified operational review belong in Up next with state blocked. Concrete decisions and ambiguous asks remain in Needs you until there is positive evidence for a mechanical move.

The mini dispatcher is `Store.tick()` in the private `sessions.py` runtime. The jobs heartbeat calls it every 30 seconds. Each session has a wrapper and a model child. A section count is not a process count. A queued session can have only `BRIEF.md` until a slot opens.

Two paths inflated Ted doing:

- The live reaper published blocked status for terminal sessions but left their cards in Ted doing.
- Mockup approval published a build card directly in Ted doing without enqueueing a session.

The historical `board-live.patch` moved terminal blockers to Needs you. That routing is retired. The current combined package preserves running workers, queued turns, report freshness checks, process identity checks, the six-hour orphan grace period, and conditional API updates, while handing terminal work to Ted.

`mockup-route.patch` puts new approved build cards in Up next until a worker handoff. It preserves existing builds in progress and their refreshes. Publishing art does not launch a worker.

The operational runtime is intentionally excluded from this public repository. These small patches contain only the changed control flow, and they make the installed mini changes reviewable without publishing the full private runtime. Apply them to the current mini runtime after backing up both files. Never apply them on the laptop.

```sh
patch --dry-run "$TED_DECISIONS_ROOT/mockup_route.py" < runner-fix/mockup-route.patch
patch "$TED_DECISIONS_ROOT/mockup_route.py" < runner-fix/mockup-route.patch
python3 runner-fix/mockup_handoff_test.py
```

Set `TED_BOARD_ROOT` and `TED_DECISIONS_ROOT` to the existing mini checkout directories. The tests default to the installed runtime. `BOARD_LIVE_SOURCE` and `MOCKUP_ROUTE_SOURCE` can point at candidate copies before installation. Tests use temporary jobs and replace network publication with local doubles.

After installation, run the existing `board_live.py` entry point, or let its existing 120-second launchd routine reconcile. Read fresh board cards and verify worker identities under the session lock before recounting. Use the board API for live card corrections. No SQL, schema migration, new routine, external send, or new worker is required.

The current Jobs view shows running and queued card workers across all board sections, plus stale cards in Ted doing. A manual move to Up next or Done does not hide an active or queued session. Retained project section headings show counts only for their cards. Untracked processes stay separate. A heartbeat older than two minutes cannot certify a running or queued job. Both views remain explicit when worker data has not loaded.

```sh
node tests/board_status_test.cjs
node tests/board_status_ui.cjs
```

The browser check requires an installed Playwright module and Chromium. It uses intercepted API fixtures and verifies the current Jobs view, manual card moves, polling, stale heartbeats, and mobile and desktop layout. The existing board QA suite covers retained workflows and draft preservation.

The Decide review follow-up described successful-job routing in [FINISHED-JOBS.md](FINISHED-JOBS.md). The current combined package includes that handoff and adds failure recovery and the decision inbox policy.
