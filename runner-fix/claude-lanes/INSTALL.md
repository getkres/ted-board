# Account-2 rollout

This is the authorized live rollout, following a fresh Opus review and green CI. Account 2 must report `loggedIn: true`, `authMethod: claude.ai`, `subscriptionType: max`, and its separate config directory. Poll at two-minute intervals while waiting. Do not wait for account 3, copy credentials, use a proxy, enable paid extra usage, or add a routine.

1. Capture the current source and file hashes, prepare a candidate with `prepare_candidate.py`, and run the mocked runtime and board checks. Preserve the currently installed failure, recovery, completion, approval, Chrome, and art rules. Review the PR and this rollout plan with a fresh `claude -p --model opus` context. Fix findings and repeat until the verdict is MERGE, then merge with green CI.
2. Take fresh private backups of `sessions.py`, `session_worker.py`, any existing `claude_lanes.py` and `capacity.json`, the flag, and the ledger. Record which of the four existing dispatcher agents are loaded, then pause those agents during file replacement. Existing worker processes retain their already imported source and finish normally. Do not stop them or copy their resume IDs to another account. Compare the live source hashes again before replacing anything.
3. Install the tested helper, capacity file, sessions module, and worker module together while dispatch is paused. Keep `inbox_policy.py` and `runner_failure_templates.json` unchanged. Capacity is 64 total, load at twice CPU count, Claude 4, and Sonnet 16. All worker environments remove every `ANTHROPIC_*` key. Atomically enable the separate lane flag, run a real Sonnet canary through the installed dispatcher and worker in an isolated diagnostic store, and check its successful result, actual config directory, Sonnet model, and normal Max auth status. Then run the production tick and resume only the recorded agents. Verify the board heartbeat and live files. Done requires a real successful account-2 worker turn.

The diagnostic store prevents canary output from being posted to an unrelated card. Its model call is real. Capture only safe auth fields, paths, booleans, counters, and model names. Never print credentials, identity fields, or raw logs.

## Rollback on any error

Pause the recorded agents, restore the flag and runtime/capacity backups atomically, verify their hashes, and resume only those agents. Stop only a still-running diagnostic worker, using its exact recorded process identity. Preserve other workers and the current ledger; never replace newer ledger entries with a stale snapshot. If production dedicated conversations have already launched, hold their queued continuations before returning to a runner without lane awareness. Preserve their dedicated account affinity and resume IDs for a corrected rollout. Leave the card blocked in Up next with the actual reason, and continue fixing the error.

Account setup remains three steps in [SETUP.md](SETUP.md). No database change or application is part of this rollout.
