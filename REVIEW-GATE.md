# Mandatory content review

The public code supplies a generic, fail-closed review engine. Business names,
client folders, project scopes, shared source paths, and integration patches
stay in a private local rollout bundle. They are never committed to this repo.

The private registry maps each business to its pod directory, aliases, allowed
projects, and whimsy trait. Each pod config selects its required reviewers,
model, effort, and order. Runtime validation checks both the private registry
and the pod config. Registry, canon, decisions, and shared-source changes
invalidate existing reviews.

## Proposed quorum for Ted to review

The proposed default requires canon-checker, creative-director, audience-panel,
and compliance for every output, including internal reports. Whimsy businesses
add a score and reviewer. This is deliberately stricter than the brief's
conditional audience and compliance checks. Ted must accept this deviation,
its quota impact, and the model and effort defaults before rollout.

A full pass consumes four sequential review runs, or five where whimsy applies.
For example, ten ordinary completed results require 40 calls, and ten whimsy
results require 50, before any additional in-run review. These are scenarios,
not a forecast. Daily result volume is not established. Failed reviewers stop
before downstream calls. Fixed worker failures stay local without a chain.

The default route is Opus 5.5 at high effort, consistent with the code-review
judgment route. The older routing document's unauthenticated-access marker is
historical; native account authentication and actual model results must be
verified at runtime. The current brief mandates independent reviews. Existing
usage-saving preferences still matter when Ted selects the deployment config.

Initial large-code samples took approximately 63 to 97 seconds per reviewer.
These samples do not guarantee latency. Each model call allows 600 seconds,
so model-timeout allowance totals 40 or 50 minutes, plus authentication and
local processing. An in-run review and final-answer review can both occur.

The runner allows only basic operating-system environment variables, excludes
user settings and MCP servers, verifies native Claude account authentication,
and never switches to API credentials. This does not prove zero incremental
cost. Account-native paid extra usage may be enabled. The tool cannot read or
enforce remaining quota, extra-usage settings, or billing caps. Ted must confirm
those controls before rollout. No account or billing setting is changed here.

## Review a job

For a running board job:

```sh
python3 review.py --job-dir JOB --from-session REPORT.md copy.txt
```

The worker records execution metadata before the maker starts. The helper reads
the session ID from the active event stream. Codex's model comes from the actual
command's model flag, and Claude's model comes from runtime metadata. Missing
identity blocks review. Legacy jobs must resume on an updated worker to produce
that metadata. For an aggregate project, pass the specific --business ID.

A standalone or scheduled pod runner instead uses the native maker result or
verified execution metadata after the maker finishes:

```sh
python3 review.py --job-dir JOB --business BUSINESS_ID \
  --maker-agent AGENT --maker-model ACTUAL_MODEL --maker-session-id ACTUAL_SESSION \
  REPORT.md copy.txt
```

Never invent identity fields. No new schedule is registered. The reviewer
runner starts each role synchronously in a fresh Claude session, with Read as
its only ordinary tool and no resumed session. Reviewers cannot edit files.
No independent background worker is delegated.

Reviewers load the business CANON.md, DECISIONS.md, pod policy, shared rules,
and applicable design sources from the private registry. They follow relevant
source pointers. Dead hits kill, and relevant missing or unresolved evidence
blocks. Current explicit owner instructions take precedence over older
summaries. An internal proposal cannot invent facts from an incomplete canon.

review-request.json binds the exact request. review.json records:

- Every reviewed relative path and SHA-256 digest.
- The maker agent, selected or reported model, and actual session ID.
- Each reviewer's role, actual reported model, separate session ID, verdict,
  findings, verified changes, item coverage, and raw run-evidence digest.
- Registry, canon, decisions, policy, and applicable shared-source digests.
- The whimsy score, declared unfixed findings and reasons, upload metadata,
  authentication type, and a fixed failure reason when applicable.

Missing records, roles, evidence, or identity block. So do fix or kill,
self-review, reused sessions, changed items, new approval files, and changed
sources. A failed attempt invalidates an earlier pass. Revise locally, record
what changed, and rerun. Every required role must pass on the final bytes.

