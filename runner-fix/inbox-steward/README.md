# Inbox steward: report-only routing

The live classifier was unsafe: a completion word could route a message to Ted review even when the same message asked Sebastian to choose, approve, or agree to a price. This review fix replaces that positive-word shortcut with a fail-closed admission gate.

A card can leave needs_you only when its latest dated worker message has positive completion evidence and the entire raw message passes every report-only check:

- No second-person address, including you, your, or Sebastian.
- No question mark, including inside quoted UI copy or URLs.
- No choice or approval language, including pick, favorite, prefer, like, option, sign-off, approve, agree, or thoughts. Word families and plural forms are treated conservatively.
- No money or pricing signal, including price, pricing, budget, spend, per day, or monthly. These signals block routing with or without a numeric amount. A bare dollar sign followed by digits also blocks routing, and that protection is restored in the wider card context.

The gate is evaluated before either a Ted-review move or a Done move. Clear completed FYIs, such as "Export completed. No action required.", can still go to Done. A receipt or welcome message without completion evidence, a thank-you message addressing the reader, and missing or undated worker messages remain for Ted. Ambiguity is an intentional hold, with no quoted-text, price-description, or FYI bypass.

Approval metadata, decision kinds, recent Sebastian replies, active workers, pending choices and guided steps, contracts, SQL requests, and send drafts retain their existing protection. Conditional or negated completion language is not completion evidence. Ordinary report numbers, such as a PR number or a count of uploaded screens, are allowed when no money or choice signal is present. Mockup archival and the 900-second schedule are unchanged.

The private overflow file always includes the full stale-first ranked inbox and an ambiguous list, even below 12 cards. Its excess_count and extras retain the cap-of-12 semantics. The read-only judgment hook also lists held messages and their reason. Ambiguous cards are never moved merely to meet the cap.

The operational scripts and launch agent remain local. This public bundle follows the existing runner-fix pattern: a focused runtime patch, synthetic regression tests, baseline hashes, and offline preparation. It contains no credentials or private board snapshots.

```sh
python3 runner-fix/inbox-steward/prepare_candidate.py \
  --source "$HOME/ted-ops/ted-board/steward-runtime/b7a4092689d42418b9fd43a2838a5159bcf8aad0" \
  --dest /tmp/ted-steward-candidate
TED_STEWARD_RUNTIME=/tmp/ted-steward-candidate \
  python3 runner-fix/inbox-steward/steward_test.py
python3 scripts/check_data_api_grants.py
python3 -m unittest discover -s tests -p 'test_data_api_grants.py'
```

Preparation refuses baseline drift and existing destinations. It copies only the two private steward scripts and checks and applies the patch in the candidate directory. Tests mock every network boundary. All seven reported false-positive strings have individual protected-case tests, with broader admission-gate, FYI-bypass, completion-evidence, quoted-question, dollar-amount, and below-cap review coverage.

After tests pass on the mini, preserve the installed release and copy the verified scripts into a new private release directory. Inspect its dry run, then switch the current symlink atomically and restore the existing launch agent. Preserve the 900-second interval, private umask, logs, journal, and previous releases. No new scheduled agent or database change is required.

The existing move and archive APIs lack atomic revision preconditions. The steward refreshes state immediately before an action, and this narrow race remains. The judgment hook is the private `steward-runtime/current/steward_review.py`.
