# Mockups on Ted Board

Shipped October 16, 2026. Open [Ted Board](https://getkres.github.io/ted-board/) with your existing private link, then choose **Mockups**. Access uses the same page key as the cards. Never put the private link or either key in Git, screenshots, or messages.

## Reviewing designs

Batches appear newest first, with a project filter and a swipeable row of large images. Open an image for fullscreen review. Tap a detail to place a numbered pin, type a comment, and choose **Send comment**. Pin positions follow the image as you resize, pan, or zoom. Use pinch gestures or the zoom controls to inspect a detail. **Add pin** places a pin in the visible area for keyboard users.

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

Uploads preserve aspect ratio, flatten transparency onto white, remove metadata, convert to JPEG, and resize images taller than 1,600 pixels. A JPEG must be no larger than 4 MB. Each object receives a UUID path. Multiple files use the supplied title as a prefix followed by each filename. `--status picked` can register an already chosen design without a Sebastian receipt. `--sort` controls order within the batch. The uploader prints each confirmed ID; if a later file fails, earlier confirmed uploads remain registered.

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

Every Sebastian pin, reply, or pick creates a `public.ted_decisions` row atomically with the action. Pin and reply receipts use the pin ID as `item_id`. Pick receipts use the mockup ID. The note contains the full comment or selection, image title, project, batch, mockup ID, and coordinates. Picks identify coordinates as applying to the whole image.

For pin feedback, the watcher posts a short acknowledgment in the same pin thread, then appends the task to `~/ted-ops/markup-watch/design-queue.md`. Queue entries include the exact reply command. Ted or a delegated design worker must reply in that pin thread with the outcome or blocker, using `mockup_reply.py`. Replies must be plain text, contain no U+2014, and stay within 2,000 characters. Resolve a pin after the requested change is complete. New design variants should be uploaded into a new batch.

The watcher sends its acknowledgment with `--decision-id` semantics through the client. The database deduplicates that acknowledgment by decision ID, and stable queue markers prevent repeated design work if a route is retried. Routing failures remain eligible for retry even after a Telegram acknowledgment. Test notes starting with `test-` never post a mockup reply or enqueue design work.

Picks enter the queue as completed, informational selection records. They do not launch design work and have no pin thread, so the watcher does not pass a mockup ID to the pin reply command. Any follow-up belongs in a related actual pin thread.

The existing fast queue consumer uses the new `~/ted-ops/markup-watch/design_dispatch.py` to distinguish mockup, card, and legacy Figma briefs. Mockup workers upload to Ted Board and reply to the original pin. Card workers retain their exact card outcome command. Existing Figma briefs retain their original delivery surface. A failed Figma poll does not prevent independent design briefs from running. Queued mockup commands use the direct Command Line Tools interpreter.

## Backend and deployment

- Function: `ted-mockups` on Supabase project `wqnrortftkffmbeugjky`, deployed independently of the card function with JWT verification disabled and the existing page and worker secrets.
- Private source: `~/ted-ops/ted-board/mockups-backend/supabase/functions/ted-mockups/{index,handler,domain}.ts`.
- Migration: `~/ted-ops/ted-board/mockups-backend/supabase/migrations/20261016160000_ted_mockups.sql`, applied and recorded in migration history.
- Tables: `public.ted_mockups` and `public.ted_mockup_pins`, both with RLS, no policies, and no anonymous or authenticated grants. Only the service role can access them or the feedback RPC.
- Storage: public `ted-mockups` bucket, UUID JPEG paths, and no public write policy. Image URLs are public to anyone who has them; the gallery, feedback, and keys stay private.
- The function uses a service-role client after validating the page or worker credential. Uploads, registration, Ted replies, and resolving pins require the worker credential.

`GET ?key=...` returns `{mockups,pins}` to the page or worker key. `POST` accepts `text/plain` JSON or JSON with `key` and `action`:

| Action | Credential | Fields |
| --- | --- | --- |
| `pin` | Page | `mockup_id`, `x_pct`, `y_pct`, `text` |
| `reply` | Page | `pin_id`, `text` |
| `pick` | Page | `mockup_id` |
| `ted_reply` | Worker | `pin_id`, `text`, optional `decision_id` for acknowledgment deduplication |
| `resolve` | Worker | `pin_id`, `resolved` boolean |
| `upload` | Worker | `project`, `batch`, `title`, `width`, `height`, base64 `jpeg`, optional `sort` and `status` |
| `register` | Worker | Same metadata, plus existing UUID JPEG `storage_path` instead of `jpeg` |

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
