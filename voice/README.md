# Hey Ted on the mini

Status: staged for Ted review. The mini currently has no microphone. Jabra routing, microphone consent, room acoustics, and echo cancellation require the arriving speakerphone. Brian synthesis stays disabled until the exact credit-use draft is approved.

When the Jabra arrives, plug it into the Mac mini by USB. If macOS asks whether Ted Voice may use the microphone, click Allow once. The service selects Jabra input and output by name and retries when devices change. If consent was denied earlier, enable Ted Voice in System Settings > Privacy & Security > Microphone.

Say "hey Ted," then your request. A small local Whisper model confirms each neural wake candidate before the chime or any playback interruption. This normally adds about 0.6 to 1 second to activation and prevents music candidates from chiming. A short chime marks listening. Recording ends after 1.2 seconds of silence, with a 30-second safety limit. A softer tone means the tagged voice request actually appeared in live Ted's transcript. No sent tone means delivery has not been confirmed. If live Ted is unavailable, the loop says so, saves a private local copy, and attempts to post it on this card. Uncertain deliveries are never automatically resent.

Ted's final text is spoken locally while Brian approval is pending. The existing Brian helper is wired behind an expiring approval, a daily character cap, and a subscription check that requires usage-based billing to be disabled. Markdown, links, and code are removed. Longer replies use the opening gist and end with "Details are on your phone." The spoken output also removes its own wake and pause phrases.

Say "hey Ted" during speech to interrupt it. Detection during playback requires native voice processing, a 0.99 wake score, two consecutive hits, and local Whisper confirmation. Ordinary wake candidates use a 0.95 threshold. Physical echo and barge-in acceptance remain unverified until the Jabra arrives.

Say "Ted, stop listening" to pause. This also works as "hey Ted, stop listening." Pause closes microphone capture and persists across KeepAlive restarts. Voice cannot resume a paused microphone.

Pause or stop from Terminal:

```sh
touch ~/ted-ops/voice/paused
launchctl bootout gui/$(id -u)/co.ted.voice
```

Resume:

```sh
rm -f ~/ted-ops/voice/paused
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/co.ted.voice.plist
```

If the agent is still loaded, removing the pause file is enough. Check service state with:

```sh
launchctl print gui/$(id -u)/co.ted.voice
```

The service is `co.ted.voice`, runs only on the mini, and uses a signed local Ted Voice app for microphone identity. Logs live in `~/ted-ops/voice/logs`. Event logs rotate at 2 MB, retain four backups, and record wake scores and timings. They omit raw speech and transcript text. Captures and rendered replies are temporary. Offline requests are private files in `pending/`, capped at 100, and do not authorize new work or automatic sends.

## Live Ted integration

The adapter reads `~/ted-ops/ted-board/frontdoor/fresh/current.json` for every request, verifies the local session identity, and reuses the existing authenticated inbox transport from `fresh_ted.py`. It creates no model session. Each message has `[voice]` and a unique marker. Reply playback starts only after that exact marker is seen in a user transcript entry. Thinking, tool use, sidechains, unrelated user messages, transcript rotation, and session rollover cannot become spoken replies.

The initial live test reached the socket but timed out without a user transcript entry. The installed CLI holds unregistered peer messages when live Ted uses bypass permission mode. Ted must review this integration and resolve the inbox policy using the normal CLI approval flow. No inbox security setting was changed. A socket write is reported as submission, never as confirmed delivery. The initial test asks for a harmless exact reply and explicitly forbids tools and external actions.

## Installation and review

Source is in the isolated card worktree under `voice/`. Runtime is copied to `~/ted-ops/voice/app`, with its own Python 3.11 environment. The installer refuses to create a routine on a machine whose hardware name is not Mac mini. It compiles and signs the native audio helper, writes the two tones and launchd plist, and can load the agent with `--load`.

```sh
python3 install.py --python ~/ted-ops/voice/.venv/bin/python \
  --models ./models --load
```

Install the pinned runtime requirements first, then install `openwakeword==0.6.0` with `--no-deps`. That avoids its Linux-only TFLite dependency on macOS. Download the openWakeWord feature ONNX models into the environment with `openwakeword.utils.download_models`. Training additionally uses Torch, ONNX, torchaudio, SoundFile, and the upstream Piper generator.

Wake training uses the [openWakeWord feature pipeline](https://github.com/dscripka/openWakeWord) and the [Piper synthetic generator](https://github.com/dscripka/piper-sample-generator). Generated "hey Ted" and "Ted stop listening" clips are positives, confusable phrases are negatives, and LibriSpeech provides additional negative speech. The model and training metadata are versioned. The training set is smaller than upstream's recommended production dataset, so the measured holdouts are a provisional acceptance check.

The final virtual background test produced zero confirmed false wakes in 30 minutes of audio. Its 46 neural candidates were all rejected locally before a chime or interruption. The virtual background test uses held-out [LibriSpeech](https://www.openslr.org/12) speakers and [SoundHelix sample music](https://www.soundhelix.com/audio-examples). It exercises 30 minutes of audio through local inference. It does not establish room performance or a measured hourly household false-trigger rate. The [ElevenLabs subscription API](https://elevenlabs.io/docs/api-reference/user/subscription/get) documents the zero-overage field used by the paid voice guard.

Validation results, remaining review gates, and the PR are recorded in the card's `REPORT.md`. No production database SQL, Telegram message, or paid API request is part of this installation.
