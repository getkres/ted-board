# Claude Max account setup

Run on the Mac mini after Ted reviews and installs the lane patches. Account 1 remains Ted and interactive work. Account 2 handles design, art, and design review, and account 3 handles research, analysis, and review gates. The flag stays off until both new accounts are verified.

1. **Create a separate directory, and log in normally.** Set `lane_account=2` for the design account. Repeat with `lane_account=3` for the research account, using its own Max subscription in the browser. Check the browser account before approving login.

   ```sh
   lane_account=2
   lane_dir="$HOME/.claude-acct${lane_account}"
   mkdir -p "$lane_dir"
   chmod 700 "$lane_dir"
   CLAUDE_CONFIG_DIR="$lane_dir" claude auth login --claudeai
   ```

2. **Verify that account and directory.** Run the command below in the same shell. Confirm `loggedIn: true`, `authMethod: "claude.ai"`, `subscriptionType: "max"`, the expected `configDirectory`, and the intended account identity. The identities for accounts 1, 2, and 3 must differ. Do not copy credentials, configure a proxy, use an API key helper, or export account tokens. The dispatcher strips inherited authentication, provider, and proxy overrides for managed lanes, and repeats this status check before every job. Complete any first-launch setup by opening `CLAUDE_CONFIG_DIR="$lane_dir" claude`, then exit without starting work. In each account's `/usage` screen, leave paid extra usage disabled.

   ```sh
   CLAUDE_CONFIG_DIR="$lane_dir" claude auth status --json
   ```

3. **Enable only after both accounts pass step 2.** This is a local flag file, reread at job boundaries by the existing mini heartbeat. No new routine or daemon is needed. The Jobs tab should show the three lane summaries after the next heartbeat. A new Claude design card should use account 2, and a new Claude research card should use account 3. Existing conversations retain their original account.

   ```sh
   python3 - <<'PY'
   import json
   import os
   from pathlib import Path
   root = Path.home() / 'ted-ops/claude-lanes'
   root.mkdir(parents=True, exist_ok=True, mode=0o700)
   target = root / 'config.json'
   temporary = root / 'config.json.tmp'
   temporary.write_text(json.dumps({'enabled': True}) + '\n')
   temporary.chmod(0o600)
   os.replace(temporary, target)
   PY
   ```

To disable routing, repeat step 3 with `False`. A running session finishes on its current account. Queued dedicated conversations wait until the flag is reenabled, and new unassigned jobs use legacy behavior. Never move an existing session ID to another account. Reauthenticate only with the same directory and account.

Jobs reports observed CLI token totals from this dispatcher's completed turns and typed limit events. These are not subscription balances or percentages. Account 1's interactive usage, usage on other machines, and account-wide plan percentages remain unavailable in this view. Use each account's interactive `/usage` screen for those details. An absent signal stays unknown, and a known limit queues the same conversation until its reported reset. A limit without a reset waits five minutes before another attempt on the same account.

Verified against installed Claude Code 2.1.309 help on 2026-10-22. Official references: [separate account directories](https://code.claude.com/docs/en/authentication#log-in-with-multiple-accounts), [authentication commands](https://code.claude.com/docs/en/cli-reference), and [interactive usage](https://code.claude.com/docs/en/costs#using-the-usage-command).
