# PR 45 review round 2

Binding specification: Ted review of PR 45 dated 2026-10-24, preserved in the private job directory as PR45-REVIEW-1024.md. No installation, service change, database execution, send, spend, or delegated worker.

1. Prove the flag-off leaks and malformed-row, dispatch, lease, cutover, configuration, and partial-feed defects with failing tests.
2. Move the managed implementations to separate reconstructed modules. Every legacy source differs only by one marked guarded redirect. Stage a dedicated mini-only launchd entry. Remove unrelated standalone lane changes from this PR.
3. Fix row quarantine and Ted queue ownership, stable once-only dispatch and lifetime bounds, lease-less cutover refusal, health observations and recovery outside the session lock, safe configuration checks, and partial-card-feed recovery.
4. Prove failure routing stays operational, prepare additive SQL and exact SQL diffs, refresh live hashes, test the reconstructed bundle and committed public export, push, verify CI, and report blocked for Ted re-review.

Ruling: use the review's permitted partial-feed coverage option instead of changing the legacy 500-card API. A truncated feed suppresses remote mutations and new admission while confirmed local managed recovery and lease renewal continue.
Ruling: automatic recovery never kills a process. It requires three separate missed-renewal observations, a dead matching PID, no changing or recent event or log activity, and an absent process group. Only an explicit user stop can signal a matching process, outside the session lock.
