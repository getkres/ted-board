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
- `co.ted.job-watchdog`: monitors card sessions every five minutes on the mini. It is installed in dry-run mode while the private recovery bundle awaits review. It checks event files and process activity on both hosts, and logs decisions to `~/ted-ops/logs/job-watchdog.log`.
- `co.ted.board-handoff`: runs `handoff.py` at 06:00 in the mini's local timezone, and at load. It writes `~/ted-ops/ted-state/HANDOFF-TODAY.md`, under 80 lines, with Needs you cards, running work, yesterday's completed cards, and pending approvals.
- `co.ted.decisions`: existing watcher routes board receipts to the same session queues. Mockup routing is unchanged.
- `co.ted.telegram`: existing owner-only bot, with `#CARD_ID` routing.

Use the mini's launchd definitions in `~/Library/LaunchAgents`. Do not install these routines on a MacBook. Logs and source deployment instructions live in the private operational directory. Keys stay in the existing secrets file and never appear in commands, Git, or public documentation.

The private integrator ledger records the dedicated card reconciler as the sole managed recovery owner. The installed watchdog timer passes `--probe` on its existing five-minute interval. Keep legacy recovery disabled alongside the managed owner, and do not deploy an older standalone watchdog archive over this runtime.

Readback at October 25, 12:26 UTC confirmed the dedicated owner and watchdog timer loaded, both last exiting zero, with no reconciliation coverage defects. The private integrator ledger records exact runtime hashes and a 615-second quiet observation from October 25, 06:58 to 07:08 UTC. That observation establishes the recorded quiet-window checks, and does not claim an exercised worker recovery.

The historical standalone source and tests for card `c-ec9fc8ca0d` remain in `~/ted-ops/ted-board/jobs/card-c-ec9fc8ca0d/job-watchdog-private.tar.gz` on the mini. SHA-256: `4347f9748c0dee9ffa5f248ba8700ff30d4c35e4448ffa98b465ff96d9f097a5`. This archive is historical evidence. Current deployment and recovery behavior must be reviewed against the managed source and private integrator ledger.

## Fresh Ted

The round red **fresh ted** button stays at the top-right on every tab. Tap it, then confirm **start a fresh ted?** once. The mini handles the handoff on its next 30-second heartbeat. Progress appears below the tabs. Repeated requests share the same rollover, and failures leave the old chat available.

Ted can set the reminder with `python3 card.py fresh-due on` or `off` on the mini. Monday at 06:00 local time remains a reminder. The staged context repair queues a rollover when the transcript identified by `frontdoor/fresh/current.json` reaches 2,400,000 bytes, estimated as 60% of a 4 MB transcript budget. Other agents do not affect that selection. Transcript size includes tool output and JSON overhead, so this is a context estimate, not a token meter. Context requests use the existing request operation; setting the due flag alone does not start a rollover.

A rollover writes a complete `~/ted-ops/ted-state/HANDOFF-TODAY.md`, including every open card, current work, approvals, and decisions waiting on Sebastian. It asks the old chat to save unsaved context, waits up to 120 seconds, and starts **Ted MM-DD** in the Fictora working directory with Remote Control. The old chat is renamed only after the fresh prompt confirms startup and the new Remote Control bridge is registered. Its conversation is retained. Sebastian receives one Telegram line naming the new chat, and the reminder clears. A failed retry resumes the same request. An uncertain CLI launch requires checking the private log before another launch, so retries cannot silently create extra chats.

`fresh_ted.sh`, its durable state, and `fresh_ted.log` remain private on the mini. The existing jobs heartbeat is scheduled every 30 seconds. The staged repair moves rollover checks ahead of unrelated card controls, confirms requests before suppressing repeats, and leaves the replacement session eligible for its own context rollover. No additional scheduled service is needed.

After the private repair is installed, the same heartbeat publishes a pinned live Ted health record. The board shows an alert on every tab when that session is done, missing, or has no verified live process. It also warns when health is over two minutes old, and clears the alert when the pinned session is healthy again. The normal detection delay is one 30-second mini tick plus one 10-second page poll, provided the heartbeat and board API succeed.

The private worker patch, 18 new Python regression tests, mocked browser test, source hashes, backup instructions, and rollback instructions for card `c-fresh-rollover-1022` are in `~/ted-ops/ted-board/jobs/card-c-fresh-rollover-1022/fresh-rollover-private.tar.gz` on the mini. SHA-256: `553cfc564a7b9c605a67b0dca9cc5a25524a63311c649412c67cc4f67e4046e5`. The full Python suite passed 87 tests, and the alert passed browser checks at mobile and desktop sizes. Review the bundle before installing the private changes. This public PR contains the alert UI and documentation; merging it alone does not activate context rollover. No database migration is required.

**Mockups** is immediately after **All**, with an image icon and a count of unopened images plus unread feedback threads. Opening an image marks it seen on this device. Upload acknowledgments include a **mockups** link. Private deep links accept `#k=YOUR_KEY&tab=mockups`, `tab=jobs`, or a project name, such as `tab=Ted%20ops`. The key stays in the fragment when switching tabs. Do not share these private links.
