# One Ted, one front door

Use [Ted Board](https://getkres.github.io/ted-board/) with your existing private link. Cards hold the conversation, work sessions, and approvals. **Jobs** shows running, queued, and waiting work, plus untracked Codex and Claude processes on the Mac mini. It refreshes every 10 seconds; the mini publishes every 30 seconds.

## Ted's commands

Run these on the Mac mini from `~/ted-ops/ted-board`:

```sh
PY=/Library/Developer/CommandLineTools/usr/bin/python3
$PY card.py new --project 'Ted ops' --title 'Review the queue' --body 'Summarize the open work.'
$PY card.py new --project Bookish --title 'Investigate the build' --body 'Find the blocker.' --engine codex --brief /path/to/BRIEF.md
$PY card.py new --project 'Kres + clients' --title 'Choose a draft' --body 'Review the two options.' --needs-you
$PY card.py say CARD_ID 'The change is ready, and verification passed.'
$PY card.py list --open
```

`--engine claude|codex` starts a session. Omit it to create a card without starting work. `--brief` supplies the worker context. Card IDs accept an unambiguous prefix for `say` and Telegram. Use the full ID when a prefix is ambiguous. A new card uses a generated stable ID.

Sebastian can reply in the card, or message Telegram with `#CARD_ID the next instruction`. Telegram verifies the sender before routing. Other Telegram messages keep their current behavior. Ted's outcome appears in the original card thread.

## Sessions and limits

Each card has one persistent engine session and a private job directory in `jobs/card-CARD_ID/`. Follow-up messages queue behind the current turn. Claude uses `--resume`; Codex uses `exec resume`. A new Codex run is seeded with the card thread and its `REPORT.md`. Resume failures remain visible as failures, and session identity is retained for diagnosis.

At most three card workers run at once. Waiting work is durable across watcher and heartbeat restarts. A worker has a three-hour limit. No long-lived front-door session is needed to keep card work moving. The worker's final answer is delivered by `board_reply.py`, with a delivery token preventing duplicate replies after a retry.

**Open** jumps from a job to its card. **Kill** requests a stop on the mini, checks the process identity, and reports back in that card. Untracked processes have no card thread, so their result is visible in Jobs after the next heartbeat. A stale heartbeat disables Kill until the mini reconnects.

## Approval artifacts

Workers must preserve the existing DATABASE GATE. They prepare exact artifacts instead of applying database changes, sending drafts, or spending money. Write these files in the card's job directory:

- Database: `apply.sql`, `backup.sql`, and `rollback.sql`. Include explicit identity guards and a usable backup and rollback. Missing safeguards remain visible and cause the fresh reviewer to refuse execution.
- Email: `draft-email.json`, including `summary`, exact recipients, subject, body, and execution instructions.
- Spend: `spend.json`, including `summary`, exact payee, amount, currency, and execution instructions.

The card shows **Approve**, **Reject**, and expandable **Exact content**. Approval authorizes only the displayed snapshot. Changed files invalidate it. Approve starts a fresh `claude -p --model opus` reviewer with that exact snapshot. The reviewer re-reads the files, checks the safeguards, and either executes and verifies that action or reports why it is blocked. The reviewer reports `APPLY_OK` only for verified success. Reject returns the decision to the original card session. A reply while waiting supersedes the pending approval before continuing work.

Only one database approval can be pending or undergoing review at a time. Other database proposals wait for that slot. Credentials never belong in an artifact because its exact contents are visible to the board's private-link holder. Keep proposals focused and below 60 KB per file.

## Mini operations

All source, local job state, operational tests, and credentials remain private on the Mac mini. This public repository publishes only the static board and usage documentation.

- `co.ted.board-jobs`: runs `jobs_heartbeat.py` every 30 seconds, consumes controls, dispatches workers, retries replies, and publishes snapshots.
- `co.ted.board-handoff`: runs `handoff.py` at 06:00 in the mini's local timezone, and at load. It writes `~/ted-ops/ted-state/HANDOFF-TODAY.md`, under 80 lines, with Needs you cards, running work, yesterday's completed cards, and pending approvals.
- `co.ted.decisions`: existing watcher routes board receipts to the same session queues. Mockup routing is unchanged.
- `co.ted.telegram`: existing owner-only bot, with `#CARD_ID` routing.

Use the mini's launchd definitions in `~/Library/LaunchAgents`. Do not install these routines on a MacBook. Logs and source deployment instructions live in the private operational directory. Keys stay in the existing secrets file and never appear in commands, Git, or public documentation.
