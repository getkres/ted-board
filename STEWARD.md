# Inbox steward

The Mac mini runs `co.ted.inbox-steward` every 15 minutes. The standard-library Python runner uses existing private `board_client` and `mockup_client` modules from the operational checkout. The operational scripts, launch agent, transports, and credentials remain local. The public [review bundle](runner-fix/inbox-steward/README.md) contains a focused patch and synthetic regression tests. The runner only calls the existing move and archive actions. It has no SQL, send, spending, or deletion path.

Only report-only messages can move cards out of needs_you. The latest dated worker message must have positive completion evidence and contain no second-person address, question mark, choice or approval words, money or pricing words, daily or monthly rate signal, or dollar amount. Quoted UI copy and URLs receive the same checks. The explicit gate runs before every routing branch, including FYIs. Ambiguity stays in needs_you for Ted.

Eligible worker reports go to up_next with the exact note `Ted review`. Clear completed FYIs go to done. A receipt or welcome message without completion evidence remains for review. Existing approval metadata, decision kinds, recent Sebastian replies and answers, active workers, unanswered choices, and guided steps retain their protection. Existing `card.py new --needs-you` sets decision_kind, which is protected regardless of age. Explicit creation metadata also receives the seven-day protection.

Mockup archival is scoped to the exact project and batch. Version normalization only removes standalone `v2`, `v3`, `final`, and `restart` tags. A replacement must have strictly newer creation times. Complete verdicts include approved, needs_work, scrapped, and legacy picked states. Pending builds, related decision cards, unresolved feedback, and Sebastian feedback or verdicts in the last 48 hours block archival. Only study batch names containing reference lock, inventory, side-by-side, or just-looking evidence qualify for seven-day inactivity archival. A product screen named Inventory does not qualify. The last pin, reply, verdict, and upload count as activity. Archived data is retained by the existing API.

The planner uses a fresh snapshot before each action. Changed actions are deferred. Move and archive APIs do not provide atomic revision preconditions, so a narrow race between the final read and write remains. The steward does not claim a server-side lock. The local lock prevents overlapping steward processes.

Every attempted and confirmed action appends to the private `~/ted-ops/ted-board/steward-log.jsonl`, with card or batch ID, from, to, reason, timestamp, and outcome. An uncertain network outcome is recorded without error bodies. The next pass reads current state before considering a retry. A dry run writes neither the action journal nor overflow.

After a live pass, `steward-overflow.json` contains the actual remaining needs_you count, the excess above 12, the oldest excess candidates, and the full remaining list in stale-first order. The full ranked list and an ambiguous list remain present even below the cap, so Ted can review held cards without an overflow event. Entries include compact, sanitized review context. Overflow never authorizes a move. An empty result clears an earlier overflow file.

## Run and review

Run from an installed release on the mini, with the private transports on PYTHONPATH:

```sh
PYTHONPATH="$HOME/ted-ops/ted-board" python3 inbox_steward.py --dry-run
PYTHONPATH="$HOME/ted-ops/ted-board" python3 inbox_steward.py
PYTHONPATH="$HOME/ted-ops/ted-board" python3 steward_review.py
```

`steward_review.py` is read-only. It prints id, project, title, age, last message, and suggested move for cards and batches needing judgment. It includes protected items with their protection reason. URLs, labeled credentials, and line breaks are removed from printed context. It starts no other workers and sends no notifications.

## Verify and install

```sh
TED_STEWARD_RUNTIME=/absolute/path/to/private/candidate python3 runner-fix/inbox-steward/steward_test.py
python3 scripts/check_data_api_grants.py
python3 -m unittest discover -s tests -p 'test_data_api_grants.py'
```

The tests mock all network boundaries and use synthetic data. Run `node qa/run.cjs` with the static fixture server and Playwright as described in README.md for the existing UI regression suite.

On the mini, prepare and test a candidate with the review bundle, then copy its two Python scripts into a release directory at `~/ted-ops/ted-board/steward-runtime/<commit>/`, then atomically point `steward-runtime/current` to that directory. Keep previous releases for rollback. Preserve the installed `~/Library/LaunchAgents/co.ted.inbox-steward.plist`, ensure `~/ted-ops/logs/` exists, and reload it in the user's GUI domain. The existing agent follows the co.ted Python interpreter, logging, background process, and private umask patterns. The runtime checks ComputerName for mini before executing. Never load it on the MacBook.

Inspect `launchctl print gui/$(id -u)/co.ted.inbox-steward` for the 900-second interval and a zero exit status. Logs are in `~/ted-ops/logs/inbox-steward-launchd.log`.

To stop, boot out the launch agent. To roll back, stop the agent, repoint `current` at a previously verified release, and bootstrap it again. Stopping a routine does not undo board moves or archives. Preserve the action journal for Ted's review. Archive has no unarchive API, so inspect the dry run before the first live pass.
