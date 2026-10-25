# Claude Max account setup, account 2 first

Run on the Mac mini with the reviewed runner bundle installed. The account-2 rollout is authorized; account 3 is optional. Account 2 is sufficient for activation. Account 3 can be added later. The installer does not change the flag.

1. **Create a separate directory, and log in normally.** For the account Sebastian just bought, use `lane_account=2`. If Ted already completed that login, proceed to verification. Confirm macOS uses Google Chrome as its default browser before starting the login, and select the intended Max account in Chrome.

   ```sh
   lane_account=2
   lane_dir="$HOME/.claude-acct${lane_account}"
   mkdir -p "$lane_dir"
   chmod 700 "$lane_dir"
   CLAUDE_CONFIG_DIR="$lane_dir" claude auth login --claudeai
   ```

2. **Verify the account and directory.** In the same shell, run the command below. Confirm `loggedIn: true`, `authMethod: "claude.ai"`, `subscriptionType: "max"`, the exact `configDirectory`, and the intended account identity. Account 2 must differ from account 1. Complete any initial CLI setup with `CLAUDE_CONFIG_DIR="$lane_dir" claude`, then exit without starting work. Leave paid extra usage disabled in that account's `/usage` screen. Never copy tokens, configure a proxy, export credential overrides, or share account directories.

   ```sh
   CLAUDE_CONFIG_DIR="$lane_dir" claude auth status --json
   ```

3. **Enable account 2 only after installation and verification.** This is an operator action, separate from applying the bundle. The existing dispatcher rereads the flag at job boundaries. The command below is for Ted to run when ready; the preparation job must not run it.

   ```sh
   python3 - <<'PY_ENABLE'
   import json
   import os
   from pathlib import Path
   root = Path.home() / 'ted-ops/claude-lanes'
   root.mkdir(parents=True, exist_ok=True, mode=0o700)
   temporary = root / 'config.json.tmp'
   temporary.write_text(json.dumps({'enabled': True}) + '\n')
   temporary.chmod(0o600)
   os.replace(temporary, root / 'config.json')
   PY_ENABLE
   ```

After the next heartbeat, new managed Opus, Sonnet, research, art, and review conversations use account 2. Aggregate caps become 4 Opus and 16 Sonnet workers when account 2 verifies, subject to the global 64-worker limit and load guard. Existing main-account conversations keep their original account and conservative 2/8 ceilings.

Later, repeat steps 1 and 2 with `lane_account=3` and a different Max identity. No second flag change is needed. Readiness is cached for 60 seconds. After the next successful account 3 readiness probe, only new research, analysis, and review conversations use account 3. Existing account 2 conversations remain pinned there. If account 3 is absent or fails verification, new research and review conversations continue on account 2; conversations already pinned to account 3 wait for it instead of moving.

To disable future dedicated launches, Ted may repeat step 3 with `False`. Running processes finish on their current account. Queued dedicated conversations wait until reenabled. Account-wide subscription usage and interactive usage are unavailable in the Jobs telemetry; use each account's interactive `/usage` screen for those details.

Official references: [separate account directories](https://code.claude.com/docs/en/authentication#log-in-with-multiple-accounts), [authentication commands](https://code.claude.com/docs/en/cli-reference), and [interactive usage](https://code.claude.com/docs/en/costs#using-the-usage-command).
