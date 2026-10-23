# Finished worker handoff

A successful worker turn is ready for Ted to review. It does not mean the card has shipped or that Sebastian must approve something. These patches put terminal successful jobs in Up next with the status note "Ted review". The live-status transport normalizes that note to lowercase. The delivery state stays blocked until the remaining review, merge, deployment, or application is complete.

The private runtime is intentionally excluded from this public repository. This follows the existing runner-fix patch convention. These changes are staged for Ted review. They have not been installed or deployed.

- `finished-jobs-session_worker.patch` adds a structured completion handoff to successful ordinary worker results. The worker still returns through the dispatcher and never publishes independently.
- `finished-jobs-sessions.patch` makes the dispatcher enforce Up next and Ted review for a successful terminal session without a queued continuation. It uses fixed policy values, regardless of worker-supplied section metadata.
- `finished-jobs-board_live.patch` lets reconciliation retry that handoff after a missed publication, including reports that still have a pending PR. It preserves active workers, queues, pending approvals, failures, veto outcomes, manual card moves, and newer card answers.
- `finished-jobs-live_status.patch` and `finished-jobs-handler.patch` allow the guarded Up next transition through the existing worker-authenticated API and update future worker completion instructions. No schema, RPC, migration, database application, email, or spending change is required.

The dispatcher and reaper still require Ted doing as the current section. The existing veto worker and its narrow delivery exception are unchanged.

Run against candidate copies first, with the Python files and the Edge Function modules in one candidate directory:

```sh
TED_RUNTIME_SOURCE=/absolute/path/to/candidate python3 runner-fix/finished_jobs_test.py
TED_RUNTIME_SOURCE=/absolute/path/to/candidate node --test runner-fix/finished_handler_test.ts
```

The tests use temporary stores, fake worker output, stubbed API publication, and an in-memory database adapter. They never launch a model worker or contact production. The handler test requires Node 24 or later for TypeScript stripping.

After approval, prepare a timestamped backup of `sessions.py`, `session_worker.py`, `board_live.py`, `live_status.py`, and `supabase/functions/ted-board/handler.ts` on the mini. Dry-run every patch against those exact files. Refuse drift instead of forcing a patch. Apply the handler allowlist and deploy the reviewed Edge Function before enabling the Python transition. Apply the runtime patches together, then run the tests above against the installed files and the existing live-status tests with publication stubbed. Let the existing mini heartbeat pick up the change. No new routine or worker is needed.

Rollback: restore those five files from the timestamped backup, redeploy the backed-up Edge Function if it changed, and rerun the offline checks. This changes future worker routing only. No existing production cards were corrected as part of this PR.
