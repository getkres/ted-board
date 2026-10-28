# Hey Ted on the Mac mini

The service is `co.ted.voice`, on this Mac mini only, with a Jabra Speak2 55 connected by USB. Say "Hey Ted," followed by a question, and wait for the reply. The listening chime follows local neural wake detection and medium.en Whisper confirmation. A second tone confirms acceptance by the selected Ted conversation.

The October 26 repair replaces the unintelligible VoiceProcessingIO capture graph with direct AudioQueue capture, bound to the Jabra input device UID at 16 kHz, 16-bit mono. Playback uses a separate engine bound to the Jabra output. Input and output remain bound when AirPods change system defaults. Ted Voice retains its previously granted microphone permission through the existing signed app launcher. Neither a running launchd process nor nonzero microphone RMS alone establishes intelligible capture.

Wake detection now stays active while the Jabra plays. During playback, two wake scores at or above 0.99, voiced audio, and a recent frame at or above -45 dBFS provisionally pause playback, and local Whisper confirms the wake before accepting a new request. Only five observed short recognition ambiguities can receive a vocabulary retry after a strong playback candidate. Empty, non-speech, unrelated, and extended transcriptions cannot use that retry. Request transcription and source-audio transcription remain unprompted, and the echo check still applies to both initial and retried recognition. An ambiguity confirmed as a stop can be removed once from that same captured request; it never becomes a general command alias. Whisper compares the microphone capture with a short audio slice ending at the native pause position. This prevents a quoted wake phrase later in the reply from vetoing a real interruption now. If the capture matches that recent audio, or confirmation rejects it, playback resumes. Say "Hey Ted, stop," wait for the listening tone, and give the next request. The Jabra supplies hardware echo cancellation when its USB input and output are both selected. Native stop acknowledgments provide detection-to-stop timing; they are distinct from the time spent speaking the wake phrase or waiting for Whisper.

October 28 room diagnosis: an external Daniel clip saying "Hey Ted, stop" decoded as "Th head, stop" after a strong wake candidate. Both medium.en and small.en recognized the same temporary capture with the existing proper-name vocabulary retry. That exact three-word ambiguity is now eligible for the guarded retry during playback. It is never a direct command alias, and broader phrases remain excluded. The card report records post-deployment acoustic results.

October 28 reconciliation: main delivery remains unverified. Fresh Ted's existing launch code already contains the proposed inbound exception, but the currently pinned process was launched without it. A new authenticated inbox probe received neither a matching user acknowledgment nor a final reply within 65 seconds. This reconciliation did not change settings, restart main Ted, or attest bypass authority. Fallback replies do not establish main delivery. The October 27 files are historical evidence; the current card REPORT.md records the latest checks.

Voice first tries the main Ted session pinned by `ted-board/frontdoor/fresh/current.json`, using the existing authenticated `fresh_ted.py` local inbox transport. It never starts a separate CLI process to resume that desktop session. Spoken requests carry a `[voice]` marker. Only the matching turn's final assistant text is spoken, with code and URLs removed and length capped. Longer replies end with "Rest is on screen."

If the pinned inbox is unavailable or stays busy for about 20 seconds, the dedicated account 2 conversation supplies the fallback. It has only Read, Grep, and Glob within `~/ted-ops/ted-state`, `~/biz`, `~/kres`, and `~/ventures`, with resolved-path restrictions. The fallback receives the Ted voice card from the configured prompt hook, without running that hook. It cannot execute actions. Action requests are saved privately for the main inbox and announced as queued. Only an exact request marker in the main transcript confirms receipt. Socket success alone is insufficient. Unacknowledged sends remain saved for review and are never sent twice; requests known not to have reached the socket retry automatically for at most ten minutes. Older or undated pending requests become expired and require a fresh request. Delivered action text is removed from the persistent queue. Metadata-only transcript notices cannot confirm receipt. The fallback never claims that it queued an action itself.

