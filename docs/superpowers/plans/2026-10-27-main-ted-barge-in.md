# Main Ted and barge-in implementation plan

> For agentic workers: use the supplied brief, focused parallel ownership, test-first fixes, and a final independent review.

**Goal:** Route voice to the pinned main Ted, supply a guarded read-only fallback, and verify Jabra interruption.

**Architecture:** Keep fresh_ted as the sole main inbox transport. A routing bridge selects main or account 2, preserves request identity, and retries only actions known not to have been delivered. Keep the direct Jabra AudioQueue capture and explicitly bound playback, and confirm high-score playback wakes locally.

**Tech stack:** Python, Swift CoreAudio, openWakeWord, Whisper, and the existing subscription CLI.

**Spec:** /Users/vahallo/ted-ops/voice/FULL-1027/BRIEF.md

## Constraints

Mac mini only. Preserve account 2 Max OAuth guards and the existing ElevenLabs expiry. No billing changes, new charges, shared remote push, or separate CLI resume of main Ted. Use the Oxford comma, and no em dash.

## Review focus

- Busy or absent main inbox: fallback after about 20 seconds, with no accidental second execution.
- Transcript tools or another user turn: only the matching final text may be spoken.
- Read-only fallback paths, including symlinks: no escape or mutation tools.
- Self-wake during speech: count provisional stops as interruptions and reject matching speech.
- Stale native playback callbacks: cannot clear a newer playback or cancel its file.

## Tasks

- [x] Routing: add test-first final reply extraction and speakable cleanup, main availability selection, scoped fallback, voice card injection, and durable action queue in session.py, account2.py, routing.py, and tests. RoutedBridge provides deliver, poll, assert_current, tick, and close.
- [x] Barge-in: add test-first Jabra playback wake gate, provisional stop, Whisper and echo checks, bare stop handling, and native stop telemetry in loop.py, core.py, runtime.py, Audio.swift, daemon.py, and tests.
- [x] Acceptance: extend DEBUG-1026/test_voice.py with installed service fixtures, acoustic interruption, real routed follow-up, ten uninterrupted trials, and raw evidence. A marker enables diagnostics only during the test.
- [x] Install: include new runtime modules, preserve the approved app launcher, run the full suite, compile Swift, install with install.py, and inspect fresh ready events.
- [x] Source handoff: ran and recorded physical acceptance, reviewed the diff, fixed material findings, updated README.md and FULL-1027/REPORT.md, saved acceptance.json, and prepared the local source commit without pushing. Overall acceptance remains false; the blockers are recorded below.

## Execution notes

The worktree already exists on feat/hey-ted-voice-1022. The eight preexisting changed files contain the October 26 repairs and must be preserved. Baseline: 54 tests, 52 passed, two optional native tests skipped. The initial pin had no local PID. Native Desktop UI and registry evidence identified the originating session, then the existing Fresh Ted lifecycle independently rolled the pin to Ted10-27. The live receiver explicitly holds the inbox message; no competing main CLI or Claude policy change was made. High-score pause precedes Whisper confirmation because waiting for the existing verifier is structurally longer than 300 ms. Measure and report both detection-to-stop and stimulus timing.

Final selection: restored the original ONNX model after candidate acoustic failures. Playback uses .99 twice, VAD, a recent four-frame maximum RMS floor of -45 dBFS, Whisper confirmation, and source-audio echo checks. Final source checks: 140 tests, 137 passed, and 3 optional native tests skipped; Ruff and diff checks passed.

Current hardware evidence: fallback end-to-end and bare stop passed. The latest Hey Ted interruption paused promptly but failed Whisper confirmation. The latest no-self-trigger run completed three trials, with two unwanted pauses in the third, then stopped when the Jabra disconnected. It recovered automatically. The preceding -50 dBFS build completed ten trials, with one unwanted pause. Neither run meets the zero-self-trigger acceptance requirement. A stable, quiet-room repeat is pending the user's answer.

Main receipt remains blocked by the receiver's permission policy. The process-scoped exception is prepared but unapplied because BRIEF.md forbids Claude setting changes. The remaining work requires that explicit exception and a completed passing acoustic run.
