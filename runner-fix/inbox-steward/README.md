# Inbox steward classifier fix

The 15-minute mini routine was healthy, but its classifier treated every question mark, product price, and broad imperative word as an approval. It also let an unrelated statement such as "not live yet" negate a completed report. These checks left worker reports in the decision inbox. Overflow ordering also used rounded display ages, which could rank a newer card ahead of an older one.

The patch narrows request checks to actual action or judgment requests, ignores question marks inside quoted UI copy and URLs, separates product prices from spending requests, and recognizes positive report evidence independently of unrelated negative assurances. Existing approval metadata, decision kinds, recent Sebastian replies, pending choices and guided steps, contracts, SQL requests, and send drafts remain protected. Active workers, conditional merge instructions, and explicit requests to pick or write copy also remain untouched. Overflow uses exact activity timestamps before rounding its display ages. Mockup archive policy and the existing 900-second launch agent are unchanged.

The operational scripts and launch agent remain local. This public bundle follows the existing runner-fix pattern: a small runtime patch, synthetic regression tests, a baseline hash manifest, and an offline candidate preparation helper. It contains no credentials, board snapshots, private card content, or executable production worker.

Prepare a candidate from the retained baseline release, then run its tests with every network boundary mocked:

```sh
python3 runner-fix/inbox-steward/prepare_candidate.py \
  --source "$HOME/ted-ops/ted-board/steward-runtime/b7a4092689d42418b9fd43a2838a5159bcf8aad0" \
  --dest /tmp/ted-steward-candidate
TED_STEWARD_RUNTIME=/tmp/ted-steward-candidate \
  python3 runner-fix/inbox-steward/steward_test.py
python3 scripts/check_data_api_grants.py
python3 -m unittest discover -s tests -p 'test_data_api_grants.py'
```

Preparation refuses source drift and existing destinations. It copies only the two steward scripts into the private candidate directory, then checks and applies the patch there. It does not change the installed release, call the board, launch another worker, or modify a database.

After tests pass on the mini, preserve the current release and install the verified scripts into a new private release directory. Run its dry run and inspect each proposed action before the first live pass. Switch the existing current symlink atomically, and reload the existing launch agent through the normal operator workflow. Retain its 900-second interval, private umask, existing logs, and original release for rollback. No new scheduled agent is needed.

The read-only judgment hook is the private `steward-runtime/current/steward_review.py`. It prints id, project, title, age, last message, and suggested move. The journal and overflow file remain in the private operational checkout. A fresh state check precedes each action, but the existing move and archive APIs still lack atomic revision preconditions. That narrow race remains documented.
