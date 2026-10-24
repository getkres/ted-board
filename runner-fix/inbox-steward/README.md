# Card-only inbox steward

The latest Ted review narrows the steward to card moves and overflow review. [Merged PR #41](https://github.com/getkres/ted-board/pull/41) is the sole mockup archive owner, with its enable flag still off. This steward patch removes every mockup planner, verdict rule, study-age rule, supersession rule, mockup read, and archive call. The private read-only judgment hook also lists cards only.

The fail-closed report-only gate is unchanged. All seven earlier decision-protection reproductions remain covered. Only a dated worker report with positive completion evidence and no addressed decision, question, choice, or money signal can move. Approval metadata, recent Sebastian replies, active workers, guided steps, contracts, SQL requests, and send drafts retain their protection.

Execution and GET validation:

- One outer `run_once` exception boundary covers reads, planning, and writes. Every failure stops later actions, revokes data permission, and calls `mark_stale`. There are no stage-specific fetch recovery handlers.
- One shared `can_write(root)` gate checks the kill switch, run root, and a validated snapshot no older than 30 monotonic seconds before each data mutation. The move adapter checks it after the attempt journal write. Direct helper calls without run permission fail closed.
- Recovery uses the same gate with an explicit `stale_only=True` permission bound to the fresh failure observation. That permission can only publish stale local health data. It cannot authorize a move, journal write, or fresh overflow publication. A kill switch vetoes recovery, and a cache-write failure returns a controlled failure without recursion.
- `fetch_cards` delegates to the shared `board_card_snapshot.fetch_cards`, extracted from this validator for the Mockups archive owner. It validates the real GET envelope from `call(page=True, section='needs_you')`: a dictionary, a present `cards` list below 500, valid card row identifiers, no top-level `error` key, and `pod_pulse_error` not true. `{cards: []}` and `{cards: [...], pod_pulse: []}` are valid. The POST action success field is not a GET requirement. It no longer uses the lossy `cards()` convenience function. The runtime patch also creates `board_card_snapshot.py`, which must be installed beside both consumers. The steward preserves its scoped request and `RuntimeError` failure contract; the archive owner uses an unscoped request and `ValueError`. There is one envelope validator.
- The existing full feed includes done cards and caps all sections together at 500. `feed.patch` adds a read-only section filter before that limit while preserving unscoped clients. This prevents done-card history from exhausting the steward's allowance after Ted deploys the scoped handler. Until then, the old handler's complete response is accepted below 500. The client still rejects any 500-row response as potentially truncated.
- `messages=null` is treated as an empty list during activity calculation and remains ambiguous.

Retained controls:

- The global `steward.disabled` marker makes run_once a zero-work no-op, with zero CLI exit status. It cannot be bypassed with another root. The steward never clears a marker.
- Board snapshot failures persist the first UTC ISO `stale_since`, retain cached review rows, and update `last_attempt_at`. A healthy live refresh clears staleness. Unknown counts are not replaced with zero. Failed dry reads also mark staleness.
- The explicit protected project/section list never moves personal or money project cards in any section, or any project's ted_doing, up_next, done, or killed cards. Matching ignores case and surrounding whitespace. The move recheck honors newly protected scopes.
- Overflow always lists held cards for Ted, including below the cap of 12. It never causes extra moves.

The public bundle contains focused runtime and read-handler patches, synthetic tests, baseline hashes, patch hashes, and candidate preparation. Operational runtime files stay private. **The steward tests require `TED_STEWARD_RUNTIME`, and the read-handler tests require `TED_STEWARD_FEED_RUNTIME`, pointing at prepared private candidates. These suites do not run in CI.** Existing grants checks remain separate CI checks. No synthetic production transport or private credentials are committed.

```sh
python3 runner-fix/inbox-steward/prepare_candidate.py \
  --source "$HOME/ted-ops/ted-board/steward-runtime/b7a4092689d42418b9fd43a2838a5159bcf8aad0" \
  --feed-source "$HOME/ted-ops/ted-board/supabase/functions/ted-board" \
  --dest /tmp/ted-steward-card-candidate
TED_STEWARD_RUNTIME=/tmp/ted-steward-card-candidate \
  python3 runner-fix/inbox-steward/steward_test.py
TED_STEWARD_FEED_RUNTIME=/tmp/ted-steward-card-candidate/feed \
  node --test runner-fix/inbox-steward/feed_test.mjs
python3 scripts/check_data_api_grants.py
python3 -m unittest discover -s tests -p 'test_data_api_grants.py'
```

Preparation refuses source or patch drift and existing destinations. It copies the two private steward scripts, then creates the shared snapshot helper while it checks and applies the patch in the candidate directory. The optional `--feed-source` stages the GET handler and its hashed imports under `feed/`, applies `feed.patch`, and never deploys it. Omit that argument for a runtime-only candidate. All network and database boundaries are mocked in tests. Coverage includes real GET response acceptance, degraded response rejection, 600 done cards ahead of two inbox cards, unscoped compatibility, unknown filter rejection, the unchanged report-only gate, forbidden mockup access, kill switches, incomplete envelopes, null messages, exception recovery, expired snapshots, protected scopes, and scope changes before a move.

After tests pass, install only the verified private steward scripts and shared snapshot helper on the mini, retain the previous release, and inspect a live dry run. Keep the existing 900-second launch agent paused until Ted signs off. The scoped GET handler remains a separate reviewed deployment handoff: preserve its current source, apply the prepared read-only change before merging the later PR #44 handler work, and deploy through the existing backend release process only with authorization. No SQL or migration is required. Do not clear a disabled marker or enable the separate archive owner. Logs and overflow stay in the private operational checkout.

PR #36 owns the run boundary, `can_write`, stale cache, fetch validation, and overflow, and merges first. PR #44 owns failure routing, `inbox_policy`, and guarded moves with `expected_section` and `expected_updated_at`. This revision does not change `move_card` or add those parameters. The existing final read/write race and the ownership handoff remain documented in [STEWARD.md](../../STEWARD.md).
