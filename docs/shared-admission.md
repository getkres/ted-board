# Shared admission for the mini

This PR stages one resource gate for board workers, direct command entry points, and model launchd wrappers. It is a private-runtime review packet, with generic source/test patches and synthetic public fixtures. Nothing is installed by merging this public repository. Do not start another routine to run it.

## Policy

Every cooperating caller uses the same installed module and `~/ted-ops/state/shared-admission`. The gate holds one flock across evidence collection, reservation, child creation, and durable state replacement. Proposed defaults are:

- Load admission: measured one-minute load, plus one CPU unit for each existing reservation, plus the proposed run's one CPU unit, must be at most twice the host's CPU count.
- Memory admission: measured available bytes, minus every existing two GiB reservation, minus the proposed run's two GiB reservation, must leave at least the larger of four GiB or 10% of physical memory.
- Each reservation persists while any non-zombie process in its process group survives. An absent leader does not free capacity while its children remain.

On macOS, available memory is free, inactive, and speculative pages from `vm_stat`, using its reported page size. Compressed and wired pages are excluded. Linux CI uses `MemAvailable`. Unknown counters, failed process evidence, corrupt state, non-private directories, symlinks, and incompatible lease policy defer admission. State and lock files are private. No command arguments or environment values are recorded.

Reservations deliberately double-count some measured demand. This is a conservative first policy, not a throughput optimum or a guarantee of a process's peak memory. Measure completion rate, queue age, actual memory peaks, and deferral rate before tuning the central policy. A process can exceed its declared reservation. Existing unwrapped work affects measured pressure but has no reservation, and load averages lag bursts. The board retains its 64-session and provider lane ceilings. The shared gate enforces the twice-core load limit, including reservations. The old silent pre-loop load check is removed so high load produces an observable deferral.

The launcher starts a small helper in a dedicated process group. The helper verifies its own PID, start identity, and committed reservation under the same lock before executing the requested command. Failed persistence cannot run the command. If a supervisor disappears, remaining group members keep the reservation. A live group leader with a different stored start identity proves reuse and releases that stale reservation, including after a reboot. Commands that deliberately detach into another session escape that group; do not route daemonizing commands through this wrapper without a separate ownership design.

Signal forwarding for TERM, INT, and HUP is installed before admission begins, with a no-op before a child is assigned, and the prior handlers are restored on return. SIGKILL cannot be forwarded. In the supplied heartbeat adapter, the existing `perl` alarm remains inside the supervised group and bounds that command to 5400 seconds even if the wrapper is killed. This bound applies to that adapter, not every command: board workers retain their existing twelve-hour model timeout, the queued-task wrapper retains its own timeout, and other direct callers must select an appropriate command timeout.

## Entry points

Apply `shared-admission-tools.patch` only in an isolated review tree. Install `scripts/shared_admission.py` and the explicit package marker in the private board runtime after review. If PR 43 already installed `scripts/__init__.py`, preserve that equivalent package marker rather than applying a duplicate creation blindly.

`shared-admission-sessions.patch` routes the board's worker spawn through the gate. On deferral, it restores the exact queued turn, clears transient veto authority, resets a review to approved, and revalidates the approved artifact on the next tick. Only capacity deferrals stop the dispatch loop. Unavailable evidence leaves that turn queued and continues to later eligible sessions. A hard launch error, including a missing cwd or failed helper `Popen`, fails only its session with the existing could-not-start response. Input preparation is inside the same launch-error boundary. Unexpected programming exceptions are not disguised as deferrals. The worker's existing store-lock identity handshake remains in place. No model, approval execution, or timed send is launched by a refused admission.

Deferrals carry one of three fixed reason codes: `LoadCapacity`, `MemoryCapacity`, or `EvidenceUnavailable`. Evidence errors add only an exception class name, never its message or arguments. The current cause appears in the queued session's `last_line` and stderr. Consecutive attempts for the same turn retain their first timestamp and count. After 15 minutes, the affected existing card receives a blocked live status with the safe cause, once per episode. Failed publication is retried on the next tick. Admission or a hard launch failure clears the episode. This reuses the work card, creates no duplicate card or routine, and makes no Needs you transition.

