# Mockup auto-archive handoff

Finished batches should leave the Mockups wall without requiring another upload. This adds a private helper and a small hook to the mini's existing heartbeat. It uses the existing worker-authenticated archive action, preserves pins, images, verdicts, and Storage, and changes no browser tab or database schema.

The runtime is intentionally excluded from the public repository. The focused patches follow the existing runner-fix convention. They are staged for Ted review and have not been installed or enabled.

## Policy

An active batch is the exact project and batch pair, with at least one non-archived frame. The pass uses these reasons, in order:

1. `all_reviewed`: every active reviewable frame has `approved`, `scrapped`, or `picked`. Legacy `status=picked` also counts when there is no explicit verdict. Any linked card outside done or killed keeps the whole batch visible while it is being built, even if a newer batch could otherwise establish stale supersession. An explicit `card_id`, an exact `build approved: <batch>` title, or a card whose own `batch` equals the batch links regardless of the card's project. A `mockup ID: <id>` body reference links only within the same project. `needs_work` is waiting for a new round and does not satisfy this reason; it can archive only through a terminal linked card or stale supersession. At least one reviewable frame is required. Titles labeled `Notes`, `Notes: ...`, `Notes, ...`, or `Who made and checked this` are informational, including those labels after a colon, such as `Hair v13: Notes, what changed and why`. A frame titled `Notes app screen` remains reviewable. Informational frames are archived with the batch.
2. `linked_card_done` or `linked_card_killed`: the linked card is terminal. Exact `build approved: <batch>` title links can establish completion only in the same project. Explicit `card_id` links retain their completion behavior across projects because the frame identifies its own card. Cross-project title and batch metadata matches remain conservative blockers while their cards are active, and they never establish terminal completion. A same-project card `batch` field or `mockup ID: <id>` body reference is narrower: it can qualify the batch only when every active reviewable frame has a recognized verdict (`approved`, `needs_work`, `scrapped`, or `picked`), with at least one reviewable frame. A done card mentioning one reviewed frame cannot hide the unreviewed remainder. Informational title cards do not require verdicts. There is no fuzzy card-title matching. If several cards link the batch, all must be done or killed. A malformed non-null frame `card_id` rejects the snapshot. A missing explicit `card_id` holds the batch under every reason, including all-reviewed verdicts and stale supersession. A missing card does not imply completion.
3. `stale_superseded`: no verdict activity for at least five full days, plus a strictly newer batch in the same project with the same prefix. Any linked card outside done or killed blocks this reason, including batches with unreviewed or needs-work frames. An active build cannot be archived through stale fallback. A prefix is the normalized descriptive name before a version, round number, or date suffix. For example, `Home`, `Home v1`, and `Home v2` share a prefix; `Home icons v2` does not. Colon descriptions remain part of the prefix. Case, punctuation, and whitespace are normalized. Archived newer batches also establish supersession.

Every reason requires the latest frame creation time and every known verdict activity timestamp to be at least 24 hours old. Activity includes `verdict_change.at`, `verdict_at`, and legacy `picked_at`, across the entire batch, including informational and already archived frames. A batch with no verdict activity uses its creation time. Missing creation times, invalid activity times, or verdicts without a known activity time keep the batch visible.

The card snapshot fails closed on the initial read and every pre-apply recheck. Both reads use the shared `board_card_snapshot.fetch_cards` extracted from PR 36's steward fetch, with the real `board_client.call(page=True)` envelope and no section filter. The result must be a dictionary with no `error` key, `pod_pulse_error` not true, and a present, nonempty `cards` list containing fewer than 500 rows. A 500-row response might be truncated, so it is rejected along with larger responses. Invalid card row identifiers also reject the snapshot. An invalid response raises `ValueError` before an archive attempt or archive call; it never becomes an empty card list. The shared fetch defaults to `allow_empty=False`, so an empty board feed cannot make reviewed batches appear unlinked. Only the steward opts in with `allow_empty=True`, because its scoped `needs_you` inbox can legitimately be empty. Auto-archive never opts in.

A missing shared snapshot module also produces the CLI's sanitized failure message and a nonzero exit status, without a traceback.

