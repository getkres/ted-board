# Card inbox steward

The Mac mini runs `co.ted.inbox-steward` every 15 minutes. The steward only moves cards through the existing board move API, appends action receipts to its private journal, and maintains overflow review data. Its read-only judgment hook prints ambiguous cards.

**PR #41 is the sole owner of mockup archiving.** That merged helper remains behind its own disabled flag. The steward does not read mockups, import the mockup transport, evaluate verdicts or study age, detect superseded batches, or issue archive requests. This change does not install or enable PR #41. [Archive owner](https://github.com/getkres/ted-board/pull/41).

The operational scripts and launch agent remain local. The [public review bundle](runner-fix/inbox-steward/README.md) contains a focused patch, baseline hashes, offline candidate preparation, and synthetic tests. The steward suite requires `TED_STEWARD_RUNTIME` to point at a prepared private runtime and does not run in CI.

## Card routing and protected workspace

The existing fail-closed gate is unchanged. The latest dated worker message must have positive completion evidence and no second-person address, question mark, choice or approval language, money or pricing signal, daily or monthly rate signal, or dollar-digit amount. Quoted copy and URLs receive the same checks. Eligible reports move to up_next with `Ted review`; eligible completed FYIs move to done. Every ambiguous message remains for Ted. Existing approval, recency, active-worker, guided-step, contract, SQL, and send protections remain.

The explicit `PROTECTED_SCOPES` list is checked before classification and again during the move recheck. Project and section names are case-insensitive, with surrounding whitespace ignored. A wildcard matches every value:

| Project | Section |
| --- | --- |
| personal | * |
| money | * |
| * | ted_doing |
| * | up_next |
| * | done |
| * | killed |

These conservative project defaults use the existing personal and money board projects. Protected cards remain visible in review data, but the steward never moves them, even when their message is a clear completion report. Other projects are eligible only in needs_you and only after every existing gate passes.

## Disable and freshness

If `~/ted-ops/ted-board/steward.disabled` exists, `run_once` performs no network calls or writes. The CLI exits zero without creating a lock. An alternate `--root` cannot bypass the global switch, and a disabled marker in that alternate root is honored too. The steward never clears either marker. It rechecks the switch after reads and before further actions.

`fetch_cards` reads the raw board envelope through `board_client.call(page=True, section='needs_you')`. The GET contract is `{cards, pod_pulse}`. Validation requires a dictionary with a present `cards` list containing fewer than 500 valid card objects with ids, projects, and sections, no top-level `error` key, and no `pod_pulse_error` flag set to true. GET validation does not depend on the POST action success field. A missing list, malformed row, explicit error, degraded pulse, or possible truncation is an incomplete snapshot. It never uses `cards()`, whose missing-key default can conceal degraded responses as an empty inbox. Null message lists are treated as empty and remain ambiguous.

The existing unscoped GET includes every section, including done, and limits the complete result to 500 rows. The companion `feed.patch` adds a read-only `section=needs_you` filter before that limit. Unscoped clients retain their existing response. The steward requests the scope, so once Ted deploys that handler patch, done-card growth cannot consume its inbox allowance. Before deployment, an older handler may ignore the filter; its complete result is still safe below 500. A 500-row result is always rejected because completeness is unknown. Do not simply raise the client threshold against a server that still truncates at 500. Applying the scoped handler is part of the delivery handoff.

`run_once` has one outer exception boundary for the complete read, plan, journal, move, and overflow pipeline. Any exception stops later actions, revokes snapshot permission, and calls `mark_stale`. This replaces the earlier stage-specific fetch handlers. An uncertain move leaves its attempt receipt, fails the run, and requires a new snapshot on the next run. Confirmed move counts survive a later journal or refresh failure.

Every write uses the shared `can_write(root)` gate immediately before mutation, including the journal, lock creation, move API call, overflow temporary file, and atomic replacement. Data writes require a validated snapshot observed within 30 monotonic seconds and the same run root. Helpers cannot write outside a run. A move rechecks this gate after its attempt receipt. A disabled switch or expired snapshot stops it there.

The exception boundary grants one narrow recovery permission: `can_write(root, stale_only=True)` checks a fresh failure observation and the kill switch, and permits only stale overflow health data. It does not authorize journal entries, card moves, or fresh overflow publication. This explicit recovery mode allows an outage to be recorded when no complete board snapshot exists. The kill switch vetoes recovery too, including when it appears during a failed fetch or before atomic file replacement.

Stale recovery writes `stale_since` as a UTC ISO timestamp into `steward-overflow.json`. Existing cached cards and their last successful `at` timestamp are preserved. Repeated failures preserve the first stale time and update `last_attempt_at`. Without an earlier cache, counts stay unknown rather than claiming an empty inbox. A successful live refresh clears `stale_since` to null. Raw transport errors are never copied into review data. If the cache itself cannot be written, the run returns failure with `stale_write_failed`, without recursive recovery.

Healthy dry runs do not write the journal or overflow. A failed dry-run read still writes the stale marker so an outage cannot leave old review data silently looking current. The kill switch takes precedence over that write. A snapshot failure returns a nonzero CLI status, and the normal schedule can retry later.

Overflow includes the exact remaining count, excess above 12, oldest excess candidates, the full stale-first list, and an ambiguous list even below the cap. Overflow never authorizes additional moves. Every attempted and confirmed move records card id, from, to, reason, timestamp, and outcome in the private append-only `steward-log.jsonl`.

## Run, verify, and deploy

```sh
PYTHONPATH="$HOME/ted-ops/ted-board" python3 "$HOME/ted-ops/ted-board/steward-runtime/current/inbox_steward.py" --dry-run
PYTHONPATH="$HOME/ted-ops/ted-board" python3 "$HOME/ted-ops/ted-board/steward-runtime/current/steward_review.py"
```

Prepare and test a candidate with the review bundle before installation. The manifest records source hashes and patch hashes, and optional feed preparation stages the scoped handler without deploying it. Keep the previous private release, run the new release dry first, and point `steward-runtime/current` at the verified release atomically. Preserve the existing launch agent, 900-second interval, private umask, logs, and journal. Keep scheduling paused until Ted signs off, then verify a fresh scheduled pass. The routine belongs only on the mini.

PR #36 owns the run boundary, `can_write`, stale cache, fetch validation, and overflow, and merges first. PR #44 owns failure routing, `inbox_policy`, and the guarded move using `expected_section` and `expected_updated_at`. This patch leaves `move_card` unchanged and adds no revision-guard parameters. The current steward refreshes card state before each attempt, refuses changed or newly protected work, and checks write admission before the API call. The final read/write race remains for PR #44 to close. No database change, new routine, or archive-owner flag change is needed.
