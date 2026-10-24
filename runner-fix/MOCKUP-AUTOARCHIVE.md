# Mockup auto-archive handoff

Finished batches should leave the Mockups wall without requiring another upload. This adds a private helper and a small hook to the mini's existing heartbeat. It uses the existing worker-authenticated archive action, preserves pins, images, verdicts, and Storage, and changes no browser tab or database schema.

The runtime is intentionally excluded from the public repository. The focused patches follow the existing runner-fix convention. They are staged for Ted review and have not been installed or enabled.

## Policy

An active batch is the exact project and batch pair, with at least one non-archived frame. The pass uses these reasons, in order:

1. `all_reviewed`: every active reviewable frame has `approved`, `needs_work`, `scrapped`, or `picked`. Legacy `status=picked` also counts when there is no explicit verdict. At least one reviewable frame is required. Titles labeled `Notes`, `Notes: ...`, `Notes, ...`, or `Who made and checked this` are informational, including those labels after a colon, such as `Hair v13: Notes, what changed and why`. A frame titled `Notes app screen` remains reviewable. Informational frames are archived with the batch.
2. `linked_card_done` or `linked_card_killed`: the linked card is terminal. Existing links are exact same-project `build approved: <batch>` titles and explicit `mockup ID: <id>` references in card bodies. A row's explicit `card_id` is supported if a feed later supplies it. There is no fuzzy card-title matching. If several cards link the batch, all must be done or killed. A missing card does not imply completion.
3. `stale_superseded`: no verdict activity for at least five full days, plus a strictly newer batch in the same project with the same prefix. A prefix is the normalized descriptive name before a version, round number, or date suffix. For example, `Home`, `Home v1`, and `Home v2` share a prefix; `Home icons v2` does not. Colon descriptions remain part of the prefix. Case, punctuation, and whitespace are normalized. Archived newer batches also establish supersession.

Staleness uses the latest frame creation time, `verdict_change.at`, `verdict_at`, or legacy `picked_at`, across the batch. A newly added frame resets the clock. Missing creation times, invalid activity times, or verdicts without a known activity time prevent a staleness decision. A superseding batch's first frame must be newer than the old batch's last frame. Ambiguous naming and links stay visible for manual handling.

Every rule waits for any active Undo window to expire. Dry-run records `would_archive` with the reason and evidence. Apply rereads both feeds immediately before each archive, skips any changed decision, writes a durable `archive_attempt`, and records `archived` only after an explicit successful receipt with the expected row count. Errors record only their type, with no raw transport details. One failed archive does not stop later batches. A read or audit-log failure stops the pass; the heartbeat catches the failure and keeps its existing work intact.

The current archive API is unconditional by project and batch. Rechecking narrows, but cannot eliminate, the interval in which a concurrent upload or verdict could arrive between the final read and the write. An atomic snapshot guard would require a separately reviewed backend change. No such backend change is included here.

## Verify before installation

The tests reconstruct the helper from its patch in a temporary directory, use synthetic snapshots, and never import production transports. This public-only check skips the private heartbeat integration:

```sh
python3 runner-fix/mockup_autoarchive_test.py
python3 scripts/check_data_api_grants.py
python3 -m unittest discover -s tests -p 'test_data_api_grants.py'
```

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

`TED_BOARD_ROOT` is the private mini runtime, `TED_REVIEW` is this PR checkout, and `TED_CANDIDATE` is a separate private candidate directory. The dry-run makes only existing GET requests and prints candidates without credentials, image URLs, card bodies, or feedback text. The job report contains the live candidate list and the separate database-gated SQL, backup, and rollback handoff. Keep those production artifacts private.

## Review and enable on the mini

The default CLI mode and `--dry-run` perform no archives. Both CLI `--apply` and the heartbeat require the exact environment value `TED_MOCKUP_AUTOARCHIVE_ENABLED=true`. When the flag is absent, the heartbeat makes no archive-related reads or writes. Do not run the full heartbeat as a smoke test: it already dispatches jobs and processes existing board controls.

Ted must review the PR, the current dry-run, and the private `apply.sql` before approving database writes or future automatic archives. This flag is an implementation gate, not authorization to bypass the standing database rule. The model worker must stop at the handoff.

After that separate authorization, back up the mini's current `jobs_heartbeat.py`, record whether a helper already exists, dry-run the patches against those exact sources, install the reviewed helper and heartbeat hunk, and rerun the offline tests against the installed sources. The flag stays absent throughout installation. Then rerun the helper's live dry-run and compare the current candidates before Ted changes the environment of the existing heartbeat to enable future archives. No new launchd agent, cron, scheduled task, or worker is needed.

The default private audit log is `~/ted-ops/ted-board/mockup-autoarchive.jsonl`; CLI `--log` can select another private path. Every record includes the exact project, batch, reason, active frame IDs, and policy evidence. Keep this log outside the public repository.

Rollback first removes the flag from the existing heartbeat environment, then restores the backed-up heartbeat and prior helper state. This stops future archives and leaves the log intact. Already archived batches require Ted's separately reviewed status restoration from the private backup. Do not restore verdicts, pins, or Storage, and do not overwrite later feedback.
