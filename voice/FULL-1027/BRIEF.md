# Hey Ted: real Ted plus barge-in (2026-10-27)

Never use an em dash; always use the Oxford comma.

Sebastian: "fix it then." The 10-26 repair (../README.md, ../DEBUG-1026/) made the Jabra loop work, but it left two gaps:
A. Voice goes to a separate, answer-only Claude conversation with tools off. It cannot do anything or see what Ted knows.
B. No barge-in: wake detection is gated during playback, so he cannot cut Ted off.

Source: ~/ted-ops/ted-board/jobs/card-c-hey-ted-voice-1022/worktree/voice (runtime copied to ~/ted-ops/voice/app, install.py). Mac mini only.

## A. Voice reaches the main Ted
1. Route spoken requests into the MAIN Ted conversation (the pinned desktop session) by reusing the existing local-inbox delivery in ~/ted-ops/ted-board/fresh_ted.py (pinned session identity, peerToken, procStart checks). Do not invent a second path, and do not resume the desktop session with a separate CLI process.
2. Tag voice messages so main Ted knows to answer short and spoken, e.g. prefix "[voice] ". Speak main Ted's reply back: read the reply from the session transcript (session.py already polls transcripts under ~/.claude/projects/-Users-vahallo-Claude-Code---Fictora) and speak only the final assistant text of that turn, trimmed to something speakable (skip tool output, links, and code; cap length; say "rest is on screen" if cut).
3. Fallback: if the main session's inbox is unavailable or busy beyond ~20 s, the existing account 2 voice conversation answers, but give it READ-ONLY context: allow Read, Grep, and Glob scoped to ~/ted-ops/ted-state, ~/biz, ~/kres, and ~/ventures so it can answer status questions. Inject the Ted voice card (find it in the UserPromptSubmit hook config) into its system prompt. Anything that asks for an action while in fallback is queued to main Ted via the inbox when it returns, and voice says so.
4. Keep every existing billing guard: account 2 Max OAuth only, never API billing, ElevenLabs only under the current approval (expires 10-29 8:11pm PT), no new charges.

## B. Barge-in
1. The Jabra Speak2 55 does hardware echo cancellation when both mic and speaker are the Jabra over USB. Keep wake detection running during playback instead of gating it.
2. On "Hey Ted" or "Ted, stop" while speaking: stop playback within 300 ms, then listen for the new request. Self-trigger guard: during playback require a higher wake score plus Whisper confirmation, and ignore a wake whose transcript matches the text currently being spoken.
3. Measure it. Extend DEBUG-1026/test_voice.py: Ted plays a long reply on the Jabra while the mini's speaker says "Hey Ted, stop" mid-reply. Pass = playback halts within 300 ms and the follow-up request is handled. Also run 10 long replies with no interruption and confirm zero self-triggers. Record everything in FULL-1027/acceptance.json.

## Done
Install on the mini with install.py, verify co.ted.voice is healthy, update ../README.md, and write REPORT.md here with what he should say to test each piece. Commit the source on its job branch; do not push to any shared remote. Do not change Claude, Stripe, ElevenLabs, or any billing settings.
