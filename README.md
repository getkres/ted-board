# Ted Board

A phone-first roadmap for Sebastian and Ted. Choose a project, answer a card, or work through a guided task one step at a time.

**Live page:** https://getkres.github.io/ted-board/

Open the private link supplied by Ted. Its access key arrives in the URL fragment, is saved on your device, and stays in the fragment for private tab links. If access is missing or expired, use **Access** to paste the private link again. Do not post that link in issues or commits.

## Using the board

- **All** shows only cards in Needs you. Each project shows Needs you, Ted’s doing, Up next, Done from the last seven days, and a collapsed Killed section.
- Tap a quick choice, send a note, or choose **Ted, you do it**. Confirmed answers move to Ted’s doing and show **sent ✓**. The move menu can file a card into In progress, Done, Killed, or Up next.
- **▶ Steps** opens a full-screen walkthrough. Open links in a new tab, use Back or Done, next, or send a stuck note. Finishing moves the card to Done. Progress is saved on this device, and step changes reset outdated progress.
- Each card keeps a conversation under its actions. Ted replies have a marigold border; your messages sit on the right. The latest three messages show first. Use **show all** for the full thread, or **Mark replies read** to clear the unread dots on this device. Refresh to fetch new replies.
- Every card in Ted’s doing shows its current step or blocker, a colored activity dot, and the update age. Running work turns amber after two hours without a changed update. Cards refresh every 20 seconds while the page is visible, preserving your draft and focused controls.
- The Kres + clients, Fictora, and Bookish project tabs show a Pods strip above their cards. Each pod shows its health, source update age, and current headline. Open a row to see shipped work and current tests. A source older than 26 hours appears red and stale.
- Use the refresh button for the latest cards. Failed requests show a message and keep the card available to retry. The board needs an internet connection.

The pinned **talk to Ted** button opens the current Ted chat in a new tab. It falls back to Claude Code when the current session is unknown. Fresh Ted updates the link after a successful rollover.

## Mockups

The **Mockups** tab has swipeable design batches, fullscreen detail up to 10x actual image scale, numbered feedback pins, threaded replies, unread dots, and image selections. Images open at Fit. Use the wheel, pinch, or zoom buttons to zoom out below Fit or in to 10x, and drag to pan. The percentage shows actual image scale, and tapping it or **Fit** resets the view. Use the edge arrows, Left/Right keys, or phone swipes at Fit to step through the batch without wrapping. Choose **Add pin** to leave feedback. Double-tap a spot for 2.5x, double-tap again to fit, or use **Fit**. Full detail loads above 1.5 times Fit when the preview needs more pixels; older images still open with their preview. Pins stay the same size as you zoom. See [MOCKUPS.md](MOCKUPS.md) for current designs, worker commands, and watcher routing.

See [FRONTDOOR.md](FRONTDOOR.md) for card sessions, Jobs, approvals, Telegram card routing, and the morning handoff.

## Deploying the static page

This public repository deliberately contains `index.html`, `mockups.js`, `mockups.css`, `cave.css`, this README, `REPLIES.md`, `MOCKUPS.md`, and `FRONTDOOR.md`. There is no build step. GitHub Pages publishes the root of `main`.

```sh
git switch -c update-ted-board
git add index.html mockups.js mockups.css cave.css README.md REPLIES.md MOCKUPS.md
git commit -m "Update Ted Board"
git push -u origin update-ted-board
gh pr create --base main --fill
gh pr merge --squash
```

The backend, card data, worker tools, screenshots, and keyed URL are local operational files. They are not part of this public repository. Local deployment and sync instructions are in `~/ted-ops/ted-board/RESULT.md` on the Mac mini. Backend access requires the private page key; the worker key is never included in the page.
