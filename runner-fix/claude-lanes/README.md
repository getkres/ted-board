# Claude lanes for the current mini runner

This bundle is staged for Ted review. It does not install itself, log in accounts, enable the flag, or create a routine. The operator install procedure is in [INSTALL.md](INSTALL.md). Account setup remains three steps in [SETUP.md](SETUP.md).

## Account routing

With `config.json` disabled, new Claude and Sonnet turns retain the main-account launch environment and the existing 2 Opus and 8 Sonnet caps. Codex remains the default when a caller omits an engine.

With the flag enabled and account 2 verified as a normal Max login, all new managed Claude and Sonnet conversations use `~/.claude-acct2`. This covers design, art, general worker jobs, research, analysis, and approval reviews. Account 1 remains Ted and interactive work. Multiple independent conversations may run on the same account; each card still has one active turn.

Account 3 is optional. Once `~/.claude-acct3` exists and passes CLI authentication, new research, analysis, and review conversations use it. New design, art, implementation, and general worker conversations remain on account 2. This includes moving new design-review conversations to account 3. Existing conversations keep their original account and exact config directory, even if account 3 becomes available or expires. A pinned conversation waits if its account is unavailable. It never falls back to another account.

Explicit `job_type` metadata is preferred. `Store.enqueue(..., job_type=...)` accepts `design`, `mockup`, `art`, `design_review`, `research`, `analysis`, `review_gate`, `interactive`, `implementation`, and `general`. Legacy callers classify review/gate titles first, design/art titles second, research/analysis titles third, and other titles as general. This classification applies to new worker conversations, including those with an interactive title. Existing main-account resume IDs retain their main-account affinity.

## Caps and preserved runner behavior

The current 64-worker global cap and `load > 2 * cpu_count` launch guard are retained. Verified, enabled account 2 raises the aggregate caps to 4 Opus and 16 Sonnet workers across all accounts. Existing main-account workers consume those aggregate slots too. When disabled or unverified, the caps remain 2 and 8. Legacy main-account conversations retain their own 2/8 ceilings even while dedicated accounts are active. Fresh approval reviews are exempt from worker model caps and do not consume those slots, including reviews attached to Codex or Sonnet cards. They remain subject to the global worker limit and host guards. All capacity values come from ~/ted-ops/ted-board/capacity.json through runner_admission.py, including base 2/8 and verified-account-2 4/16 ceilings. Veto sends retain their dedicated path and do not consume a model slot.

Claude worker commands select Opus explicitly, and Sonnet worker commands select Sonnet explicitly. The worker keeps Ted's twelve-hour timeout and stream parsing for both engines. The current Chrome-only rules, art-process instructions, approval-sync conflict handling, approval digest checks, process-identity checks, retry affinity, and previous review-cancellation fixes are preserved.

The private runtime stays local. `runtime.patch` adds claude_lanes.py, the shared runner_admission.py, and capacity.json, and modifies `sessions.py` and `session_worker.py`. The existing heartbeat still uses its accepted `claude` wire label for Sonnet model jobs, with `worker_engine: sonnet` as metadata for display. Fresh approval reviews display as Claude/Opus regardless of the card's base engine. No handler deployment or database migration is required for that compatibility. The Jobs UI labels account 2 as shared workers until account 3 verifies.

## Authentication, limits, and usage

The dispatcher probes readiness once per tick and verifies the selected account again from the actual job directory before launch. It uses only normal `claude auth status --json`, captures and discards account metadata, and never reads or transfers credential files or Keychain entries. Malformed responses leave the affected Claude job queued while unrelated Codex work can launch. Managed environments remove inherited authentication, provider, endpoint, and proxy overrides.

Limited turns wait on the same account, with their resume ID and approval digest retained. Unknown resets wait five minutes before another attempt. Successful turns are never replayed because of earlier transient signals. A limited approval reviewer without a recoverable resume ID stops for outcome review. Stopped or rejected review contexts cannot contaminate a subsequent Codex turn.

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

The reconciler bundle folds this runtime into one reviewed installation. Do not apply the standalone patch over a reconciler candidate. See [RECONCILER.md](../RECONCILER.md) for the combined cutover and rollback.
