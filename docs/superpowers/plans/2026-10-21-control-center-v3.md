# Control Center v3 Implementation Plan

> For agentic workers: use superpowers:executing-plans for the ordered stack, with a fresh final reviewer.

**Goal:** Rebuild the real Ted Board around Inbox, Spaces, Roadmap, and Mockups in six stacked draft PRs.
**Architecture:** Preserve the existing global card, ControlCenter, and MockupsBoard action paths. Add a DOM-based v3 controller, a responsive layout stylesheet, and an interchangeable theme asset layer. Optional snapshots never prevent existing cards or mockups from loading.
**Tech Stack:** Static HTML, CSS, JavaScript, Supabase Edge Function integration modules, SQL, and headless Playwright.
**Spec:** /Users/vahallo/ted-ops/ted-board/jobs/control-center-v3/BUILD-SPEC.md and mock/.

## Global Constraints
- Six branches and draft PRs, each based on the previous. No main pushes, merges, deployments, database writes, sends, or spend.
- Take B velvet and zine paper, with condensed Archivo bold caps. No cut-out letters, gradients, or em dashes. Oxford comma.
- Preserve page-key auth, guided mode, fresh Ted, control actions, pins, verdicts, batch approval and undo, supersede, and pod pulse.
- Serve the folder. Test at 390 by 844 and 1440 by 960; screenshots and clip checks for every view.
- Never read ~/Documents or print secrets. Durable routines belong on the mini; this build creates none.

## Review Focus
- Missing snapshot schema or capabilities must show honest empty states and leave existing actions usable.
- Key changes must clear private data and invalidate requests across every new view.
- Navigation history, unknown deep links, long names, and keyboard shortcuts must remain safe.
- Database approvals and money or send decisions must never be swiped or put on automatic timers.
- Mockup feedback must retain a reason or stroke, preserve undo tokens, and avoid losing drafts during polling.

### Task 1: Theme and shell
- [ ] Add theme.css, v3.css, v3.js, compressed texture assets, and reusable bear art derived from supplied mock source.
- [ ] Update index.html navigation and history while preserving legacy controllers.
- [ ] Add browser fixture harness; prove four tabs, auth, navigation history, command search, and responsive clipping.
- [ ] Capture shell screenshots, commit, push branch cc-v3/01-shell, and open draft PR against main.

### Task 2: Inbox and snapshots
- [ ] Add Yours, item detail, Decided, Routines, and Woke from live cards, control vetoes, and optional snapshots.
- [ ] Wire card options, control tools, keyboard paths, safe swipe behavior, and review choices only when supported.
- [ ] Add snapshot integration module, contracts, and migration plus job-dir apply.sql with backup and rollback. Do not execute SQL.
- [ ] Test missing feeds, actions, and all Inbox splits at both widths; open cc-v3/02-inbox draft against PR 1 branch.

### Task 3: Spaces
- [ ] Add ten ordered spaces, space, pod, and agent drill-downs using pod pulse plus optional pods snapshots.
- [ ] Show absent data as not logged; expose review ledger, outputs, runs, and related card actions.
- [ ] Test deep links, sibling navigation, keyboard paths, and long agent names at both widths; open cc-v3/03-spaces draft against PR 2 branch.

### Task 4: Roadmap
- [ ] Render wall and line board from roadmap snapshots with status, dates, and linked Yours cards.
- [ ] Test all ten lines, absent data, and responsive table or stacked cards; open cc-v3/04-roadmap draft against PR 3 branch.

### Task 5: Mockups
- [ ] Extend MockupsBoard with wall, filters, decision log, direction rounds, lineage compare modes, triage, and normalized markup.
- [ ] Retain existing API behavior and feature-gate schema-dependent good_with_fix, strokes, and round metadata.
- [ ] Add D5 migration and integration contracts to apply.sql, with backup and rollback.
- [ ] Test verdict validation, pins, batch undo, compare, markup, triage, and both widths; open cc-v3/05-mockups draft against PR 4 branch.

### Task 6: Cleanup and QA
- [ ] Remove obsolete tab entries, keep reused control tools and all existing behaviors reachable.
- [ ] Run full browser matrix, keyboard, history, private-key reset, clip, console, copy, and gradient checks.
- [ ] Fresh reviewer checks against spec and reference frames. Resolve material issues, document remaining limitations honestly.
- [ ] Open cc-v3/06-qa draft against PR 5 branch. Write job-dir REPORT.md with all links, SQL requirements, and gaps.
