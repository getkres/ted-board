# Report review state fallback

The report observer previously searched every sentence for review phrases. It
matched `ted review` inside `completed review` and `selected reviews`, and it
treated `no pending review` as unfinished work. The inferred workflow kept Done
cards in the open ledger and produced false dead-lane alarms.

The canonical runtime bundle now keeps an explicit `workflow.json`
`review_required` value authoritative, including `false`. Only when that field
is absent does it infer a review hold from a phrase at the start of a line or
in the latest `LIVE_STATUS:` line. Markdown headings, bullets, emphasis, and a
line-start `Status:` label retain their status meaning. The fallback recognizes
an explicit `awaiting design selection` hold as review work, preserving that
existing pending decision.

It ignores fenced examples and incidental prose. Negation before a phrase, or
a directly completed/closed predicate after it, cancels that phrase. Words in
unrelated suffixes, such as `needs ted review before the PR closes` or `needs
ted review of the no-op fix`, do not cancel it. Separate status clauses can
still express a real hold, for example `no SQL or sends; needs ted review`.

Pending SQL packets and actual PR delivery chains retain their existing
independent evidence. This change does not close cards, rewrite reports, edit
queues, clear dispatch holds, or replay approvals.

The old generic `not merged`, `not deployed`, and `not live` prose signals no
longer create review workflow records. Actual unfinished deployment remains
represented by its structured PR, deployment, or verification evidence.

The implementation is part of `reconciler-runtime.patch`, and the manifest pins
its reconstructed checksum. The regression suite exercises the real snapshot
and planner with disposable fixtures:

```sh
python3 runner-fix/report_review_status_test.py
```

To check a rebased private candidate, set `TED_RUNTIME_SOURCE` to that candidate
directory and run the same command. The candidate must retain all newer private
runtime changes. Apply only the reviewed report-classification diff to the
installed mini runtime after checking its exact current hash. A read-only
reconciler dry-run verifies the resulting item set. Incident source closure
remains with its existing owner.
