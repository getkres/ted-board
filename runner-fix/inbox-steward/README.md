# Card-only inbox steward

The latest Ted review narrows the steward to card moves and overflow review. [Merged PR #41](https://github.com/getkres/ted-board/pull/41) is the sole mockup archive owner, with its enable flag still off. This steward patch removes every mockup planner, verdict rule, study-age rule, supersession rule, mockup read, and archive call. The private read-only judgment hook also lists cards only.

The fail-closed report-only gate is unchanged. All seven earlier decision-protection reproductions remain covered. Only a dated worker report with positive completion evidence and no addressed decision, question, choice, or money signal can move. Approval metadata, recent Sebastian replies, active workers, guided steps, contracts, SQL requests, and send drafts retain their protection.

The fourth review changes the execution structure, without adding card-language exceptions:

- One outer `run_once` exception boundary covers reads, planning, and writes. Every failure stops later actions, revokes data permission, and calls `mark_stale`. There are no stage-specific fetch recovery handlers.
- One shared `can_write(root)` gate checks the kill switch, run root, and a validated snapshot no older than 30 monotonic seconds before each data mutation. The move adapter checks it after the attempt journal write. Direct helper calls without run permission fail closed.
- Recovery uses the same gate with an explicit `stale_only=True` permission bound to the fresh failure observation. That permission can only publish stale local health data. It cannot authorize a move, journal write, or fresh overflow publication. A kill switch vetoes recovery, and a cache-write failure returns a controlled failure without recursion.
- `fetch_cards` validates the raw `call(page=True)` envelope: `ok is True`, a present `cards` list, valid card row identifiers, and no possible 500-card truncation. It no longer uses the lossy `cards()` convenience function. A missing success marker is rejected even if a cards list is present.
- `messages=null` is treated as an empty list during activity calculation and remains ambiguous.

Retained controls:

- The global `steward.disabled` marker makes run_once a zero-work no-op, with zero CLI exit status. It cannot be bypassed with another root. The steward never clears a marker.
- Board snapshot failures persist the first UTC ISO `stale_since`, retain cached review rows, and update `last_attempt_at`. A healthy live refresh clears staleness. Unknown counts are not replaced with zero. Failed dry reads also mark staleness.
- The explicit protected project/section list never moves personal or money project cards in any section, or any project's ted_doing, up_next, done, or killed cards. Matching ignores case and surrounding whitespace. The move recheck honors newly protected scopes.
- Overflow always lists held cards for Ted, including below the cap of 12. It never causes extra moves.

The public bundle contains a focused patch, synthetic tests, baseline hashes, and candidate preparation. Operational runtime files stay private. **The steward tests require `TED_STEWARD_RUNTIME` pointing at a prepared private candidate and do not run in CI.** Existing grants checks remain separate CI checks. No synthetic production transport or private credentials are committed.

```sh
python3 runner-fix/inbox-steward/prepare_candidate.py \
  --source "$HOME/ted-ops/ted-board/steward-runtime/b7a4092689d42418b9fd43a2838a5159bcf8aad0" \
  --dest /tmp/ted-steward-card-candidate
TED_STEWARD_RUNTIME=/tmp/ted-steward-card-candidate \
  python3 runner-fix/inbox-steward/steward_test.py
python3 scripts/check_data_api_grants.py
python3 -m unittest discover -s tests -p 'test_data_api_grants.py'
```

Preparation refuses baseline drift and existing destinations. It copies the two private steward scripts, then checks and applies the patch in the candidate directory. All network boundaries are mocked in tests. Coverage includes the unchanged report-only gate, forbidden mockup access, global and local kill switches, kill activation during successful and failed fetches, a switch after the attempt receipt, incomplete envelopes, null messages, exceptions at planning and writing stages, expired snapshots, direct writer denial, recovery, protected scopes, and scope changes before a move.

After tests pass, install only the verified private scripts on the mini, retain the previous release, and inspect a dry run. Restore the existing 900-second launch agent only after the live snapshot passes the strict contract. An endpoint without `ok: true` is an operational blocker, not a reason to fabricate success or relax validation. Do not clear a disabled marker or enable the separate archive owner. The only mutation API is the board move action. Logs and overflow stay in the private operational checkout. The existing move API's narrow final read/write race remains documented in [STEWARD.md](../../STEWARD.md).
