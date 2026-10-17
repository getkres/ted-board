# Mockups on Ted Board

Shipped October 16, 2026. Open [Ted Board](https://getkres.github.io/ted-board/) with your existing private link, then choose **Mockups**. Access uses the same page key as the cards. Never put the private link or either key in Git, screenshots, or messages.

## Reviewing designs

Batches appear newest first, with a project filter and a swipeable row of large images. Open an image for fullscreen review. Choose **Add pin**, tap a detail to position the numbered pin, type a comment, and choose **Send comment**. Pin positions follow the image as you resize, pan, or zoom. Each image opens at Fit. Zoom out to 25% actual image scale, or below Fit for large boards, and in to 10x with pinch gestures, the mouse wheel, or the visible controls. The percentage shows actual image scale, where 100% means one image pixel per screen pixel. Tap the percentage or **Fit** to reset. Double-tap a spot for 2.5 times Fit and again to Fit. Drag or use two fingers to pan. Full detail loads above 1.5 times Fit when the preview needs more pixels. Use the edge arrows or Left/Right keys to step through the batch in grid order without wrapping. Swipe left or right on a phone at Fit or below to navigate. Neighbor previews preload, and each image opens with pin placement off. Focus the viewer and use Up/Down or Shift+Left/Right keys to pan, plus/minus to zoom, or 0 to Fit. Pins stay a constant size on screen. **Add pin** places a pin in the visible area for keyboard users.

Tap a numbered dot or a **Pin** button to open its conversation. Ted's replies have the same marigold treatment as card replies. Reply in that thread to keep the conversation together. A reply to a resolved pin reopens it. Green pins are resolved. Unread Ted replies add dots to the image, the pin list, and the Mockups tab; opening a thread marks it read on this device. Refresh fetches new replies.

Choose **Pick this one** below an image to record a selection. Repeated picks are idempotent. Picking one image does not clear other selections. Archived images are hidden from the gallery and cannot receive new Sebastian feedback.

Sebastian comments allow 1,200 characters, leaving room for the full comment, mockup title, project, batch, and coordinates in the existing 2,000-character decision receipt. Ted replies allow 2,000 characters and reject U+2014. Failed saves retain the draft. If a connection times out, refresh before sending again to check whether it arrived. Read markers are local to the browser, and feedback needs an internet connection.

## Current designs

The gallery was seeded with 20 real mockups:

- **Fictora / Top bar v2:** comparison board, plus all 12 glass home, scrolled home, and shelf shots across Daydream, Lair, Moonflower, and Night.
- **Lunair + art / Closet spike:** nine-combination contact sheet, head styling tab, tops styling tab, and headwear with hair grid.
- **Lunair + art / Dressup v2:** wardrobe contact sheet and G2 styling v2.
- **Bookish / App icon round 3:** board 11, marked picked, with the title identifying 11a as chosen.

Seeding used worker registration and created no Sebastian decisions.

## Worker commands

Operational source and tests remain private on the Mac mini in `~/ted-ops/ted-board`. They are not deployed through GitHub Pages. The following commands use the installed Command Line Tools Python runtime. This also avoids the machine's current Xcode license prompt without changing its global developer-tool selection.

```sh
PY=/Library/Developer/CommandLineTools/usr/bin/python3

$PY ~/ted-ops/ted-board/mockup_upload.py \
  --project Fictora --batch 'Top bar v3' --title 'Glass home' \
  /path/to/home.png

$PY ~/ted-ops/ted-board/mockup_upload.py \
  --project 'Lunair + art' --batch 'Closet v2' --title 'Outfit options' \
  /path/to/one.png /path/to/two.png

$PY ~/ted-ops/ted-board/mockup_reply.py <pin_id> 'Updated the spacing. Ready for another look.'
$PY ~/ted-ops/ted-board/mockup_pins.py --open
```

Uploads preserve aspect ratio and save a full WebP at quality 95, retaining transparency and capping the long edge at 12,000px. The grid uses a separate JPEG quality 95 preview, capped at 1,600px on either axis, with transparency flattened onto white. Metadata is removed. Preview files must fit 4 MB, and full files must fit 32 MB. Each image object receives a UUID path. Multiple files use the supplied title as a prefix followed by each filename. `--status picked` can register an already chosen design without a Sebastian receipt. `--sort` controls order within the batch. The uploader prints each confirmed ID; if a later file fails, earlier confirmed uploads remain registered. If full detail fails after preview registration, it prints the existing ID and a recovery command, continues the batch, and returns nonzero. Retry that row with `mockup_upload.py --attach-full MOCKUP_ID /path/to/original.png`; this does not create another row. When replacing an image with a different aspect ratio, add `--replace-preview` to attach its matching preview through Storage metadata while preserving the row ID and pins. Original source paths are recorded in a private local upload log.

`mockup_pins.py --open` prints one JSON object per unresolved pin, including its image, project, batch, full thread, and latest Sebastian text. Omit `--open` to include resolved pins.

Resolve or reopen a pin through the private worker client:

```sh
cd ~/ted-ops/ted-board
/Library/Developer/CommandLineTools/usr/bin/python3 - <<'PY'
from mockup_client import call
call('resolve', pin_id='<pin_id>', resolved=True)
PY
```

## Watcher replies and routing

The existing `co.ted.decisions` watcher handles `page='mockups'` receipts. It uses the new `~/ted-ops/ted-decisions/mockup_route.py` module; card routing remains unchanged. Its launchd environment uses Command Line Tools Python, and no new routine was created.

Every Sebastian pin, reply, legacy pick, or verdict creates a `public.ted_decisions` row atomically with the action. Pin and reply receipts use the pin ID as `item_id`. Pick receipts use the mockup ID. The note contains the full comment or selection, image title, project, batch, mockup ID, and coordinates. Picks identify coordinates as applying to the whole image.

For pin feedback, the watcher posts a short acknowledgment in the same pin thread, then appends the task to `~/ted-ops/markup-watch/design-queue.md`. Queue entries include the exact reply command. Ted or a delegated design worker must reply in that pin thread with the outcome or blocker, using `mockup_reply.py`. Replies must be plain text, contain no U+2014, and stay within 2,000 characters. Resolve a pin after the requested change is complete. New design variants should be uploaded into a new batch.

The watcher sends its acknowledgment with `--decision-id` semantics through the client. The database deduplicates that acknowledgment by decision ID, and stable queue markers prevent repeated design work if a route is retried. Routing failures remain eligible for retry even after a Telegram acknowledgment. Test notes starting with `test-` never post a mockup reply or enqueue design work.

Good to go and Scrap enter the queue as completed, informational verdict records. Legacy picks also remain informational. They do not launch design work and have no pin thread, so the watcher does not pass a mockup ID to the pin reply command. Any follow-up belongs in a related actual pin thread.

The existing fast queue consumer uses the new `~/ted-ops/markup-watch/design_dispatch.py` to distinguish mockup, card, and legacy Figma briefs. Mockup workers upload to Ted Board and reply to the original pin. Card workers retain their exact card outcome command. Existing Figma briefs retain their original delivery surface. A failed Figma poll does not prevent independent design briefs from running. Queued mockup commands use the direct Command Line Tools interpreter.

## Backend and deployment

- Function: `ted-mockups` on Supabase project `wqnrortftkffmbeugjky`, deployed independently of the card function with JWT verification disabled and the existing page and worker secrets.
- Private source: `~/ted-ops/ted-board/mockups-backend/supabase/functions/ted-mockups/{index,handler,domain,detail}.ts`.
- Migration: `~/ted-ops/ted-board/mockups-backend/supabase/migrations/20261016160000_ted_mockups.sql`, applied and recorded in migration history.
- Tables: `public.ted_mockups` and `public.ted_mockup_pins`, both with RLS, no policies, and no anonymous or authenticated grants. Only the service role can access them or the feedback RPC.
- Storage: public `ted-mockups` previews and `ted-mockup-detail` full images and per-row metadata, with no public write policy. The private `ted-board-state` bucket holds the current chat URL, served by the authenticated board jobs endpoint. No schema change was needed for zoom or chat. Image URLs are public to anyone who has them; the gallery, feedback, and keys stay private.
- The function uses a service-role client after validating the page or worker credential. Uploads, registration, Ted replies, and resolving pins require the worker credential.

`GET ?key=...` returns `{mockups,pins}` to the page or worker key. Rows include `preview_url`, `preview_width`, and `preview_height`, plus `full_url`, `full_width`, and `full_height` when detail exists. Pins expose normalized `x` and `y` in 0..1; legacy percentage columns remain available and are translated at the API boundary. `POST` accepts `text/plain` JSON or JSON with `key` and `action`:

| Action | Credential | Fields |
| --- | --- | --- |
| `pin` | Page | `mockup_id`, normalized `x` and `y`, `text`; legacy `x_pct` and `y_pct` remain accepted |
| `reply` | Page | `pin_id`, `text` |
| `pick` | Page | `mockup_id`, legacy compatibility only |
| `verdict` | Page | `mockup_id`, `verdict` (`approved`, `needs_work`, or `scrapped`), optional `text` |
| `verdict_note` | Page | `mockup_id`, current `token`, and `text`; coalesces into the verdict during Undo grace |
| `undo_verdict` | Page | `mockup_id`, `token` from `verdict_change`, within five seconds |
| `ted_reply` | Worker | `pin_id`, `text`, optional `decision_id` for acknowledgment deduplication |
| `resolve` | Worker | `pin_id`, `resolved` boolean |
| `upload` | Worker | `project`, `batch`, `title`, `width`, `height`, base64 `jpeg`, optional `sort`, `status`, and base64 WebP `full` with `full_width` and `full_height` |
| `register` | Worker | Same metadata, plus existing UUID JPEG `storage_path` instead of `jpeg` |
| `attach_full` | Worker | Existing `mockup_id`, base64 WebP `full`, `full_width`, and `full_height` |
| `delete_pin` | Worker | `pin_id`; removes the pin and its routing receipts |
| `detail_setup` | Worker | Configures the detail bucket through the Storage API |

The upload action uploads and registers together, removing the newly uploaded object if registration fails. Direct registration checks that the supplied storage object exists. Feedback writes serialize on the image, preserving concurrent appends. Sebastian actions share a bound of 90 receipts per ten minutes. GET paginates database reads internally rather than silently truncating at the default row limit.

Redeploy only the mockups function:

```sh
~/.local/share/supabase/supabase functions deploy ted-mockups \
  --project-ref wqnrortftkffmbeugjky --no-verify-jwt \
  --workdir ~/ted-ops/ted-board/mockups-backend
```

Do not reapply the migration during routine function deployments. The public repository contains only static assets and documentation. No credentials, operational code, image files, or keyed URLs are published there.

## Verification

Verification includes 10 new Deno tests, 12 new Python tests, and eight new browser scenarios at 390x844 and desktop size. The existing nine Deno tests, 13 Python tests, and 12 card-browser scenarios also pass against the integration. The queue-consumer regression tests exercise the real shell flow with external Figma polling and model execution stubbed, verifying that failed Figma polling cannot block mockup work. Real seeded images were decoded and visually inspected in the gallery and fullscreen views. A fresh code review caught and verified the need for source-aware queue delivery, informational picks, and the direct reply runtime.

One minor visual issue remains: a selected pin can retain its unread dot while its thread is open. Closing the viewer redraws the gallery and clears that already-read dot. Physical iPhone keyboard and Safari gesture behavior have not been tested on a device; browser checks used Chromium touch emulation. Drafts survive failed saves within the session, but are not persisted through a page reload. The page loads all mockups and pins, which is appropriate for the current 20-image workload; its backend read is deliberately bounded at 100,000 rows per table.

A live test uploaded one temporary JPEG, added a Sebastian pin, posted a Ted reply, appended eight concurrent replies without loss, retried an acknowledgment without duplication, reopened a resolved thread with a Sebastian reply, and picked the image. SQL checks verified matching decision receipts and table/RPC access restrictions. The existing watcher was paused for those test decisions. Exact test rows, receipts, and the Storage object were removed before the watcher was restored.

## Verdicts

Each image has **Good to go**, **Needs work**, and **Scrap** controls in the gallery and fullscreen viewer. All targets are at least 44px. Verdicts save on one tap, and Undo is available for five seconds. Existing `status='picked'` rows display **GOOD TO GO**. A saved verdict takes precedence over legacy status.

- **Good to go** stores `verdict='approved'`, shows a green **GOOD TO GO** badge, and keeps legacy status `picked`. The owning project or batch worker must treat this as final art to build from. Stop design iteration unless Sebastian changes the verdict.
- **Needs work** stores `verdict='needs_work'`, shows an amber **NEEDS WORK** badge, and opens an optional “what's off?” note. Existing pins count as feedback. The action creates a whole-image pin thread and matching receipt, even without a note. An optional note updates that thread. During Undo grace, it updates the same verdict receipt and initial message, so it cannot double-route or outlive an undone verdict. Notes sent after grace append a new reply. The existing decisions watcher, now polling every 20 seconds on the Mac mini, acknowledges the feedback in that thread and queues it for the existing `markup-watch` / `figma-fast` consumer. It uses the same delivery path as a new pin. Workers inspect the image, existing pins, and full conversation, then post the outcome or blocker on the original mockup using `mockup_reply.py` with the actual pin ID. The five-second undo delay, 20-second decisions poll, and existing 30-second design poll target pickup within a minute when workers are idle. Busy workers or network delays can delay pickup or the outcome. No new routine was created.
- **Scrap** stores `verdict='scrapped'`, greys the preview, and moves the image to its batch's collapsed **Scrapped** group. It preserves the image, pins, and history. Workers must not iterate on scrapped art. Choose another verdict to restore it.

Workers must load current rows with the private `mockup_client.call()` before editing and again before uploading. Check `verdict`, with `status='picked'` as the legacy approval fallback. The router and queue dispatcher both recheck the current verdict, and exclude approved, scrapped, archived, removed, undone, or superseded work as appropriate. Pass these rules to every delegated worker, including batch owners. A queued brief does not override a newer verdict. New feedback on approved or scrapped art receives an explanation in its own pin thread, asking Sebastian to choose Needs work before iteration. A mockup fetch failure leaves unrelated card and Figma briefs available for dispatch.

Verdict receipts wait for the five-second undo window before acknowledgment or routing. Undo restores the previous verdict and legacy status only if its token is still current. It removes that verdict's receipt and its untouched generated pin. If someone already added a reply, the pin is retained and resolved. A newer verdict prevents an older undo from overwriting it.

Storage is additive: nullable `ted_mockups.verdict` and `verdict_change` fields, plus the service-role-only `ted_mockup_verdict` RPC. The page uses the existing `ted-mockups` edge function, which already owns mockup writes. GET includes `verdicts_enabled`; controls remain disabled until the RPC capability check succeeds. Ted must apply the private, idempotent `~/ted-ops/ted-board/mockup-zoom/verdicts-apply.sql`. The verdicts worker must not run that SQL. No schema migration is applied during a function deployment.
