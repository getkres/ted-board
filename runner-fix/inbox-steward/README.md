# Card-only inbox steward

The latest Ted review narrows the steward to card moves and overflow review. [Merged PR #41](https://github.com/getkres/ted-board/pull/41) is the sole mockup archive owner, with its enable flag still off. This steward patch removes every mockup planner, verdict rule, study-age rule, supersession rule, mockup read, and archive call. The private read-only judgment hook also lists cards only.

The fail-closed report-only gate is unchanged. All seven earlier decision-protection reproductions remain covered. Only a dated worker report with positive completion evidence and no addressed decision, question, choice, or money signal can move. Approval metadata, recent Sebastian replies, active workers, guided steps, contracts, SQL requests, and send drafts retain their protection.

Additional controls:

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

Preparation refuses baseline drift and existing destinations. It copies the two private steward scripts, then checks and applies the patch in the candidate directory. All network boundaries are mocked in tests. Coverage includes the unchanged report-only gate, forbidden mockup access, global and local kill switches, kill activation during a fetch, outage handling at every read stage, recovery, protected scopes, and scope changes before a move.

After tests pass, install only the verified private scripts on the mini, retain the previous release, inspect a dry run, and restore the existing 900-second launch agent. Do not clear a disabled marker or enable the separate archive owner. The only mutation API is the board move action. Logs and overflow stay in the private operational checkout. The existing move API's narrow final read/write race remains documented in [STEWARD.md](../../STEWARD.md).
