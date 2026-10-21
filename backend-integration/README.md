# Backend integration, prepared but not deployed

The public clone contains no `ted-board` or `ted-mockups` handler. These files are integration seams, not a deployed API. SQL has not been executed. The live-data completion condition remains blocked until Ted integrates the private handler, applies reviewed SQL, deploys the functions, and installs the snapshot producer on the Mac mini. This change creates no routine.

## Required private handler hooks

1. Reuse existing credential verification before invoking `handleSnapshotAction`. Pass `principal: 'page'` only after the page key matches, `'worker'` only after the separate worker key matches, and `null` for an invalid credential. Never infer the role from a request body, caller header, or user-editable JWT claim. Reject shared page and worker key values in the private configuration. Keep the existing per-key rate limits, CORS checks, and request-size bounds. Limit request bytes to 2 MB before parsing JSON. Do not log bodies, keys, or keyed URLs.
2. Create the service-role Supabase client exclusively in the Edge Function. Adapt it with `createSupabaseSnapshotStore`. Invoke `handleSnapshotAction({method, resource, body, principal}, store, optionalReviewHook)` before the existing unknown-action response. A `null` return continues existing routing. `resource` is the existing board query parameter; `scope` is also accepted as an internal alias. Keep all legacy handlers unchanged.
3. Serialize returned `{status,body}` with existing CORS headers and `Cache-Control: no-store`. Keep the service-role key, worker key, local files, and snapshot producer out of all static assets. The page uses only its existing page key.
4. Add `snapshots` to page-readable GET resources and `snapshot_push` to the worker-only action allowlist. `GET ?resource=snapshots` returns `{snapshots:[{kind,key,payload,generated_at}],capabilities:{snapshots:true,review_choice:false}}`. Missing schema returns the same shape with an empty array and both flags false. Other database errors return a generic 503, not a false empty feed. Snapshot timestamps describe provenance, not verification or approval. The normal cards GET must advertise `capabilities.snapshots` and `capabilities.review_choice` after the same server-side capability check. Prefer including the snapshot rows inline in that normal response, merging these fields with existing capabilities. The frontend must never probe a legacy API for unsupported resources. If a snapshot query fails operationally, keep the cards response usable, set both optional capabilities false, and include a generic `snapshot_error`; never erase cards or claim snapshots are current.
5. Add `review_choice` to page actions only after supplying the durable hook described below. When absent, capability stays false and the action returns 501. Do not advertise a successful review until a durable receipt exists.

The module has no external imports, environment reads, HTTP server, or key material. `SupabaseSnapshotClient` is the minimal structural adapter interface; reconcile it with the actual pinned SDK in the private backend. Do not replace the deployed handler with this file.

## Producer contract

Worker POST: `{action:'snapshot_push',key:WORKER_KEY,snapshots:[{kind,key,payload,generated_at}]}`. Envelope `key` is authentication only and is never retained. Snapshot row `key` is a stable feed identifier such as `daily`, `line3`, or `line1`. Batches have at most 50 rows, each payload has at most 256 KiB, and total payload bytes are at most 1 MiB. Duplicate kind/key pairs, unknown feed kinds, malformed dates, future dates beyond five minutes, sensitive field names, and unbounded nesting are rejected. The SQL RPC updates only when `generated_at` is newer; replaying the same timestamp is a no-op. Replacing a snapshot replaces its whole payload. Delete or tombstone semantics require a separate reviewed change.

Payloads are objects with `items:[]` for the common frontend contract, plus `woke:[]` for decisions and `review_items:[]` for routines. Pods and roadmap snapshots are keyed by line. Roadmap item rows carry their column as a `lane` (`now`, `next`, `later`, or `shipped`). The module also accepts the named-array alternatives below for producer compatibility. IDs and stable keys come from source records. Missing information stays absent or says `not logged`; do not fabricate runs, reviews, models, dates, routine success, or roadmap items.

| Kind | Required payload | Optional payload |
| --- | --- | --- |
| `decisions` | `decisions:[{id,status:'done'\|'proposed'\|'approve',line,why,decision_kind,undo,veto_hours,veto_starts,card_close}]` | `woke:[{id,line,status:'woke'\|'running'\|'stuck'\|'asleep'}]` |
| `routines` | `routines:[{id,name,line,schedule,last_run,status:'fine'\|'look'\|'broke',last_output}]` | `review_items:[{id,title,why,suggestion,kind:'bookmark'\|'screenshot',line}]` |
| `pods` | `pods:[{id,line,name,agent,state,now,last_run,model,outputs,runs,blocked_on,reviews,seats}]` | Agent objects may carry IDs, names, states, outputs, runs, and reviews from the same ledger. |
| `roadmap` | `now:[],next:[],later:[],shipped:[]`, with items `{id,title,status,date,card_id}` | `line`, `empty_copy` |

Row metadata beyond these fields is allowed as JSON, subject to bounds and secret-field rejection. The pure validator checks collection structure, decision identity and status, review identity, and envelope safety. It does not certify that source content is correct. Producer tests and private reviewer checks must validate the richer row contracts before enabling their corresponding UI.

Money out, sends, database writes, legal decisions, and login decisions must use `status:'approve'`, never `done` or `proposed`. They cannot start automatic veto timers. The producer must classify these before publishing. Page display and snapshot data must never authorize these actions. Actual undo and veto actions continue through existing revision-checked control handlers. `veto_starts` must come from the existing server first-view tracking; a snapshot read must not start or reset a timer. Card closes retain `card close, your rule pending` until the server records the rule.

