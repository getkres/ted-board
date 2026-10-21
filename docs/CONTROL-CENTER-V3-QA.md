# Control Center v3 QA and handoff

All six changes are draft PRs in an ordered stack. No SQL, deployment, main push, or merge was performed. Testing serves the static folder on localhost:8763, with every backend request intercepted by synthetic fixtures. No live page key or private operational data is in screenshots.

## Verification

The final run passed 13 verification groups, nine snapshot unit tests, and 70 responsive screenshots, with zero clipped text, horizontal scroll, console errors, visible gradients, or em dashes.

Run `node qa/run.cjs` after starting the static server. It covers backend validation, Inbox actions, split isolation, snapshot polling, in-flight key isolation, Spaces, Roadmap, Mockups, triage/Undo, markup, retained controls, guided mode, Jobs, and Access. The final screenshot matrix covers 390 by 844 and 1440 by 960, with JSON evidence and PNGs under `qa/pr6/`.

Clip checks inspect rendered text ranges against the viewport and clipping ancestors. They also check document horizontal overflow, console errors, em dashes, and computed gradient backgrounds. Gesture and action tests supplement screenshots. These checks do not certify accessibility conformance, the private backend, or live data freshness.

The theme uses Archivo condensed bold caps, supplied Lair WebP textures of 69,412 and 255,162 bytes, and reusable bear SVGs. The unused cave stylesheet and old primary Control/project tab generator were removed. Reused workflows remain reachable through the Inbox disclosure. Phone has all four primary tabs on one row, while desktop includes the command field.

## Independent review resolutions

A fresh independent Codex reviewer checked the implementation and references. A Claude reviewer was not available through this session's tools, so no Claude review is claimed.

| Finding | Resolution and regression |
| --- | --- |
| Inbox shortcuts could approve a hidden card | Split-scoped dispatch; `qa/inbox-safety.cjs` reproduced the failure before the fix. |
| Compare shortcut targeted the wrong version | Visible right-hand target stored; `qa/mockup-safety.cjs` reproduced the failure before the fix. |
| Round dialog survived a key change | Creation-time ownership and tracked dialog cleanup; `qa/mockup-safety.cjs`. |
| Round approval skipped why | All approved paths route through the round reason dialog; `qa/mockup-safety.cjs`. |
| Snapshots stopped refreshing during polling | Guarded poll accepts optional feeds and capabilities; `qa/polling.cjs` reproduced the failure before the fix. |
| Reserved decision aliases entered automatic feeds | One shared classification contract in UI and server integration; nine snapshot test groups, including alias regressions. |
| Non-Yours cards lost access | Details resolve against all cards, and the mobile disclosure exposes All project cards; `qa/inbox-safety.cjs`. |
| Triage did not advance after feedback | Confirmed decisions leave the session queue, with Undo restoring the frame; `qa/triage.cjs`. |
| Routine status-only payloads showed not logged | Status is used consistently in counts, labels, and fine grouping; `qa/inbox-safety.cjs`. |
| Painted text fell outside submitted crop | Shared text layout for drawing and crop; actual SVG bounds checked at corners, including long text; `qa/markup.cjs`. |
| Initial phone viewer long-press did not pin | Default Pan long-press pins at the actual spot; movement and second-pointer cancellation tested in `qa/markup.cjs`. |
| In-flight card response could cross key resets | Request owner and generation guards, plus cleared drafts and guide state; `qa/key-reset.cjs` reproduced the failure before the fix. |

## Remaining integration work

The public clone does not include the private Edge Functions or workers. The modules in `backend-integration/` are prepared integration seams, not deployed replacements. Ted must review and apply SQL, connect the private authenticated handler hooks, preserve transactional receipt and Undo semantics, update the mockup uploader and watcher, and install the producer on the Mac mini.

Snapshot decisions support display and existing control veto. Snapshot-only Undo, Reopen, Split back, and first-view veto tracking are not implemented by a new private handler here, so unsupported controls remain disabled and the browser starts no timer. Review choices require the documented durable receipt hook. Woke status requires a producer that checks actual work.

Good, one fix, atomic direction picking with why and optional scrap-rest, and persistent normalized strokes/crops require their reviewed backend transactions. The UI gates each capability separately. Pixel differences require images whose host permits canvas reads; the UI reports an unavailable diff when the host prevents it. Signed-in live end-to-end validation remains outstanding.

Spec-specific operational speech, reviewer claims, routines, and roadmap items come from live payloads when available. Missing information uses truthful fallback copy. The implementation does not certify pixel-for-pixel parity with every supplied frame, and the final live-data completion scenario has not been demonstrated without the private integration.
