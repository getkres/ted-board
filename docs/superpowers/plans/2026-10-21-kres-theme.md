# Kres Theme Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan. Steps use checkbox syntax for tracking.

**Goal:** Apply Sebastian's selected take A poster theme while preserving every existing view and action.

**Architecture:** Replace the theme tokens, typography, and Ted artwork. Keep all layout files and interaction handlers intact. Remove the forced zine theme marker, update the existing handled-count copy, and self-host the fonts.

**Tech Stack:** Static HTML, CSS, JavaScript, Node, and Playwright.

**Spec:** The user's 2026-10-21 Kres theme request, `../../../../BRIEF-kres.md`, and the supplied take A mockups.

## Global Constraints

- Work in the existing worktree on `cc-v3/07-kres`, based on `cc-v3/06-qa`.
- Use Archivo condensed uppercase display, `#e2402a`, white, near-black, hard 2px structural rules, and a truthful `TED HANDLED N` stamp.
- Honor system light/dark and explicit `data-theme` overrides. Keep the same red in both modes.
- Preserve layout, routes, controls, and behavior. Remove unused B assets and font requests.
- No textures, gradients, ransom letters, or em dashes. Never read `~/Documents`.
- Run `node qa/run.cjs` at 390 and 1440, commit screenshots, push only the task branch, and open a draft PR against `cc-v3/06-qa`. Never merge.

## Review Focus

- Dark surfaces, inverted panels, form controls, and modal text remain legible.
- System preference changes work, and explicit theme overrides win.
- Long titles, counts, and condensed text remain unclipped at 390 and 1440.
- Stamp count remains derived from completed decisions, including after updates.
- All existing action handlers and layout CSS are unchanged.

### Task 1: Theme replacement

- [x] Run the baseline suite and the new theme check before changing the theme.
- [x] Replace `theme.css`, update the artwork in `theme.js`, bundle fonts and licenses in `assets/`, and delete velvet and paper assets.
- [x] Make only theme-related HTML and `v3.js` integration edits, and update theme documentation.
- [x] Run the theme checks, inspect screenshots, and resolve any visible defects.

### Task 2: Verification and delivery

- [x] Run the full suite with evidence under `qa/pr7/`, including both themes and viewport sizes.
- [x] Obtain an independent review and fix material findings.
- [x] Check the final diff, commit, push `cc-v3/07-kres`, and create the requested draft PR with screenshots.
- [ ] Append the outcome, QA evidence, and PR link to the job's `REPORT.md`.

## Verification record

- Original take B baseline: 13 verification groups passed before the theme replacement.
- New theme check failed against the original velvet ground, then passed after replacement.
- Independent review found an invisible selected-tab count in dark mode. The new regression failed with white text on white, then passed with the contrasting paper token.
- Intentional uppercase styling required authored-title assertions to read `textContent`. No action assertions were removed.
- Parallel browser attempts on the temporary local server lost local script responses. Final full verification runs use the ordinary sequential suite, one theme at a time.
- Visual review found inherited serif guided instructions. A regression check failed on `Fraunces, Georgia, serif` before the theme-only Archivo override.
- Final full suite: light 14/14 and dark 14/14, with 78 screenshots each, and all reported console/visual checks zero.
