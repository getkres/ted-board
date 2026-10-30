# Taste check frontend

A phone-first, static interface for a private local taste service. Serve this directory at `/taste/` on the same origin as its API. It uses no external fonts, analytics, paid APIs, or third-party requests. Opening it on GitHub Pages without a local service shows a recoverable loading error.

The service supplies pairs with the same format, business, and audience. Each creative has a brief and an archive source label. A and B have equal visual weight. Tap either creative to inspect its full frame, then choose A, B, or skip. An optional reason stays in the form until the save receipt arrives. Network retries send the same offer ID and payload, so the service must enforce idempotency.

Private media, catalog provenance, choice history, deployment configuration, and server code remain local. Never commit those files to this public repository.

The frontend expects these same-origin JSON routes:

- `GET api/next`: `{id, seq, a, b, stats}`. Each creative has `{id, business, format, audience, brief, source_label}` and either a relative `media` URL or exact saved `text`.
- `POST api/pick`: `{id, choice: "a" | "b" | "skip", why}`. Requires JSON and `X-Taste-Request: 1`. Returns `{id, seq, stats}`. A retry with the same ID and choice must return its existing receipt. A stale or changed submission returns HTTP 409.
- `GET api/summary`: the current statistics.

Stats are `{total, decisive, repeat_checks, repeat_agreements}`. Skipped repeats do not count toward self-agreement. Prior answers and repeat markers are never sent with the next pair. The page pauses after 25 choices per visit, and Keep going starts another session. The server owns global repeat scheduling and pair selection.

For private phone access, bind the local service only to the intended private interfaces, and use the mini's LAN address or existing Tailscale access. Do not expose the service through a public tunnel. A local process board lives at `process/`.

Verification uses Google Chrome, a 390px phone viewport, synthetic choice history, and a separate local service instance. The static page also supports 320px, tablet, and desktop widths, keyboard focus, full-size inspection, and reduced-motion preferences.

Run the portable synthetic UI checks against a served page with:

```sh
PLAYWRIGHT_MODULE=/path/to/playwright TASTE_QA_URL=http://127.0.0.1:8767/taste/ node taste/qa.cjs
```

The script launches the installed Google Chrome, intercepts the local API with synthetic state, and never records real choices.
