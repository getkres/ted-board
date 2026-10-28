# Read-only retention inventory

This PR stages a retention tool for job directories, event/log files, and registered Git worktrees. The public repository carries a generic source-and-test patch, an offline harness, and CI. Private operational code and live reports remain local. There is no delete, apply, archive, prune, branch-removal, or scheduling operation.

Proposed ages are 90 days for whole job directories, 30 days for event/log files, and 30 days for worktrees. Age is necessary but insufficient. A shared job-state gate requires an exact session cwd, a terminal session (`done`, `failed`, or `killed`), no PID or queued turn, resolved approvals, and a report beginning `LIVE_STATE: done` or `LIVE_STATE: killed`. It loads current card metadata through the existing read-only private `board_client.cards()` call. Every supplied non-null card section/status must be `done` or `killed`; missing, unknown, open, or conflicting card state preserves the job. This same gate protects registered worktrees inside jobs, including cwd matching and card status. A worktree exactly at the jobs root is retained without inferring an owner.

Job and event eligibility uses a case-insensitive file allowlist: `REPORT.md`, `BRIEF.md`, `*.events`, `*.log`, `*.jsonl`, and `*.claim`. Any other file or child directory preserves the job and its event files with reason `unrecognized artifact`. This includes SQL variants, `.bak` and `.dump` files, and backup directories. Child directories are retained conservatively. Report lookup also ignores filename case. Any claim entry preserves the job and its owned worktrees, regardless of case, age, or whether a lock is held. The tool never opens claims to probe locks, and never calls flock or lockf. Reports are inspected through a bounded prefix.

A whole job directory is only a review candidate when every scanned entry is old enough and its tree has no unknown file, excluded subtree, child directory, or registered worktree. It has `requires_archive: true`; a separate reviewed archive and retention decision is required before removing it. Individual old `.events`, `.log`, and `.jsonl` candidates preserve `REPORT.md` and `BRIEF.md`. An unknown artifact or claim prevents these individual candidates too. Event candidates are omitted when their whole directory is already a candidate, avoiding double-counting.

Every configured path must be explicit, absolute, nonempty, and narrower than filesystem root or the user's home. Worktree roots require at least one explicit repository. Resolved repository paths and common Git directories are deduplicated. The first worktree-list entry and `git rev-parse --git-common-dir` identify the main checkout. A worktree scope equal to or containing a main checkout is rejected, including with repeated repositories or a linked-worktree repository argument.

The main checkout, locked/prunable registrations, active sessions, and observed process working directories are excluded. A candidate's top level and common Git directory must match its registration, it must have no tracked changes, untracked files, or ignored files, and its entire scanned tree must meet the age threshold. Any unregistered or nested `.git` entry is unsafe and is not traversed. Only the verified registered worktree's own root `.git` pointer is treated as registration metadata. The job artifact allowlist applies to job/event candidates; registered worktrees retain these separate Git checks.

The merge reference must be in `refs/remotes/`. For every supplied repository, Git checks the reference format and verifies the commit with `rev-parse --verify --end-of-options` before eligibility. A local branch, raw HEAD, option-like value, or missing remote reference fails closed with exit 2. Ancestry uses the verified commit, and reference changes during the scan clear candidates. No fetch occurs. Git uses `--no-optional-locks` and disables fsmonitor. A process working-directory snapshot cannot prove that no other process has an open file; that remains a review check before any separately authorized cleanup.

Traversal opens every path component without following symlinks, excludes Documents before descent, reads metadata plus the explicit session store and report prefix, and has a shared entry and elapsed-time budget. The existing board client supplies read-only card metadata; card bodies are omitted from the evidence snapshot and output. Git performs its own registration, status, and ancestry inspection. Vendor model history and arbitrary home directories are outside scope. A scan error, exhausted budget, changed ownership snapshot, reopened card, or changed merge reference clears all candidates. Routine heartbeat text changes do not invalidate unchanged ownership. Logical bytes are an estimate, not a promise of APFS recovery, and may double-count hard links.

## Run after extraction in an isolated review tree

```sh
PRIVATE_BOARD_ROOT=/absolute/private/board
PYTHONPATH="$PRIVATE_BOARD_ROOT" python3 scripts/ops_retention.py \
  --jobs-root /absolute/private/board/jobs \
  --repo /absolute/private/board \
  --worktree-root /absolute/private/board/jobs \
  --worktree-root /absolute/private/board/.worktrees \
  > /absolute/private/retention-output.json
```

The existing private board client and its existing authentication must be available, either alongside the installed scripts or through the explicit private PYTHONPATH above. The public patch does not contain that client or credentials. Missing provider evidence fails closed. Card calls are read-only; no database mutation is included.

Exit 0 means the selected inventory completed, 1 means an incomplete snapshot with no offered candidates, and 2 means invalid or unavailable input, roots, or merge reference. No candidates is a valid result. Roots and candidate paths are included for exact private review, so keep live output outside the public repository. The default limits are 100,000 entries and 20 seconds, with hard maxima of 100,000 entries and 60 seconds. The elapsed-time limit applies to traversal; bounded Git/process evidence calls also have their own ten-second timeouts. There is no scheduler installation.

The session store, current card metadata, and verified references are checked again before reporting. This is a point-in-time proposal, not an atomic lease on future deletion. Before any future cleanup, recheck the exact paths, active processes and open files, dirty/ignored work, pending PRs, archive integrity, required logs, and separately approved retention scope. Never remove a registered worktree with a recursive filesystem delete.

## Verification and rollback

```sh
python3 runner-fix/retention_test.py
python3 scripts/check_data_api_grants.py
python3 -m unittest discover -s tests -p 'test_data_api_grants.py'
```

Thirty-one tests cover each review item, including backup/SQL variants, casefolded names, unregistered and nested repositories, current and reopened cards, killed jobs, exact worktree ownership, the jobs-root boundary, claim presence without locking, rejected roots, duplicate repositories, main checkout protection, separate Git directories, and invalid or missing remote references. Existing scan, activity, approval, and clean/dirty worktree checks remain covered. Git fixtures and files live only in temporary directories, and the board-client boundary is isolated in tests. The workflow runs on pull requests and uses the repository's actual default branch for push jobs, without a hard-coded branch name. If the script is later installed, rollback means stop calling it and restore the prior helper files. No runtime data is changed by an inventory run.
