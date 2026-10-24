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

The staged watchdog uses a twenty-minute silence threshold, checks process identity before stopping a worker, and queues at most one fresh retry with the last safe tool description prepended to its brief. A second stall holds follow-ups and marks the card blocked. Approval execution, cleared veto sends, uncertain host ownership, and unowned jobs require manual review. Recovery activation is pending. Telegram alerts remain exact approval drafts under the worker's no-Telegram instruction.

The private source, tests, and deployment instructions for card `c-ec9fc8ca0d` are in `~/ted-ops/ted-board/jobs/card-c-ec9fc8ca0d/job-watchdog-private.tar.gz` on the mini. SHA-256: `25e001f9e57ca86c404d9ae91ef99a250b7e5bfb5dec73fc1bf662b12c505d26`. Review that bundle before enabling recovery; merging this documentation does not activate it. The watchdog and installer passed 41 tests, and the existing offline Python suite passed 69 tests with the launchd interpreter. The latest dry-run observed three verified mini workers while the MacBook was unreachable, deferred 10 other cards, and proposed no recovery action. An unavailable remote host is logged separately and does not suppress independently verified mini observations. Ted owns the remaining review and activation.

## Fresh Ted

The round red **fresh ted** button stays at the top-right on every tab. Tap it, then confirm **start a fresh ted?** once. The mini handles the handoff on its next 30-second heartbeat. Progress appears below the tabs. Repeated requests share the same rollover, and failures leave the old chat available.

Ted can set the reminder with `python3 card.py fresh-due on` or `off` on the mini. Monday at 06:00 local time remains a reminder. The revised private worker reads the last assistant message in the transcript identified by `frontdoor/fresh/current.json`, sums `input_tokens`, `cache_read_input_tokens`, and `cache_creation_input_tokens`, and requests a rollover at 60% of the configured model window. `FRESH_TED_CONTEXT_WINDOW` defaults to 200000 tokens, giving a 120000-token boundary. Confirm the actual model window before installation. Automatic requests require an explicitly idle live Ted session and an `idle` or `done` rollover control state. A failed prior request sets the reminder only, so it cannot automatically resume a half-started replacement. Other agents and transcript byte size do not affect the trigger.

A rollover writes a complete `~/ted-ops/ted-state/HANDOFF-TODAY.md`, including every open card, current work, approvals, and decisions waiting on Sebastian. It starts **Ted MM-DD** in the Fictora working directory with Remote Control, and confirms startup through the authenticated readiness marker and registered bridge. Only then does it ask the old chat to save unsaved context, wait up to 120 seconds, refresh the handoff, and rename the old chat. Its conversation is retained. Sebastian receives one Telegram line naming the new chat, and the reminder clears. An explicitly requested manual retry resumes the same request. An uncertain CLI launch requires checking the private log before another launch, so retries cannot silently create extra chats.

`fresh_ted.sh`, its durable state, and `fresh_ted.log` remain private on the mini. The existing jobs heartbeat is scheduled every 30 seconds. The revised worker checks rollover before unrelated card controls, contains automatic request errors so manual requests can still dispatch, confirms requests before suppressing repeats, and keeps the replacement eligible for its own context rollover. Old Ted receives wrap-up only after the replacement is confirmed ready. Failed startup leaves old Ted working. No additional scheduled service is needed.

After the private repair is installed, the same heartbeat publishes a pinned live Ted health record. The board shows an alert on every tab when that session is done, missing, or has no verified live process. It also warns when health is over two minutes old, and clears the alert when the pinned session is healthy again. The normal detection delay is one 30-second mini tick plus one 10-second page poll, provided the heartbeat and board API succeed.

The alert UI shipped in PR #31. The replacement private worker bundle for card `c-fresh-rollover-fix2-1022` is at `~/ted-ops/ted-board/jobs/card-c-fresh-rollover-fix2-1022/fresh-rollover-private.tar.gz` on the mini. SHA-256: `339b40aee15876294268fde7e9126fc2dc64a18371a61c0b69f42253102e4178`. It includes the cumulative patch, source hashes, regression tests, and exact pause, restore, backup, and rollback instructions. The full Python suite passed 99 tests in the isolated worktree with OS network access denied. The four frontdoor fixture status calls are explicitly mocked. Run tests only in that worktree under the documented network sandbox, never in the live directory. The prior alert UI passed mocked mobile and desktop browser checks. Review the replacement bundle before installation; merging UI or documentation alone does not activate the private worker repair. No database migration is required.

**Mockups** is immediately after **All**, with an image icon and a count of unopened images plus unread feedback threads. Opening an image marks it seen on this device. Upload acknowledgments include a **mockups** link. Private deep links accept `#k=YOUR_KEY&tab=mockups`, `tab=jobs`, or a project name, such as `tab=Ted%20ops`. The key stays in the fragment when switching tabs. Do not share these private links.
