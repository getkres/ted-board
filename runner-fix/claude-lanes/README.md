# Claude account lanes, staged for Ted review

This bundle prepares the mini dispatcher for separate Claude Max accounts. It is not installed, merged, or deployed. The local configuration defaults to `{"enabled": false}` when the flag file is absent. Codex remains the default engine for new sessions when a caller omits an engine. Explicit engine choices and existing sessions retain their engines.

The operational runtime remains private. `runtime.patch` contains only the lane helper addition and changes to `sessions.py` and `session_worker.py`. `Store.tick()` is the dispatcher, and its existing heartbeat publishes the lane summaries. The existing authenticated heartbeat already accepts these idle job rows and preserves their JSON data. No database migration, RPC change, Edge Function change, new routine, or account login is part of this PR.

## Routing and isolation

New Claude jobs use structured `job_type` when passed to `Store.enqueue(..., job_type=...)` or supplied on the card. Supported types are `design`, `mockup`, `art`, `design_review`, `research`, `analysis`, `review_gate`, and `interactive`. Existing callers without structured metadata classify design, mockup, art, visual, and illustration titles as design, and other explicit Claude jobs as research. Classification examines the title, not prompt text or conversation contents. Review gates use account 3, except design review chains, which stay on account 2. Design and fresh approval review commands explicitly select Opus.

Each conversation pins its lane and exact config directory before launch. Existing Claude resume IDs remain on the main account. Approval review IDs are separate from the card's implementation session ID. Dedicated lanes run one card turn per account at a time, within the existing three-worker total. Usage-limited turns keep their queue ID, resume ID, account, approval digest, and context. They wait on the same lane, while unrelated lanes and Codex work remain eligible. There is no automatic account fallback.

A successful turn is never replayed because of an earlier transient limit signal. A limited approval reviewer without a recoverable resume ID fails with an explicit outcome-review reason, so it cannot repeat an external action in a fresh conversation. Rejected or changed approval snapshots discard their review affinity and resume metadata.

Before a managed launch, the dispatcher verifies the CLI reports a logged-in Max subscription for the exact config directory. It captures and discards account metadata without logging it. The child environment removes inherited API keys, OAuth token overrides, provider selection, custom Anthropic endpoints, and proxy overrides. A missing directory, symlinked account directory, invalid config, wrong authentication method, or failed status check leaves the turn queued. No token files or Keychain entries are read by this code.

The disabled flag preserves the existing main-account launch environment for new unassigned Claude turns. A previously pinned dedicated conversation waits while disabled instead of moving to the main account. Running processes are never interrupted by a flag change. Normal login and the three-step enable procedure are in [SETUP.md](SETUP.md).

## Offline verification

Create a candidate copy from the installed private runtime, with strict patch drift detection:

```sh
python3 runner-fix/claude-lanes/prepare_candidate.py \
  --source "$HOME/ted-ops/ted-board" \
  --dest /tmp/ted-claude-lanes-candidate
TED_LANES_RUNTIME=/tmp/ted-claude-lanes-candidate \
  python3 runner-fix/claude-lanes/test_lanes.py
PLAYWRIGHT_MODULE=/absolute/path/to/playwright \
  node --require ./qa/offline.cjs tests/claude_lanes_ui.cjs
node tests/board_status_test.cjs
python3 scripts/check_data_api_grants.py
python3 -m unittest discover -s tests -p 'test_data_api_grants.py'
```

The Python integration tests use temporary stores, a fake CLI status response, mocked process creation, and forbidden network publication. They exercise the real worker and dispatcher, including approval digest checks and veto dispatch separation. Browser requests are intercepted, and the offline guard refuses unmatched external requests. Lane summary rows use no process controls and do not count as running workers. Usage counters omit private paths, account identities, raw CLI errors, and credentials. Missing plan-wide usage is labeled unavailable.

## Installation after review

On the mini, stop the existing heartbeat and queue-ingestion routines through their current operator controls, and let running workers drain. Do not install while an old dispatcher has imported the old module. Record a timestamped backup of `sessions.py`, `session_worker.py`, `jobs/sessions.json`, and any existing lane helper or flag file. Preserve file permissions. Do not publish those backups.

Rebuild the candidate against the exact installed files with `prepare_candidate.py`, rerun the offline tests, and refuse drift. Copy the reviewed candidate's three Python files into the private runtime together. Copy `SETUP.md` to `~/ted-ops/claude-lanes/SETUP.md`, keep the flag false, and resume the existing routines. Deploy the reviewed static frontend through the normal board release process. No database application is required. Then perform the three setup steps when the accounts exist.

Rollback: set the flag false first, drain active workers, stop the same existing routines, restore the two backed-up runtime files and prior helper, and restore the prior static frontend. Keep account directories intact. Do not overwrite a sessions ledger with a stale backup after it has processed new turns. If any dedicated conversation exists, keep the reviewed lane-aware runtime disabled until Ted explicitly retires those conversations or reconciles their account affinity. The old runtime cannot safely resume their IDs on the main account. Resume routines only after this check.
