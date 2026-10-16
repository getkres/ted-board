# Ted Board

A phone-first roadmap for Sebastian and Ted. Choose a project, answer a card, or work through a guided task one step at a time.

**Live page:** https://getkres.github.io/ted-board/

Open the private link supplied by Ted. Its access key arrives in the URL fragment, is saved on your device, and is removed from the address bar. If access is missing or expired, use **Access** to paste the private link again. Do not post that link in issues or commits.

## Using the board

- **All** shows only cards in Needs you. Each project shows Needs you, Ted’s doing, Up next, Done from the last seven days, and a collapsed Killed section.
- Tap a quick choice, send a note, or choose **Ted, you do it**. Confirmed answers move to Ted’s doing and show **sent ✓**. The move menu can file a card into In progress, Done, Killed, or Up next.
- **▶ Steps** opens a full-screen walkthrough. Open links in a new tab, use Back or Done, next, or send a stuck note. Finishing moves the card to Done. Progress is saved on this device, and step changes reset outdated progress.
- Use the refresh button for the latest cards. Failed requests show a message and keep the card available to retry. The board needs an internet connection.

## Deploying the static page

This public repository deliberately contains only `index.html` and this README. There is no build step. GitHub Pages publishes the root of `main`.

```sh
git add index.html README.md
git commit -m "Update Ted Board"
git push origin main
```

The backend, card data, worker tools, screenshots, and keyed URL are local operational files. They are not part of this public repository. Local deployment and sync instructions are in `~/ted-ops/ted-board/RESULT.md` on the Mac mini. Backend access requires the private page key; the worker key is never included in the page.
