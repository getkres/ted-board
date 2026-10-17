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

## Fresh Ted

The round red **fresh ted** button stays at the top-right on every tab. Tap it, then confirm **start a fresh ted?** once. The mini handles the handoff on its next 30-second heartbeat. Progress appears below the tabs. Repeated requests share the same rollover, and failures leave the old chat available.

Ted can set the reminder with `python3 card.py fresh-due on` or `off` on the mini. It also turns on Monday at 06:00 local time, and when the newest front-door transcript exceeds the context estimate. The private constant is 2.4 MB, estimated as 60% of a 4 MB transcript budget. Transcript size includes tool output and JSON overhead, so this is a reminder estimate, not a token meter. The button glows when due, with a solid bright red under reduced motion.

A rollover writes a complete `~/ted-ops/ted-state/HANDOFF-TODAY.md`, including every open card, current work, approvals, and decisions waiting on Sebastian. It asks the old chat to save unsaved context, waits up to 120 seconds, and starts **Ted MM-DD** in the Fictora working directory with Remote Control. The old chat is renamed only after the fresh prompt confirms startup and the new Remote Control bridge is registered. Its conversation is retained. Sebastian receives one Telegram line naming the new chat, and the reminder clears. A failed retry resumes the same request. An uncertain CLI launch requires checking the private log before another launch, so retries cannot silently create extra chats.

`fresh_ted.sh`, its durable state, and `fresh_ted.log` remain private on the mini. The existing jobs heartbeat performs the weekly and context checks, and dispatches the rollover separately so card jobs continue. No additional scheduled service is needed.

**Mockups** is immediately after **All**, with an image icon and a count of unopened images plus unread feedback threads. Opening an image marks it seen on this device. Upload acknowledgments include a **mockups** link. Private deep links accept `#k=YOUR_KEY&tab=mockups`, `tab=jobs`, or a project name, such as `tab=Ted%20ops`. The key stays in the fragment when switching tabs. Do not share these private links.
