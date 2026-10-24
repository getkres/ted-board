# Ted's operator install steps

Run these only after reviewing the PR, on the Mac mini, from the same shell. The preparation job does not execute them. Keep the lane flag false throughout this procedure. Do not use the older cap-3 or cap-16 backups as the rollback source; take a fresh backup of tonight's runner.

1. **Pin the reviewed bundle, and pause the existing routines.** Confirm the commit shown is the one reviewed. Avoid manual `card.py` creation or other dispatcher invocations during the install window. These four labels were read from the installed mini LaunchAgents. No new routine is created.

   ```sh
   umask 077
   lane_bundle="$HOME/ted-ops/ted-board/jobs/card-c-claude-lanes-1022/worktree"
   lane_runtime="$HOME/ted-ops/ted-board"
   lane_install_root="$HOME/ted-ops/claude-lanes/install-$(date -u +%Y%m%dT%H%M%SZ)"
   lane_uid="$(id -u)"
   mkdir -p "$lane_install_root"
   touch "$lane_install_root/paused-labels.txt"
   (
   set -eu
   git -C "$lane_bundle" diff --exit-code
   git -C "$lane_bundle" diff --cached --exit-code
   git -C "$lane_bundle" rev-parse HEAD
   for lane_label in co.ted.decisions co.ted.board-jobs co.ted.board-live co.ted.job-watchdog; do
     if launchctl print "gui/$lane_uid/$lane_label" >/dev/null 2>&1; then
       launchctl bootout "gui/$lane_uid/$lane_label"
       printf '%s\n' "$lane_label" >> "$lane_install_root/paused-labels.txt"
     fi
   done
   )
   ```

2. **Let existing workers drain, without stopping them.** Run this read-only check until it succeeds. It reports only a count. It checks process identity rather than trusting a stale running status in the ledger. Do not call `Store.tick()` to drain, because it can launch queued work.

   ```sh
   python3 - <<'PY_DRAIN'
   import json
   import sys
   from pathlib import Path
   root = Path.home() / 'ted-ops/ted-board'
   sys.path.insert(0, str(root))
   from sessions import alive
   path = root / 'jobs/sessions.json'
   data = json.loads(path.read_text()) if path.exists() else {'sessions': {}}
   active = sum(s.get('status') == 'running' and alive(s.get('pid'), s.get('identity'))
                for s in data['sessions'].values())
   if active:
       raise SystemExit(str(active) + ' active workers remain; wait before installing')
   print('No active card workers remain.')
   PY_DRAIN
   ```

3. **Back up current files and build from copies.** This backs up the live flag without changing it. Keep the ledger backup private. The two source copies must be tonight's files, including the 64-worker cap, load guard, Sonnet engine, Chrome rules, and twelve-hour timeout. If the patch refuses drift, stop and rebase it against the changed files; never force it.

   ```sh
   (
   set -eu
   mkdir -p "$lane_install_root/source" "$lane_install_root/backup"
   for lane_file in sessions.py session_worker.py; do
     cp -p "$lane_runtime/$lane_file" "$lane_install_root/source/$lane_file"
     cp -p "$lane_runtime/$lane_file" "$lane_install_root/backup/$lane_file"
   done
   cp -p "$lane_runtime/jobs/sessions.json" "$lane_install_root/backup/sessions.json"
   cp -p "$HOME/ted-ops/claude-lanes/config.json" "$lane_install_root/backup/config.json"
   if [ -f "$lane_runtime/claude_lanes.py" ]; then
     cp -p "$lane_runtime/claude_lanes.py" "$lane_install_root/backup/claude_lanes.py"
   else
     touch "$lane_install_root/backup/helper-was-absent"
   fi
   python3 "$lane_bundle/runner-fix/claude-lanes/prepare_candidate.py" \
     --source "$lane_install_root/source" --dest "$lane_install_root/candidate"
   TED_LANES_RUNTIME="$lane_install_root/candidate" \
     python3 "$lane_bundle/runner-fix/claude-lanes/test_lanes.py"
   python3 -m py_compile "$lane_install_root/candidate/claude_lanes.py" \
     "$lane_install_root/candidate/sessions.py" "$lane_install_root/candidate/session_worker.py"
   python3 "$lane_bundle/scripts/check_data_api_grants.py" --root "$lane_runtime"
   )
   ```

4. **Install the three reviewed candidate files together while the routines are paused.** Verify the flag is false and the source files have not changed since capture. If either comparison fails, stop and rebuild the candidate. Do not replace an active process's imported code.

   ```sh
   (
   set -eu
   python3 - <<'PY_FLAG'
   import json
   from pathlib import Path
   assert json.loads((Path.home() / 'ted-ops/claude-lanes/config.json').read_text()).get('enabled') is False
   PY_FLAG
   cmp "$lane_install_root/source/sessions.py" "$lane_runtime/sessions.py"
   cmp "$lane_install_root/source/session_worker.py" "$lane_runtime/session_worker.py"
   for lane_file in claude_lanes.py sessions.py session_worker.py; do
     install -m 600 "$lane_install_root/candidate/$lane_file" "$lane_runtime/.$lane_file.next"
   done
   for lane_file in claude_lanes.py sessions.py session_worker.py; do
     mv "$lane_runtime/.$lane_file.next" "$lane_runtime/$lane_file"
   done
   cp -p "$lane_bundle/runner-fix/claude-lanes/SETUP.md" "$HOME/ted-ops/claude-lanes/SETUP.md"
   TED_LANES_RUNTIME="$lane_runtime" \
     python3 "$lane_bundle/runner-fix/claude-lanes/test_lanes.py"
   cmp "$lane_install_root/backup/config.json" "$HOME/ted-ops/claude-lanes/config.json"
   )
   ```

5. **Resume only the routines recorded as paused, with the flag still false.** Do this after successful checks, or after restoring the backup if installation failed. The agents' existing RunAtLoad settings start them after bootstrap. Inspect the next heartbeat through the board, rather than printing raw logs.

   ```sh
   (
   set -eu
   while IFS= read -r lane_label; do
     launchctl bootstrap "gui/$lane_uid" "$HOME/Library/LaunchAgents/$lane_label.plist"
   done < "$lane_install_root/paused-labels.txt"
   )
   ```

6. **Activate separately.** Release the PR's static Jobs UI through the normal board deployment process. Complete [SETUP.md](SETUP.md) for account 2, then let Ted explicitly enable the flag. Account 3 is optional, and its later successful login automatically changes routing only for new research and review conversations. No SQL, schema change, or Edge Function deployment is required by this bundle.

## Rollback

Keep the flag false, pause the same four routines, and repeat the drain check. Before reverting to a runner without lane awareness, inspect the ledger privately for `claude_lane`, `review_claude_lane`, and `active_claude_lane` values of `design` or `research`. If any exist, keep the lane-aware runner disabled until Ted retires or reconciles those conversations. Do not resume their IDs on the main account.

If there are no dedicated conversations, restore `sessions.py` and `session_worker.py` from `$lane_install_root/backup` with `cp -p`. Restore the backed-up helper if present; if `helper-was-absent` exists, remove only the newly installed `claude_lanes.py`. Preserve account directories and tonight's current ledger. Never overwrite the ledger with its stale backup after it has processed newer turns. Keep the flag false, revert the static UI through the normal release process if needed, and resume the same four routines.
