# Voice validation, 2026-10-23

Delivery state: blocked pending PR review and Ted's live wake and reply acceptance. The installed KeepAlive agent is running on the Mac mini with the connected Jabra and granted microphone access.

## Jabra startup repair, 2026-10-23

- Reproduced startup failure on the real hardware: NSError domain `com.apple.coreaudio.avfaudio`, code `-10875`. The original graph had an input client format of 16 kHz and three channels, an output client format of 44.1 kHz and two channels, and invalid zero-rate hardware formats after assigning separate devices to the shared voice-processing audio unit.
- Select Jabra as the system default input and output before creating the engine. Remove per-node `CurrentDevice` assignments, and connect the mixer to the output using the input node's output format. No sample-rate setting was forced on the USB hardware.
- Actual launchd `events.jsonl` now records `audio_ready`, `capture: true`, and `echo_cancelled: true`. Input ID 99 and output ID 94 both name Jabra Speak2 55 MS. Both graph sides are 16 kHz, float32, and three channels. Output hardware is 16 kHz stereo. The shared unit reports output device 94 on both nodes, while the system default input remains Jabra input 99.
- Default output changed from Mac mini Speakers, ID 88, to Jabra, ID 94. Default input remains Jabra, ID 99. The service remains running without a pause marker after the test.
- Exactly one listen-tone playback was commanded through the installed helper under the microphone-approved app supervisor. It reported `playback_started` and `playback_done` with the Jabra duplex route active. This verifies software playback completion, not a human listening assessment.
- Rebuilt and ad hoc signed the separate audio helper. Preserved the approved app launcher and Info.plist byte for byte, verified both signatures, and registered the app through LaunchServices. No microphone reapproval or system security change was needed.
- Native NSError and route fields now reach the rotating event log instead of being discarded by the Python adapter. Regression tests cover metadata forwarding and preservation of the approved launcher during updates.
- Current suite: 38 tests discovered, 37 passed, and one optional two-chime native test skipped to honor the one-chime limit. Ruff passes. The offline grants guard checks zero future migrations, and its 17 regression tests pass. No SQL was applied.
- No wake phrase, live Ted message, transcription benchmark, speech synthesis, or account API call was initiated in this hardware repair. The existing Brian approval was temporarily held during diagnostics and restored unchanged. Physical echo rejection, barge-in, live delivery, and reply playback remain for Ted.

## Previous virtual validation, 2026-10-22

- 36 behavioral and native output tests pass in the durable Python 3.11 environment.
- Six held-out wake clips pass: Daniel and Samantha at 140, 180, and 220 words per minute.
- Two held-out stop clips pass: Daniel and Samantha saying "Ted, stop listening."
- Final background input: 1,800 seconds, consisting of 10 minutes of held-out LibriSpeech, 10 minutes of unseen SoundHelix Song 2, and 10 minutes mixed. Zero confirmed false wakes. All 46 neural candidates were rejected by local Whisper before a chime or playback interruption.
- This was an accelerated virtual-input run, processed in 48.706 seconds. It was not 30 wall-clock minutes of room microphone audio, and it does not establish a household false-trigger rate.
- Initial unverified model testing exposed frequent music candidates. The final model adds music negatives, uses VAD gating and 0.95/0.99 thresholds, and requires local Whisper confirmation. Its 15,436 training examples include 2,400 synthetic positive clips, 1,500 confusable clips, negative speech, music, and mixed speech.
- Whisper cold benchmark on the same clip: small.en 0.564 seconds, and medium.en 1.846 seconds. Both transcribed the wake and question exactly. The final replay's medium.en pass took 0.740 seconds.
- Virtual end-to-end replay uses real wake inference, VAD, local Whisper, the state machine, tones, and Mac mini speaker playback. Ted's reply is explicitly stubbed. Neural candidate to confirmed wake: 1.442 seconds. Candidate to speech dispatch: 6.771 seconds. Speaker playback completed 14.472 seconds after test startup, including speech duration. These are local pipeline measurements, not live Ted latency.
- Native playback stop control was measured at 0.0027 seconds to completion. Physical barge-in detection and Jabra echo rejection remain untested.
- The live inbox socket accepted a write in 0.160 seconds, but no correlated user entry or reply appeared within 180 seconds. The installed CLI holds unregistered peers without a permission-mode assertion when Ted uses bypass mode. The adapter now reports submission separately from transcript-confirmed delivery and refuses a session already waiting at a permission prompt. No inbox security setting was changed.
- On 10-22, CoreAudio reported two outputs and no input devices, and microphone consent was not determined. This is superseded by the 10-23 Jabra results above.
- ElevenLabs calls were not made. Brian was subsequently approved for seven days using existing credits and $0 in new charges. Its installed ISO expiry marker is now recognized, alongside legacy Unix timestamps. The daily cap and no-overage subscription guard remain required. All audio testing used local speech; the follow-up made no API call.

Model SHA-256: `68f66ae5eec9e304eb00d41c726e6778289cbb2fb2f9c0369b9e471ef17760f1`.

Private evidence is retained in the card job's artifacts directory. No private transcript, session identifier, recorded user voice, or secret is included in this PR.

Review acceptance: resolve the voice sender's inbox admission through the supported CLI approval flow, run live wake and correlated reply playback, honor the existing credit approval, and assess room echo rejection and physical barge-in.

Follow-up handoff: the card is Up next. Ted owns inbox admission and live wake and reply testing. Sebastian has already granted microphone access, and no further physical setup is requested.
