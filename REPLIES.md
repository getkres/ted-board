# Card conversations

Shipped October 15, 2026. Each card now keeps a conversation between Sebastian and Ted.

- Sebastian's choices, notes, delegation, stuck reports, moves, and completed walkthroughs append a timestamped `seb` message. Choices use their displayed labels. Stuck messages include the human step number in `step`.
- Ted replies append a timestamped `ted` message through the worker-only `ted_reply` action. Replies require nonempty text, allow at most 2,000 characters, and reject Unicode U+2014.
- Cards show the last three messages in append order, with **show all** for the complete conversation. Ted has a small label and marigold border; Sebastian's messages are subtle and right-aligned. All message content renders as text.
- Unread Ted replies add dots to cards and project tab counts, including tabs with zero decisions. **Mark replies read** or **show all** clears the dot on this device. Older Done cards with unread replies remain discoverable, and opening their thread keeps them visible for the current session. Killed cards also signal unread replies in their collapsed section.
- Content sync and explicit answer resets preserve messages. Removing a card with replacement sync removes that card and its thread, as before.

## Backend and operations

The existing public repository boundary remains in place: the static page and documentation are published here. Operational source, tests, private card content, jobs, and credentials remain local on the Mac mini.

Local changes in `~/ted-ops/ted-board`:

- `supabase/migrations/20261016060000_card_messages.sql`: adds `public.ted_board_cards.messages jsonb` with an empty-array default, extends atomic action writes, and adds the service-role-only reply RPC. Applied using the linked Supabase CLI and recorded in migration history.
- `supabase/functions/ted-board/handler.ts`, `domain.ts`, and `index.ts`: validate worker replies, enforce credentials, return messages, and keep the handler testable. The `ted-board` edge function was redeployed.
- `board_reply.py`: reads the existing local secrets file and posts a worker reply without printing keys or response bodies. Usage: `python3 ~/ted-ops/ted-board/board_reply.py <card_id> "text"`.
- `sync.py`: discards locally authored messages so only the server owns conversation history. The database sync function also leaves the messages column untouched.

Local changes in `~/ted-ops/ted-decisions`:

- `board_route.py`: acknowledges each routed action inside its card, explains the next action, and gives Codex, Claude, design, and delegated workers the exact command to report the outcome or blocker. Launch-time instructions also cover existing queued briefs.
- `watch.py`: tracks successful board routing separately from Telegram acknowledgments and retries routing failures before marking receipts seen. Stable decision-based jobs and marked design queue entries prevent duplicate work on retries.
- Worker launch failures produce a blocker reply. If that reply cannot be delivered, the existing dispatch loop retries delivery. No new routine was created.

Database appends lock the card row, preventing simultaneous replies and actions from overwriting history. Replies leave the card's section, answer, and retention timestamp unchanged.

## Verification

- 9 Deno validation and HTTP handler tests.
- 13 Python CLI, sync, routing, retry, deduplication, and launch-outcome tests.
- 12 browser scenarios, including thread expansion, safe text rendering, unread persistence, zero-count tabs, and older Done cards. Mobile layout was visually inspected.
- Transactional SQL assertions exercised all six Sebastian actions, timestamps, step numbering, reply permissions, invalid replies, and sync preservation, then rolled back.
- Live backend checks confirmed all six action messages, answer-reset preservation, and existing access controls. Test receipts and temporary cards were removed, and the existing watcher was restored.
- Live worker checks rejected page-key impersonation and invalid replies, accepted the 2,000-character boundary, preserved messages through sync, and retained all eight concurrent replies.
- The CLI posted exactly `test reply` to `fx-xcode-mini`. GET returned the message, and cleanup deleted that exact new message without restoring a stale snapshot or changing the card's state.

Read markers are local to each browser or device. New replies appear when the board refreshes. No historical actions were backfilled.