`codex-heartbeat-admission.patch` wraps the existing model heartbeat runner as lane `launchd`. `company-launchd-admission.patch` wraps the existing explicit queued-task compatibility entry point as lane `launchd`. `direct-browser-admission.patch` wraps the direct browser chore command as lane `direct`. The patches preserve existing prompts, timeouts, task selection, command arguments, and redirections. They propagate the actual exit status, including deferral code 75. They do not enable a schedule or alter launch agent configuration.

Use the same wrapper for other direct Ted commands:

```sh
python3 "$HOME/ted-ops/ted-board/scripts/shared_admission.py" run --lane direct -- command argument
```

Use `--lane launchd` for other reviewed model-producing launchd commands. Health, status, watchdog, queue bookkeeping, and renewal checks stay outside the model admission gate so pressure does not prevent observation. The lane is descriptive, not a different allowance. Production callers must use the default state directory; `--state-dir` exists for isolated tests and is a bypass if used in production.

A deferral does not create a success artifact. Board work stays queued. Direct commands return 75 for capacity or unavailable evidence. A missing executable returns 127, and a non-executable or otherwise failed exec returns 126, with a distinct class-only diagnostic. Helper `Popen` errors retain their original `OSError` for the board's could-not-start handling. When an uncommitted helper does not exit after TERM and a ten-second wait, cleanup sends KILL to its owned group and reaps it. A second bounded wait failure is an evidence deferral, not an uncaught `TimeoutExpired`. The existing launchd wrappers preserve these statuses, and their next-run or catch-up handling must be confirmed during rollout. This gate does not add durable scheduling or claim that a daily job will retry automatically.

## Rollout and rollback

Back up each private source file and its current mode. Confirm that no other admission implementation is installed. Apply every adapter with `patch --dry-run --fuzz=0` against its actual current file. Refuse drift and reconcile it in review. Run the source-specific harness before installation, then install the same reviewed helper and adapters on the mini. Existing running jobs are not killed or retroactively registered. Verify a low-pressure start, a pressure deferral with the same turn still queued, approved-artifact revalidation, a surviving-child reservation, and exit status propagation. Do not execute real approvals or external sends as a smoke test.

Inventory every model-producing entry point, including application scheduler jobs and ad hoc raw CLI calls, before claiming universal coverage. The supplied adapters cover the inspected board dispatcher, direct browser helper, model heartbeat runner, and queued-task compatibility wrapper. Arbitrary raw CLI calls and application-owned scheduler launches remain bypasses until routed through the common wrapper. This is staged code, not a claim of host-wide enforcement.

Rollback restores the backed-up adapters first. Stop or allow admitted children to finish before removing the helper. Retain the state directory and lock inode while any caller uses them. Do not delete a reservation to force a start; investigate its recorded process group.

## Validation

```sh
python3 runner-fix/shared_admission_test.py
python3 runner-fix/shared_admission_test.py --sessions-source /absolute/private/sessions.py
python3 scripts/check_data_api_grants.py
python3 -m unittest discover -s tests -p 'test_data_api_grants.py'
```

The harness applies the tools, dispatcher, and three command patches in a disposable tree with zero fuzz. It checks shell syntax and runs 31 tests, including concurrent lanes, real process groups, identity reuse, failed commits, bounded cleanup, pre-spawn signal handlers, distinct exec statuses, directory replacement, safe reason codes, and aged-card publication and retry. Marker-file tests prove a missing cwd fails only its session, unavailable evidence lets later work run, capacity stops later dispatch, and refused admission never runs the synthetic worker. They do not depend on a swallowed `Popen` assertion. Provider boundaries are isolated, and test workers execute only synthetic local commands. The optional source path copies the actual private dispatcher without publishing or installing it.
