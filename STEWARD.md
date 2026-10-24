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

A board snapshot failure at the initial read, action recheck, or final refresh writes `stale_since` as a UTC ISO timestamp into `steward-overflow.json`. Existing cached cards and their last successful `at` timestamp are preserved. Repeated failures preserve the first stale time and update `last_attempt_at`. Without an earlier cache, counts stay unknown rather than claiming an empty inbox. A successful live refresh clears `stale_since` to null. Raw transport errors are never copied into review data.

Healthy dry runs do not write the journal or overflow. A failed dry-run read still writes the stale marker so an outage cannot leave old review data silently looking current. The kill switch takes precedence over that write. A snapshot failure returns a nonzero CLI status, and the normal schedule can retry later.

Overflow includes the exact remaining count, excess above 12, oldest excess candidates, the full stale-first list, and an ambiguous list even below the cap. Overflow never authorizes additional moves. Every attempted and confirmed move records card id, from, to, reason, timestamp, and outcome in the private append-only `steward-log.jsonl`.

## Run, verify, and deploy

```sh
PYTHONPATH="$HOME/ted-ops/ted-board" python3 "$HOME/ted-ops/ted-board/steward-runtime/current/inbox_steward.py" --dry-run
PYTHONPATH="$HOME/ted-ops/ted-board" python3 "$HOME/ted-ops/ted-board/steward-runtime/current/steward_review.py"
```

Prepare and test a candidate with the review bundle before installation. Keep the previous private release, run the new release dry first, and point `steward-runtime/current` at the verified release atomically. Preserve the existing launch agent, 900-second interval, private umask, logs, and journal. Verify a fresh scheduled pass after restoring the agent. The routine belongs only on the mini.

The existing move API has no atomic revision precondition. The steward refreshes current card state immediately before each move and refuses changed or newly protected work. The narrow final read/write race remains. No database change, new routine, or archive-owner flag change is needed.