## Reviewed mockup batches

Pass --design and --upload-manifest with JSON like:

```json
{
  "project": "Example project",
  "batch": "sample batch",
  "images": [
    {"path": "screen.png", "title": "Screen", "sort": 0}
  ],
  "unfixed": [
    {"finding": "A secondary note remains compact.", "reason": "The owner requested the full evidence on one card."}
  ]
}
```

Uploads always require design context. The private design source list includes
DESIGN-JOB-RULES.md and, where applicable, the design canon and referenced
WHIMSY-CHECK.md. Design whimsy must be at least 9/10. Nonvisual work records the
score and applicability without a numeric threshold.

After the content passes, the runner mechanically generates "Who made and
checked this" from the actual maker, reviewer results, findings, changes, and
unfixed findings with reasons. An empty unfixed list says "None declared."
The gate recomputes the provenance card's bytes. Every reviewer must have
reviewed every original content item. Full findings can make a tall card;
the board's zoom controls support close reading.

```sh
python3 mockup_upload.py --job-dir JOB --project 'Example project' --batch 'sample batch'
```

The uploader uses reviewed titles and sort values and sends the entire manifest.
It uploads attribution first, with the last sort value, so partial failure
cannot expose content without provenance. Detail reattachment needs the exact
project, batch, reviewed source, and remote-row receipt. The low-level transport
also checks provenance and encoded bytes before loading credentials.

## Other delivery paths

The worker reviews final-answer.txt after a successful maker result. The
outbox checks it before queueing and flushing. A new request invalidates the
old pass. Unreviewed output becomes review_blocked and is not delivered. Fixed
operational failures stay in job status rather than bypassing the reply gate.

Needs you transitions, direct replies, exact card creation and sync payloads,
SQL, email, and spend approval staging, approval snapshots, and approved
execution all require the current passing review. Timed proposal staging
binds veto-request.json. The dedicated veto worker and server send scope are
unchanged. Review grants no send, spend, database, or publishing authority.

Pod instructions and templates require canon_check and review. Copy the exact
status to JOB/pod-status.json before review, then add review_job_dir to the live
status. The publisher compares every other status field with the reviewed
snapshot. Only passing rows enter a new snapshot. If none pass, no publication
occurs, and the last remote snapshot becomes stale. If some pass, unreviewed
rows are omitted. This applies the newer review mandate to daily pod updates;
prepare status reviews before rollout. Existing panel rounds remain required.

## Private rollout and verification

Ted reviews the public PR and the private local bundle before applying either.
The bundle contains the private registry, narrow worker and existing-test
patches, and original and resulting file hashes. No private bundle is uploaded
by these tools. Deployment builds patched bytes in temporary storage, checks
base hashes, parses pod configs, and prepares the proposed review settings and
scaffold. The dry-run file count describes planned updates. It does not certify
canon content, source freshness, account quota, or business facts.

```sh
python3 deploy_review_gate.py --bundle PRIVATE_BUNDLE
python3 test_review_gate.py --bundle PRIVATE_BUNDLE
```

Tests reconstruct the private overlay in a temporary directory. Python HTTP is
disabled, and Deno uses database fakes. Only Ted, after reviewing the PR and
private bundle, runs the local rollout with a private backup:

```sh
python3 deploy_review_gate.py --bundle PRIVATE_BUNDLE --apply --backup PRIVATE_BACKUP
python3 deploy_review_gate.py --rollback PRIVATE_BACKUP
```

The rollout preserves existing authority and cadence, updates the shared
playbook templates, and can create an unscheduled desk scaffold. No database,
Edge Function, service, or schedule is changed. Source drift blocks rollout.
Rollback restores existing files and removes new files. Use a quiet worker
window so old and new Python modules are not mixed in active jobs.

This is an operational gate for supported local entry points. Processes with
arbitrary filesystem access and production credentials can bypass it. The PR
does not claim server-side enforcement or credential isolation.
