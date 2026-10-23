# Voice validation, 2026-10-22

Delivery state: blocked pending Ted review. Source and a KeepAlive agent are staged on the Mac mini. This is not a completed live voice acceptance test.

- 33 behavioral and native output tests pass in the durable Python 3.11 environment.
- Six held-out wake clips pass: Daniel and Samantha at 140, 180, and 220 words per minute.
- Two held-out stop clips pass: Daniel and Samantha saying "Ted, stop listening."
- Final background input: 1,800 seconds, consisting of 10 minutes of held-out LibriSpeech, 10 minutes of unseen SoundHelix Song 2, and 10 minutes mixed. Zero confirmed false wakes. All 46 neural candidates were rejected by local Whisper before a chime or playback interruption.
- This was an accelerated virtual-input run, processed in 48.706 seconds. It was not 30 wall-clock minutes of room microphone audio, and it does not establish a household false-trigger rate.
- Initial unverified model testing exposed frequent music candidates. The final model adds music negatives, uses VAD gating and 0.95/0.99 thresholds, and requires local Whisper confirmation. Its 15,436 training examples include 2,400 synthetic positive clips, 1,500 confusable clips, negative speech, music, and mixed speech.
- Whisper cold benchmark on the same clip: small.en 0.564 seconds, and medium.en 1.846 seconds. Both transcribed the wake and question exactly. The final replay's medium.en pass took 0.740 seconds.
- Virtual end-to-end replay uses real wake inference, VAD, local Whisper, the state machine, tones, and Mac mini speaker playback. Ted's reply is explicitly stubbed. Neural candidate to confirmed wake: 1.442 seconds. Candidate to speech dispatch: 6.771 seconds. Speaker playback completed 14.472 seconds after test startup, including speech duration. These are local pipeline measurements, not live Ted latency.
- Native playback stop control was measured at 0.0027 seconds to completion. Physical barge-in detection and Jabra echo rejection remain untested.
- The live inbox socket accepted a write in 0.160 seconds, but no correlated user entry or reply appeared within 180 seconds. The installed CLI holds unregistered peers without a permission-mode assertion when Ted uses bypass mode. The adapter now reports submission separately from transcript-confirmed delivery and refuses a session already waiting at a permission prompt. No inbox security setting was changed.
- CoreAudio reports two outputs, Mac mini Speakers and an HDMI display, and no input devices. Microphone consent is not determined.
- ElevenLabs calls were not made. The Brian path requires an approved, expiring marker, a daily cap, and a read-only subscription check proving usage-based billing is disabled. All testing used local speech.

Model SHA-256: `68f66ae5eec9e304eb00d41c726e6778289cbb2fb2f9c0369b9e471ef17760f1`.

Private evidence is retained in the card job's artifacts directory. No private transcript, session identifier, recorded user voice, or secret is included in this PR.

Review acceptance: resolve the voice sender's inbox admission through the supported CLI approval flow, rerun live delivery and correlated playback, review the credit-use draft, and test the USB Jabra and microphone consent when it arrives.
