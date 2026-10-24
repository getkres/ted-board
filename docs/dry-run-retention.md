# Read-only retention inventory

This PR stages a retention tool for job directories, event/log files, and registered Git worktrees. The public repository carries a generic source-and-test patch, an offline harness, and CI. Private operational code and live reports remain local. There is no delete, apply, archive, prune, branch-removal, or scheduling operation.

Proposed ages are 90 days for whole job directories, 30 days for event/log files, and 30 days for worktrees. Age is necessary but insufficient. Job ownership must match the session store, the session must be terminal with no PID or queued turn, its report must begin `LIVE_STATE: done`, and approvals must be resolved. Approval artifacts are retained. Missing reports, missing owners, blocked outcomes, active process working directories, and held claim locks are retained. Reports are inspected through a bounded prefix, without loading their bodies.

A whole job directory is only a review candidate when every scanned entry is old enough and its tree has no excluded or registered worktree subtree. It has `requires_archive: true`; a separate reviewed archive and retention decision is required before removing it. Individual old `.events`, `.log`, and `.jsonl` candidates preserve `REPORT.md`, `BRIEF.md`, and other artifacts. Event candidates are omitted when their whole directory is already a candidate, avoiding double-counting.

Worktree scope is explicit. The main checkout, locked/prunable registrations, active session paths, and observed process working directories are excluded. A candidate must have no tracked changes, untracked files, or ignored files, its HEAD must be an ancestor of the configured known base, and its entire scanned tree must meet the age threshold. Worktrees inside job directories also require a completed job outcome and resolved approvals. No fetch occurs, and an absent base is unknown. Git uses `--no-optional-locks` and disables fsmonitor so inspection does not refresh the index or run a configured fsmonitor hook. A process working-directory snapshot cannot prove that no other process has an open file; that remains a review check before any separately authorized cleanup.

Traversal opens every path component without following symlinks, excludes Documents before descent, reads metadata only except the explicit session store and report prefix, and has a shared entry and elapsed-time budget. It does not inspect vendor model history, credential contents, or arbitrary home directories. A scan error, exhausted budget, or changed ownership snapshot clears all candidates and reports incomplete evidence. Routine heartbeat text changes do not invalidate unchanged ownership. Logical bytes are an estimate, not a promise of APFS recovery, and may double-count hard links.

## Run after extraction in an isolated review tree

```sh
python3 scripts/ops_retention.py \
  --jobs-root /absolute/private/board/jobs \
  --repo /absolute/private/board \
  --worktree-root /absolute/private/board/jobs \
  --worktree-root /absolute/private/board/.worktrees \
  > /absolute/private/retention-output.json
```

Exit 0 means the selected inventory completed, 1 means an incomplete snapshot with no offered candidates, and 2 means invalid or unavailable input. No candidates is a valid result. Roots and candidate paths are included for exact private review, so keep live output outside the public repository. The default limits are 100,000 entries and 20 seconds, with hard maxima of 100,000 entries and 60 seconds. The elapsed-time limit applies to traversal; bounded Git/process evidence calls also have their own ten-second timeouts. There is no scheduler installation.

The session file is read again before reporting. Changes to ownership, status, queue, PID, identity, or approval state invalidate the snapshot. This is a point-in-time proposal, not an atomic lease on future deletion. Before any future cleanup, recheck the exact paths, active processes and open files, dirty/ignored work, pending PRs, archive integrity, required logs, and separately approved retention scope. Never remove a registered worktree with a recursive filesystem delete.

## Verification and rollback

```sh
python3 runner-fix/retention_test.py
python3 scripts/check_data_api_grants.py
python3 -m unittest discover -s tests -p 'test_data_api_grants.py'
```

Thirteen synthetic tests cover unchanged files after inventory, old events versus preserved reports, queued work, pending approvals, blocked reports, unknown owners, live working directories, claim locks, protected subtrees, scan budgets, ownership changes, bounded report prefixes, and clean/dirty worktrees. Git fixtures and files live only in temporary directories. The tool writes only its JSON to stdout. If the script is later installed, rollback means stop calling it and restore the prior helper files. No runtime data is changed by an inventory run.
