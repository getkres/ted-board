# Opt-in operational safeguards

These standard-library tools are staged for review. Adding them to the repository does not install them, rotate a live log, create a routine, send an alert, or change worker limits. Keep inventories and machine evidence outside this public repository. Run operational checks on the Mac mini.

The public repository carries [a source-and-test patch](../runner-fix/safeguard-tools.patch), an offline test harness, and this documentation, following the existing `runner-fix` convention. Executable operational files remain local. Apply the patch only in an isolated review tree to inspect or test it. The examples below refer to that extracted tree. Applying the separate watchdog integration to the private runtime is a later rollout.

## Read-only preflight

Create a private JSON inventory with mode `0600`. Use canonical paths and safe lowercase labels. Include only checks whose scope you deliberately select. The example is synthetic:

```json
{
  "disks": [{"name": "data", "path": "/private/tmp", "min_free_gib": 50}],
  "logs": [{"name": "worker", "path": "/private/tmp/example.log", "max_mib": 50}],
  "heartbeats": [{"name": "runner", "path": "/private/tmp/runner.ok", "max_age_seconds": 600}],
  "expiries": [
    {"name": "sign_in_secret", "expires_at": "2027-04-06T00:00:00Z", "warn_days": 60},
    {"name": "oauth_refresh", "expires_at": null}
  ],
  "cleanup_candidates": [{"name": "old_cache", "path": "/private/tmp/old-cache", "max_entries": 50000}]
}
```

```sh
python3 scripts/ops_preflight.py --inventory /absolute/private/inventory.json
```

Exit `0` means every configured check is healthy, `1` means attention or unknown evidence, and `2` means an invalid or unreadable inventory. Output contains configured labels and numbers, without paths, log contents, or credential values. An empty inventory cannot pass. Missing evidence and a heartbeat more than 60 seconds in the future remain unknown. Inventory timestamps must include timezones. The tool refuses Documents paths and custom symlinks, including symlink ancestors. Standard macOS `/var`, `/tmp`, and `/etc` aliases are accepted only when they resolve to their standard `/private` targets.

The cleanup mode only measures explicitly supplied candidates. It has no delete or apply option. It skips Documents directories and symlinks, opens path components without following links, stops at the entry budget, and reports incomplete scans or filesystem errors as unknown. Counts are logical file bytes, which can double-count hard links, omit sparse-file savings, and differ from reclaimable APFS space. Directory timestamps do not establish that a worktree is unused. Before any separate cleanup, inspect Git status, active jobs, open files, backup coverage, and ownership. Do not remove model history or worktrees solely because this tool reports their size.

Expiry checks consume operator-recorded dates only. They do not decode JWTs, refresh OAuth, read API keys, or prove that a credential is valid. Unknown expiry stays unknown. Many refresh tokens expire through revocation, inactivity, or provider policy, so use a separate authenticated health probe when authorized. A fresh output log is also not proof of a successful run: point heartbeat checks at an artifact written only after the actual success condition. Select expected intervals per job, including overnight gaps. These tools do not yet provide an external dead-man monitor.

## Bounded JSON logs

`scripts.bounded_json_log.append_rows(path, rows, max_bytes=5_000_000, backups=3)` uses the same standard-library rotation approach as existing messaging workers, plus a shared flock around validation, rotation, and append. Files and the lock are mode `0600`. Oversized records, oversized existing logs, numeric archives outside the selected retention, symlinks, and hard-linked files are rejected. Callers must sanitize records before passing them in. Retention removes the oldest archive, so preserve required audit records separately before enabling it.

All writers to the selected log must migrate together. Do not rotate launchd stdout/stderr, active vendor transcripts, or logs with a writer holding an old descriptor. Their retention needs a separate process-aware change. The parent directory must already exist, be private, and be trusted. This helper is for Unix hosts, including the mini. The lock file remains in place; do not unlink it during operation.

The private watchdog integration is staged in [bounded-watchdog-log.patch](../runner-fix/bounded-watchdog-log.patch). Both normal and exception-path writes use the helper's own lock. Logger validation, import, or filesystem failures emit only a fixed stderr marker and never escape `log()`. If stderr also fails, monitoring still continues. The fallback does not append through refused symlinks or hard links, and it does not echo records or exception text. A lazy helper import keeps standalone remote probes usable without the helper package. Install the explicit `scripts/__init__.py` with both helper modules. This patch changes logging only; the live watchdog's recovery authority remains unchanged.

## Rollout and rollback

After review, Ted can prepare a timestamped backup of the private watchdog and its log, preserve any oversized existing archives separately, dry-run the patch with `--fuzz=0` against the then-current source, install the explicit package and both generic scripts, and run the offline tests. Keep `~/ted-ops/logs` at mode `0700`; keep individual logs and locks at `0600`. Refuse source drift. Coordinate a quiet transition so no old writer remains, then let the existing mini invocation pick up the reviewed code. This card did not execute that rollout, create a launch agent, or run live recovery. Roll back by restoring the backed-up watchdog; retain the helper and archives until all new writers have stopped.

For monitoring, first run a private inventory manually. Review each success artifact before integrating exit codes into the existing mini health routine. External recovery monitoring, spend shutoffs, legal sign-off, and provider quota decisions remain separate. Local warning output is not a delivered external alert.

## Verification

```sh
python3 runner-fix/bottleneck_safeguards_test.py
python3 runner-fix/bottleneck_safeguards_test.py --watchdog-source /absolute/private/job_watchdog.py
python3 -m unittest discover -s tests -p 'test_data_api_grants.py'
python3 scripts/check_data_api_grants.py
```

The harness applies the tools patch and the watchdog patch with zero fuzz in a disposable directory, then runs 25 tests. CI uses a public contract fixture containing the original logging surface and an offline probe, without private recovery code. The optional private-source invocation copies the actual watchdog into the same disposable tree, imports the patched module, exercises refused paths, and executes only `--probe` against an empty temporary jobs directory. It never runs enforcement, imports production sessions, contacts providers, or changes production state. Tests cover oversized records and logs, hard links, symlink parents, old archives, missing imports, failed stderr, private JSON output, concurrent writers, concurrent directory replacement, FIFO inventory refusal, and retention reductions. Existing grant checks stay separate.

The private-source harness also accepts the reviewed watchdog after the reconciler redirect. It copies only that source's adjacent `reconciler_gate.py` dependency, and forces the disposable gate off before importing or probing logging. This tests the legacy logging fallback without invoking managed recovery or using production configuration. In managed mode the watchdog entry remains a compatibility probe and delegates recovery ownership to the dedicated reconciler; this logging patch does not add a second recovery owner.