Only the mini producer reads local ledgers. This implementation neither accesses those files nor installs a worker. Snapshot payloads must be curated to remove credentials, private paths, and keyed links. The validator is defense in depth, not a general-purpose secret scanner.

## Durable review choices

Page POST: `{action:'review_choice',item_id,choice:'keep'|'skip'|'card',operation_id:UUID,key:PAGE_KEY}`. The injected `ReviewHook` must check that the item belongs to the current review feed, atomically persist the choice and an existing `ted_decisions` routing receipt, and deduplicate by `operation_id`. Reusing an operation ID with different fields must be a conflict. The watcher routes `card` into existing card creation, using that operation ID to prevent duplicate cards. Return `{ok:true,item_id,choice}` only after commit. Preserve existing rate limits. Do not use a read-modify-write snapshot as a review receipt because the next worker snapshot can overwrite it. The private receipt schema is unavailable, so no speculative receipt-table SQL or fake successful write is included.

## D5 private mockups hooks

`20261021221735_control_center_v3_mockups.sql` is proposed metadata and strokes storage. `MOCKUPS.md` documents UUID mockups and pins, nullable `verdict`, and existing transactional verdict RPCs. The actual enum and constraints are not public. The migration checks expected IDs, verdict representation, existing D5 types, and strokes shape, and aborts on incompatible schemas or compound verdict checks. It adds `good_with_fix` to a discovered enum or narrowly extends checks scoped only to `verdict`. No verdict RPC is changed. Review this against the private migration before applying.

Uploader writes `kind` (`set`, `stack`, or `round`), lineage, positive version, and the same batch `review_chain:[{reviewer,verdict,round}]` to every row in its batch. No batch table is documented. Do not infer reviewer passes from missing data.

Extend the private GET response with explicit booleans `good_with_fix_enabled`, `strokes_enabled`, and `rounds_enabled` only after storage and corresponding write handlers pass capability probes. Keep them false until then. The private verdict RPC must add `good_with_fix` atomically with its receipt, note or pin, five-second Undo token, and watcher behavior. `needs_work` must require a reason chip or saved stroke, validated inside that transaction. Valid reasons are spelling, off-model, spacing, copy, color, and type. The old backend has no such guarantee, so the new UI must not claim these capabilities merely because columns exist.

Strokes are path data only, never raw SVG markup. Private writes must parse path commands, reject non-finite or out-of-bounds normalized coordinates, enforce tool, color, size, frame, and text limits, validate that an optional pin belongs to the same mockup, and atomically save strokes with the relevant feedback receipt. `frame_id` identifies an image frame, not an external file. `text_content` is rendered as escaped text. SQL restricts path characters but cannot substitute for a normalized path parser. Join strokes into authenticated reads, keep RLS enabled with no public policies, and route the crop and strokes through existing private feedback workers. Update watcher rules for good-with-fix art before advertising support. Never silently map it to final approval.

## Offline verification

Run `node --test backend-integration/snapshots.test.ts` with Node 24 or newer. This exercises the actual validator and action authorization without network, SDK installation, secrets, or database access. SQL was reviewed statically, not executed. Ted still needs staging migration, pinned-SDK type checking, real handler credential tests, receipt idempotency tests, and five-second Undo and watcher regression tests before deployment.

Supabase guidance checked: [RLS](https://supabase.com/docs/guides/database/postgres/row-level-security), [upsert](https://supabase.com/docs/reference/javascript/upsert), and the [changelog](https://supabase.com/changelog). This module uses a server-only service-role adapter and denies direct anonymous and authenticated table access.

### V3 mockup request contracts

The UI gates these actions on the explicit flags above. `round_pick` accepts `{mockup_id,why,scrap_rest,operation_id}`. Resolve the authenticated mockup's project and batch server-side, require a nonempty reason, and record the pick and any rest-of-round scrap receipts atomically. Do not accept a caller-supplied batch as authority, expose Ted's picks before the choice, or advertise `rounds_enabled` until the transaction and Undo policy are reviewed.

`stroke` accepts `{mockup_id,frame_id,operation_id,tool,path,color,crop,pin_id?,text_content?}`. The UI sends only bounded M/L/Z paths normalized to 0..1, with crop `{x,y,width,height}`. Persist `path` as `svg_path`; return `{ok:true,stroke:{id,...submittedFields}}` only after the stroke and its routing receipt commit. The client retains drafts unless identity, operation, path, color, tool, text, and crop match the acknowledgement. The private receipt must persist and deduplicate `operation_id`, and the worker must receive the normalized crop. The proposed strokes table intentionally does not invent the private receipt schema. Curate GET strokes for the same authenticated image. Never turn raw markup into HTML.

The original `verdict` action now receives a nonempty `text` with needs-work and one-fix feedback. Keep existing token and five-second Undo semantics, and enforce the reason or saved-stroke requirement server-side. A browser check alone cannot secure another caller. Normal approved, scrapped, pin, reply, approve_batch, undo_approve_batch, and undo_verdict requests retain their existing shapes.

## Authenticated line metadata

The board response should include `lines: [{id, name}]` in display order. IDs must be stable lowercase letters, numbers, underscores, or hyphens. Names are account data and must only be returned after authentication. The frontend also accepts a `lines` snapshot payload with an array, `items`, or `lines`; a private producer must explicitly support that kind before using it. This change does not add a new SQL feed kind or deploy a producer.

Older board feeds can supply `line` plus `line_name` or `project` on authenticated cards, pods, and roadmap payloads. Only identities with a recorded name are shown. No client directory ships in the static bundle. Metadata resets with the access key, and successful polls refresh it. While authentication is pending, no generic directory is invented. Only a rejected 401 or 403 board request enables the generic Line 1 through Line 10 fallback.
