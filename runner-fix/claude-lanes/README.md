# Claude lanes for the current mini runner

This bundle supports the authorized account-2 rollout. It does not log in accounts or create a routine. Review the current PR in a fresh Opus context, merge after green CI, back up the live runtime, install, and verify a real Sonnet turn before marking delivery done. The operator install procedure is in [INSTALL.md](INSTALL.md). Account setup remains three steps in [SETUP.md](SETUP.md).

## Account routing

With `config.json` disabled, dispatch, command construction, worker execution, and snapshots return through separate copies of the pre-PR paths. `Store.enqueue` defaults to `claude`, ordinary Claude commands have no `--model` argument, Sonnet keeps its explicit model, and review turns retain their existing Claude-cap exemption. No config directory is invented: an unset `CLAUDE_CONFIG_DIR` stays absent, and an inherited config directory stays inherited. Every worker environment now removes all `ANTHROPIC_*` variables, including Codex and disabled-lane launches, as required for the plan-only rollout. Already dedicated conversations remain queued rather than crossing to the main account. Malformed configuration also uses this legacy path for main and legacy work, while dedicated conversations wait.

With the flag enabled and account 2 verified as a normal Max login, all new managed Claude and Sonnet conversations use `~/.claude-acct2`. This covers design, art, general worker jobs, research, analysis, and approval reviews. Account 1 remains Ted and interactive work. Multiple independent conversations may run on the same account; each card still has one active turn.

Account 3 is optional. Once `~/.claude-acct3` exists and passes CLI authentication, new research, analysis, and review conversations use it. New design, art, implementation, and general worker conversations remain on account 2. This includes moving new design-review conversations to account 3. Existing conversations keep their original account and exact config directory, even if account 3 becomes available or expires. A pinned conversation waits if its account is unavailable. It never falls back to another account.

Explicit `job_type` metadata is preferred. `Store.enqueue(..., job_type=...)` accepts `design`, `mockup`, `art`, `design_review`, `research`, `analysis`, `review_gate`, `interactive`, `implementation`, and `general`. Legacy callers classify review/gate titles first, design/art titles second, research/analysis titles third, and other titles as general. Explicit `interactive` jobs stay on main, without an invented config override or managed authentication probe. Explicit interactive conversations retain their existing main-account environment. When enabling lanes, an existing managed main-account conversation archives its old ID as `legacy_main_session_id` and starts a fresh dedicated conversation. The old ID is never resumed on another account. This happens only between turns. Titles alone do not mark a job interactive.

## Caps and preserved runner behavior

The current 64-worker global cap and `load > 3 * cpu_count` launch guard are retained. Verified, enabled account 2 raises the aggregate caps to 4 Opus and 16 Sonnet workers across all accounts. Existing main-account workers consume those aggregate slots too. When disabled or unverified, the caps remain 2 and 8. Interactive main-account conversations retain their own 2/8 ceilings even while dedicated accounts are active. Active global, load, and model limits come from `~/ted-ops/ted-board/capacity.json`, which ships with 64 total workers, a load threshold of three times CPU count, 4 Claude workers, and 16 Sonnet workers. Disabled paths do not read that file. Invalid capacity holds managed launches without falling back to main. With lanes enabled, fresh Opus approval reviews count toward the Opus cap, including reviews attached to Codex or Sonnet cards. The disabled legacy path retains its original review-cap exemptions and veto behavior. Veto sends use their existing dedicated worker path.

Managed Claude worker commands select Opus explicitly. Unmanaged Claude commands retain the original command, without a new model argument. Sonnet worker commands select Sonnet explicitly. The worker keeps Ted's twelve-hour timeout and stream parsing for both engines. The current Chrome-only rules, art-process instructions, approval-sync conflict handling, approval digest checks, process-identity checks, retry affinity, review-cancellation fixes, failure publication, bounded recovery, and completion handoff are preserved. The patch is rebased onto the installed failure-safe runner.

The private runtime stays local. `runtime.patch` adds the helper and adds `capacity.json` and modifies `sessions.py` and `session_worker.py`. The existing heartbeat still uses its accepted `claude` wire label for Sonnet model jobs, with `worker_engine: sonnet` as metadata for display. Fresh approval reviews display as Claude/Opus regardless of the card's base engine. No handler deployment or database migration is required for that compatibility. The Jobs UI labels account 2 as shared workers until account 3 verifies.

## Authentication, limits, and usage

The dispatcher probes dedicated-account readiness before taking the store lock. Each lane caches readiness for 60 seconds, both in memory and in private `readiness-design.json` or `readiness-research.json` files beside the flag. These files contain only the lane, config path, CLI path, a timestamp, a readiness boolean, and a fixed failure reason. They contain no account identity or credentials. The cache survives short-lived dispatcher processes. `prepare()` consumes that verified layout without probing again under the lock. Login changes can take up to 60 seconds to be noticed.

Probes use only normal `claude auth status --json`, capture and discard account metadata, and never read or transfer credential files or Keychain entries. Malformed auth responses leave the affected dedicated job queued. Main and interactive jobs do not depend on these probes. Managed environments remove inherited authentication, provider, endpoint, and proxy overrides.

Only turns marked `active_claude_managed: true` record lane usage or retry a limit. A retry requires a typed `rate_limit_event` with status `rejected`, or an event with `error: "rate_limit"`. Free text and a bare `limited` flag cannot trigger it. Limited turns wait on the same account, with their resume ID and approval digest retained. Unknown resets wait five minutes before another attempt. Successful turns are never replayed because of earlier transient signals. A limited approval reviewer without a recoverable resume ID stops for outcome review. Stopped or rejected review contexts cannot contaminate a subsequent Codex turn.

Jobs shows observed dispatcher token counters, typed limit signals, reset times, optional-account readiness, and stale heartbeats. These are not plan-wide balances. Unknown data stays unknown. The summary does not fetch account usage through a proxy or direct OAuth endpoint.

## Offline verification

Always prepare from copies of the current runtime. Use a fresh destination each time:

```sh
python3 runner-fix/claude-lanes/prepare_candidate.py \
  --source /absolute/path/to/current-runtime-copies \
  --dest /absolute/path/to/fresh-candidate
TED_LANES_RUNTIME=/absolute/path/to/fresh-candidate \
  python3 runner-fix/claude-lanes/test_lanes.py
PLAYWRIGHT_MODULE=/absolute/path/to/playwright \
  node --require ./qa/offline.cjs tests/claude_lanes_ui.cjs
node tests/board_status_test.cjs
python3 scripts/check_data_api_grants.py
python3 -m unittest discover -s tests -p 'test_data_api_grants.py'
```

The lane UI check launches installed Google Chrome explicitly. Python model, auth, process, and network calls use local doubles, and browser requests are intercepted. The candidate builder refuses conflicting patch drift instead of forcing it. The full private source and backup copies must never be committed to the public repository.