Card bodies must be strings or null. An invalid body rejects the snapshot with `ValueError`, so the CLI returns its sanitized failure message without exposing a regex type error.

The existing mockup GET feed includes `ted_mockup_pins`. Every reason skips a batch if any of its frames has an unresolved pin, including pins on informational or already archived frames. Resolved pins and pins belonging to other batches do not block it. A missing or malformed pin feed fails closed before any archive write.

Staleness adds the five-day inactivity requirement to the same creation and verdict clocks. A newly added frame resets the clock. A superseding batch's first frame must be newer than the old batch's last frame. Ambiguous naming and links stay visible for manual handling.

Every rule also waits for any active Undo window to expire. Dry-run records `would_archive` with the reason and evidence. Apply rereads the mockup, pin, and card snapshots immediately before each archive, skips any changed decision, and writes a durable `archive_attempt`.

The archive request uses only the explicit active frame IDs from that recheck, in lists of at most 500 IDs to respect the existing API limit. An upload arriving after the last GET is never included or archived unseen. Each receipt must confirm exactly the length of its requested ID list, excluding already archived rows. The log records `archived` only after every request succeeds. A failed later request records `archive_failed` and the confirmed partial count. Errors record only their type, with no raw transport details. One failed batch does not stop later batches. A read or audit-log failure stops the pass; the heartbeat catches the failure and keeps its existing work intact.

The existing API cannot condition an ID archive on unchanged verdict or pin state. A verdict or pin can still arrive on one of those known frames after the final GET. Eliminating that interval atomically would require a separately reviewed backend change. No such backend change is included here.

## Heartbeat cadence and log backoff

The enabled heartbeat runs the archive pass at most once per ten minutes. Its last start time is persisted before any network read, so failed passes also consume the interval. The exact ten-minute boundary permits a new pass. Separate heartbeat processes and module reloads share the same local state and exclusive file lock; the lock covers the pass and serializes it with CLI apply runs using the same log. Lock acquisition uses nonblocking attempts with a one-second deadline. A busy lock raises a sanitized timeout before network access or control-state changes, allowing the heartbeat to continue without waiting for a hung apply. A saved timestamp up to ten minutes ahead keeps the pass throttled. A timestamp more than ten minutes ahead is treated as a clock jump and replaced with the current attempt time, allowing recovery. Direct CLI runs remain available for a deliberate dry-run or separately authorized apply.

Repeated `archive_failed` and `skipped_changed` outcomes append one log line for the batch until their state changes. The saved fingerprint excludes the pass timestamp and private error text, and includes the outcome, reason, frame IDs, counts, sanitized error type, and any changed candidate observed during recheck. A changed outcome or evidence emits a new line. If a batch stops qualifying on a later apply or enabled heartbeat initial read, its saved outcome is cleared, so a later recurrence is visible again. Successful archives always log. Every batch archive attempt still gets its durable `archive_attempt` entry even when a repeated failure outcome is suppressed.

The state file sits beside the log, with its suffix replaced by `.state.json`, and the lock uses `.state.lock`. The default paths are `~/ted-ops/ted-board/mockup-autoarchive.state.json` and `~/ted-ops/ted-board/mockup-autoarchive.state.lock`. State updates use an atomic file replacement. An unreadable or malformed state file stops an apply pass before network access or archive writes. Keep these files private, and preserve the state with the runtime backup. Disabled heartbeat calls create no state or log files.

Dry-run bypasses the state file and lock entirely. It never creates, reads, prunes, or rewrites control state, including when a saved state file is malformed. It performs GET requests and appends `would_archive` records only to its requested audit log when candidates exist. An empty preview creates no files. Existing throttle and log-backoff state remain unchanged.

## Verify before installation

The tests reconstruct the archive helper and the exact shared new-file artifact from `inbox-steward/runtime.patch` in a temporary directory, use synthetic snapshots, and never import production transports. This public-only check skips the private heartbeat integration:

```sh
python3 runner-fix/mockup_autoarchive_test.py
python3 scripts/check_data_api_grants.py
python3 -m unittest discover -s tests -p 'test_data_api_grants.py'
```

