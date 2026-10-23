# Ted Board, Control Center v3

A static, phone-first board for Sebastian and Ted. GitHub Pages serves the root of `main`, with no build step. Work on this eight-PR stack stays on its feature branches, in draft, until Ted reviews and integrates it.

Phones narrower than 760px open Inbox in Decide: one card, real recorded choices, Tell Ted, and Later. Decisions disappear into a five-second cancellation window, then use the existing action API. Undo cancels every decision still in that window. Failed saves restore the card. Confirmed dismissals stay on this browser until the ask changes; Later lasts only for the page session. FYI cards share one updates pile, cleared with one Got it through the existing card actions. Reloading cancels actions still in the window.

List opens the full board in one tap. The choice lasts for the browser tab session. Desktop starts in List, with a Decide button for the same stack. Explicit deep links to other views retain their target.

The four primary tabs are Inbox, Spaces, Roadmap, and Mockups. Inbox defaults to Yours, with Ted decided, Routines, and Woke alongside it. Spaces follows the authenticated line directory into pods and agents. Roadmap shows Now, Next, Later, and Shipped. Mockups includes the review wall, rounds, compare modes, triage, and markup.

Private access stays in `#k=` and is remembered on the device. Deep routes use `#tab=inbox`, `spaces`, `space:line3`, `pod:line3/media`, `agent:line3/meta-media-buyer`, `roadmap`, `roadmap:line1`, `mockups`, or `mockups:<encoded batch key>`. Browser Back and Forward work. Never publish a keyed URL.

Use the desktop command field to find a view, space, or card. On phone, Inbox's “Rules, sprint, batches, and jobs” disclosure also contains All project cards, so active, queued, completed, and killed cards retain their conversations and guided steps. Talk to Ted, Fresh Ted, and the Access footer retain their existing behavior.

## Theme and layout

Take A uses Kres poster typography: locally bundled Archivo condensed bold caps, red `#e2402a`, white, near-black, hard 2px structural rules, and a live `TED HANDLED N` stamp. System light and dark preferences are supported, with optional `data-theme="light"` or `data-theme="dark"` overrides on the root element. Both modes retain the same red. There are no textures, cut-out letters, or gradients. `theme.css`, `theme.js`, and `assets/` contain the theme. `v3.css`, `spaces-v3.css`, `roadmap-v3.css`, `mockups-v3.css`, and `markup-v3.css` contain layout and interaction styling. Alternate themes can replace tokens and artwork without changing view markup.

## Data and actions

Existing card, guided-mode, control, pod-pulse, pin, reply, verdict, whole-batch approval, Undo, and archive/supersede paths remain. The old Control tab is replaced by the Inbox disclosure, which opens its preserved Veto, Rules, Sprint, and Batches workflows. No browser action applies SQL or directly sends or spends.

Snapshot feeds and new mockup writes are optional and capability-gated. Missing data says not logged. A local drawing remains a draft until the backend acknowledges its exact normalized path and crop. Needs work requires a reason before saving. Round approval requires a reason and the supported round transaction. Existing five-second verdict and whole-batch Undo tokens remain owned by the original API.

The public clone omits the private backend and workers. Read [backend integration](backend-integration/README.md) before enabling snapshots, review choices, Good, one fix, round picks, or saved strokes. Proposed SQL is in `migrations/`. The build job contains `apply.sql` with opt-in backup and apply phases, plus manual rollback instructions. SQL was not run by this build.

## Local verification

Serve the folder, then run the offline fixture tests. They never use live credentials or write to a live backend.

```sh
python3 -m http.server 8763
# In a second terminal, with Playwright available:
QA_THEME=light QA_OUT=qa/pr7/light node qa/run.cjs
QA_THEME=dark QA_OUT=qa/pr7/dark node qa/run.cjs
```

`qa/decide.cjs` covers 390x844 decisions, Undo, Later, updates, the empty bear, existing action payloads, failed saves, account resets, new asks during the grace period, keyboard isolation, reduced motion, the 760px boundary, and horizontal overflow. Legacy list tests explicitly select List through the shared fixture.

`PLAYWRIGHT_MODULE` may name an installed Playwright module. Set it in the environment for every browser command when the machine's default fixture path is unavailable. Screenshots and JSON reports are under `qa/pr1/` through `qa/pr7/`. Run the theme suites sequentially. `QA_THEME` controls browser color preference, and `QA_OUT` preserves earlier evidence. The Kres theme group also checks explicit overrides, locally loaded fonts, and live stamp counts. Reports contain synthetic data only. Live authorization, private handler integration, server-side receipts, watchers, and database migrations require separate staging verification by Ted.

Additional existing action contracts remain documented in [MOCKUPS.md](MOCKUPS.md), [FRONTDOOR.md](FRONTDOOR.md), [REPLIES.md](REPLIES.md), and [APPLY.md](APPLY.md).

Final verification notes and review resolutions are in [CONTROL-CENTER-V3-QA.md](docs/CONTROL-CENTER-V3-QA.md). The complete local fixture suite is `node qa/run.cjs`.

## Supabase table grants

New public Supabase tables require explicit grants and RLS in their creating migration. Ted Board uses `service_role` only. See [AGENTS.md](AGENTS.md) for the SQL template, the offline check (`python3 scripts/check_data_api_grants.py`), and the local backend boundary, and [the grant audit](docs/data-api-grants-audit.md) for historical coverage.