The fallback verifies Claude.ai Max OAuth authentication and the current OAuth usage endpoint on every turn, refuses enabled or unknown extra usage, removes API and alternate-provider environment variables, and uses the authenticated account 2 CLI subscription. It never falls back to API billing. Session continuity is recorded privately in `claude-voice-session.json`. MCP, hooks, plugins, and mutation tools remain disabled in this fallback.

Whisper runs locally. The short wake verifier uses the installed medium.en model because small.en misheard the recorded test wake as "Hated reply," while medium.en recognized "Hey Ted replied" from the same clip. The approved ElevenLabs Brian voice uses existing credits only, while the installed approval is active and the subscription reports disabled overages. The current approval expires October 29 at 8:11 p.m. Pacific, October 30 at 03:11 UTC. The daily character cap still applies. If the guard refuses ElevenLabs or rendering fails, local Daniel speech is used. A log event identifies the renderer actually used. No new charges are authorized by the voice channel.

Say "Ted, stop listening" to pause, or "Hey Ted, stop listening." Pause persists across service restarts, and voice cannot resume a closed microphone. To pause manually:

```sh
touch ~/ted-ops/voice/paused
```

To resume an already loaded service:

```sh
rm -f ~/ted-ops/voice/paused
```

If it is unloaded, resume with:

```sh
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/co.ted.voice.plist
```

Check it with:

```sh
launchctl print gui/$(id -u)/co.ted.voice
tail -f ~/ted-ops/voice/logs/events.jsonl
```

Wait for a fresh `audio_ready` and `capture_audio_ready` after a restart. The `debug-audio` flag enables five-second PCM levels and wake score summaries. Logs omit ordinary transcript text. Short microphone captures are temporary and deleted after transcription; uncertain deliveries are stored privately for review. Only action requests known not to have been sent, captured less than ten minutes ago, are eligible for automatic delivery to the main inbox.

The repeatable synthetic room test uses the Mac mini speaker as the external voice source, the Jabra microphone for capture, and the Jabra speaker for Ted's reply:

```sh
python3 ~/ted-ops/voice/DEBUG-1026/test_voice.py --mode full --continue-on-failure --output ~/ted-ops/voice/FULL-1027/retest.json
```

The default test requires a real wake, Whisper transcription, a routed reply, rendering, and completed playback. The full acceptance mode additionally plays local long-reply fixtures through the installed service, interrupts one acoustically from the Mac mini speaker, checks a real follow-up reply, and runs ten uninterrupted trials. See `FULL-1027/REPORT.md` and `FULL-1027/acceptance.json` for measured results and limitations.

Source is in `~/ted-ops/ted-board/jobs/card-c-hey-ted-voice-1022/worktree/voice`. Runtime is copied to `~/ted-ops/voice/app`. The installer refuses to create a routine on non-mini hardware and preserves the approved app launcher:

```sh
cd ~/ted-ops/ted-board/jobs/card-c-hey-ted-voice-1022/worktree/voice
python3 install.py --python ~/ted-ops/voice/.venv/bin/python --models ./models --load
```

The installed model is the original local openWakeWord ONNX model. An October 27 candidate added 400 explicit bare-stop clips and improved offline bare-stop validation from 54/60 to 60/60, but failed its room acceptance attempts. It was rolled back. Those validation clips selected the model epoch, and the separate macOS examples were synthetic, so neither establishes natural voice accuracy. The current source and hardware evidence, including failures, are in `FULL-1027/REPORT.md` and `FULL-1027/acceptance.json`. A synthetic room test does not establish performance at every position or a household false-trigger rate.

For a short, explicit recognition diagnostic, the service requires debug mode plus both `diagnostics-enabled` and `diagnostic-wake-capture` marker files. It retains at most five private microphone WAV and JSON pairs under `diagnostics/verification`. Remove both markers and delete those private captures after inspection. Ordinary event logs omit transcript text.