The shared module is delivered once in the hash-checked steward runtime bundle. Prepare that bundle offline from its reviewed private baseline, then copy only `board_card_snapshot.py` into the archive candidate. This preparation does not install or run the steward:

```sh
python3 "$TED_REVIEW/runner-fix/inbox-steward/prepare_candidate.py" \
  --source "$TED_STEWARD_BASELINE" --dest "$TED_STEWARD_CANDIDATE"
cp "$TED_STEWARD_CANDIDATE/board_card_snapshot.py" "$TED_CANDIDATE/board_card_snapshot.py"
```

`TED_STEWARD_BASELINE` is the PR 36 baseline release named in its manifest, and `TED_STEWARD_CANDIDATE` is a new private destination. Keep the shared module beside both installed consumers when updating either runtime. Refuse a mismatched existing shared module instead of silently overwriting it.

To exercise the actual candidate heartbeat, copy the mini's current `jobs_heartbeat.py` into a private candidate directory, then dry-run and apply both patches there. Refuse drift instead of forcing a patch:

```sh
cd "$TED_CANDIDATE"
patch --dry-run -p0 < "$TED_REVIEW/runner-fix/mockup-autoarchive.patch"
patch --dry-run -p0 < "$TED_REVIEW/runner-fix/jobs-heartbeat-autoarchive.patch"
patch -p0 < "$TED_REVIEW/runner-fix/mockup-autoarchive.patch"
patch -p0 < "$TED_REVIEW/runner-fix/jobs-heartbeat-autoarchive.patch"
TED_RUNTIME_SOURCE="$TED_CANDIDATE" python3 "$TED_REVIEW/runner-fix/mockup_autoarchive_test.py"
PYTHONPATH="$TED_BOARD_ROOT" python3 "$TED_CANDIDATE/mockup_autoarchive.py" --dry-run --log "$TED_CANDIDATE/dry-run.jsonl"
```

`TED_BOARD_ROOT` is the private mini runtime, `TED_REVIEW` is this PR checkout, and `TED_CANDIDATE` is a separate private candidate directory. The dry-run makes only existing GET requests, prints candidates, and records the requested local audit log without changing lock or state files. Its output contains no credentials, image URLs, card bodies, or feedback text. The job report contains the refreshed live candidate list. The original one-time cleanup was completed separately by Ted and is outside this fix round. Keep production evidence and backups private.

## Review and enable on the mini

The default CLI mode and `--dry-run` perform no archives. Both CLI `--apply` and the heartbeat require the exact environment value `TED_MOCKUP_AUTOARCHIVE_ENABLED=true`. When the flag is absent, the heartbeat makes no archive-related reads or writes. Do not run the full heartbeat as a smoke test: it already dispatches jobs and processes existing board controls.

Ted must review the PR and the current dry-run before approving future automatic archives. This flag is an implementation gate, not authorization to bypass the standing database rule. The model worker must stop at the review handoff. No one-time SQL application is part of this fix round.

After that separate authorization, back up the mini's current `jobs_heartbeat.py`, archive helper, shared snapshot helper, and state file when present. Dry-run the patches against those exact sources, install the reviewed archive helper, shared snapshot helper, and heartbeat hunk, and rerun the offline tests against the installed sources. The flag stays absent throughout installation. Then rerun the helper's live dry-run and compare the current candidates before Ted changes the environment of the existing heartbeat to enable future archives. No new launchd agent, cron, scheduled task, or worker is needed.

The default private audit log is `~/ted-ops/ted-board/mockup-autoarchive.jsonl`; CLI `--log` can select another private path. Every record includes the exact project, batch, reason, active frame IDs, and policy evidence. Keep this log outside the public repository.

Rollback first removes the flag from the existing heartbeat environment, then restores the backed-up heartbeat, archive helper, shared snapshot helper, and local state file when present. This stops future archives and leaves the log intact. Already archived batches require Ted's separately reviewed status restoration from the private backup. Do not restore verdicts, pins, or Storage, and do not overwrite later feedback.
