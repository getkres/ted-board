# Hey Ted voice repair, October 27, 2026

**The full brief is not complete, and overall acceptance remains false.** The voice fixes are installed on the Mac mini. Main Ted holds authenticated voice messages before they reach the model. Its receiver-policy exception is prepared but unapplied because the brief prohibits Claude setting changes. Acoustic acceptance also remains incomplete after rejected interruptions and a Jabra disconnect.

## Current result

| Requirement | Evidence-backed status | Evidence |
| --- | --- | --- |
| Reach pinned main Ted through its existing inbox | Blocked by the receiver's permission policy. Socket success did not establish model receipt. | [Observed hold](/Users/vahallo/ted-ops/voice/FULL-1027/main-inbox-held.json), [diagnosis](/Users/vahallo/ted-ops/voice/FULL-1027/main-route-diagnosis.json) |
| Answer through account 2 after approximately 20 seconds | Passed: the installed loop received and spoke a real account 2 reply after the main wait. | [Current hardware evidence](/Users/vahallo/ted-ops/voice/FULL-1027/final-hardware.json) |
| Restrict fallback to read-only context and include Ted's voice card | Verified live with harmless sentinels and an outside-path denial. | [Scope probe](/Users/vahallo/ted-ops/voice/FULL-1027/read-only-scope.json) |
| Preserve action requests without duplicate delivery | Unit coverage verifies the durable queue, exact transcript acknowledgment, uncertain sends, and restart behavior. | [Test log](/Users/vahallo/ted-ops/voice/FULL-1027/unit-tests.log), source routing tests |
| Interrupt with “Hey Ted, stop” | Failed: 0.502 ms detection-to-native-pause; real follow-up handled: False. | [Current hardware evidence](/Users/vahallo/ted-ops/voice/FULL-1027/final-hardware.json) |
| Interrupt with bare “Ted, stop” | Passed: 0.49 ms detection-to-native-pause; real follow-up handled: True. | [Current bare-stop evidence](/Users/vahallo/ted-ops/voice/FULL-1027/final-bare-stop.json) |
| Ten long replies without self-triggering | Failed: 3/10 trials completed, one failed trial, and two unwanted pauses recorded as four stop events. | [Reconstructed partial results](/Users/vahallo/ted-ops/voice/FULL-1027/reconstructed-self-trigger.json) |

`main-route.json` records `main_route_verified: false` and `account2_fallback_verified: true`. Its filename does not establish main delivery. Historical hardware passes do not certify the latest confirmation and energy-guard code, even though the original model has been restored.

## Routing, context, and action handoff

Voice requests carry a unique `[voice]` marker and reuse the existing `fresh_ted.py` inbox transport. The adapter checks the selected session, process start identity, and socket. It never starts a competing CLI process or resumes the desktop session independently. Registry discovery uses the main Claude registry, while fallback uses account 2.

The transcript reader waits for the matching request and final assistant text. It excludes tool output, intermediate commentary, and hook context. Speech cleanup removes code and URLs, caps answers at 60 words, and adds “Rest is on screen” when trimming. Main session identity is checked again before playback to prevent stale speech after rollover.

Inbox operations and transcript reconciliation run off the audio pump. After approximately 20 seconds without a main answer, informational requests use account 2. Its Ted voice card comes from the configured UserPromptSubmit hook without executing the hook. Only Read, Grep, and Glob are available, restricted to resolved paths within `~/ted-ops/ted-state`, `~/biz`, `~/kres`, and `~/ventures`.

Fallback cannot execute actions. Action requests receive a local status message and remain in a private durable queue. Definitely unsent requests retry when the inbox returns. A socket write does not mark delivery: unacknowledged sends become uncertain, stay saved for review, and are never automatically resent. A later exact user marker confirms receipt without another send. Reconciliation checks file metadata before rescanning transcripts.

The live scope probe exposed exactly the three read tools. It read an allowed generated sentinel and received an explicit restricted-mode denial for an outside sentinel. The voice card, Max OAuth, and disabled extra usage were verified. Temporary sentinels and test state were removed.

## Wake detection and confirmation

The Jabra Speak2 55 supplies hardware echo cancellation while both USB audio routes remain bound to it. Capture and wake detection continue during playback. The installed baseline requires **two consecutive playback scores at or above 0.99**, plus the existing voice-activity gate, local Whisper confirmation, and source-audio echo check. The idle threshold remains 0.95.

Playback admission also requires the maximum RMS among the last four 80 ms microphone frames to be at least **-45 dBFS**. The floor applies consistently to initial candidates, late candidates during provisional pause, and supplemental stop scans. Idle wake admission is unchanged. Using a recent maximum retains a short quiet gap after speech instead of requiring every frame to exceed the floor.

This guard was calibrated against two retained true-stop captures, whose exact trigger-window maxima were -24.60 and -29.11 dBFS, and one false candidate at -58.45 dBFS. Those three examples support this limited noise-floor distinction, not a general household false-trigger rate. The final installed acoustic results are reported below; these few calibration clips do not establish a general sensitivity guarantee.

A strong candidate pauses playback provisionally. Eight additional audio frames complete the confirmation capture. Rejected candidates resume the same playback. Echo comparison uses a physically cropped portion of the rendered audio ending at the matching native pause position, correlated by playback and stop identifiers. A quoted wake phrase later in the reply therefore cannot veto a real interruption now.

Only four exact, observed two-word ambiguities can receive a vocabulary retry: “third storm,” “Ted storm,” “Ted stone,” and “fed stop.” They are not accepted command aliases. Empty, non-speech, unrelated, and longer transcripts cannot use the retry. Both initial and retried recognition remain subject to the echo check. Request and source-audio transcription remain unprompted.

If that retry confirms a stop, the same ambiguity may be removed once from that captured request's prefix. The correction is tied to the current generation and cannot become a general phrase substitution. This keeps a confirmed stop from being forwarded as an action when the longer request capture repeats the recognition error.

## Baseline selection and candidate research

The final selected model in source and runtime is the original `68f66ae5eec9e304eb00d41c726e6778289cbb2fb2f9c0369b9e471ef17760f1`, with its original training metadata and 2,400 positive clips. Its positives comprised 2,000 “Hey Ted” clips and 400 “Ted stop listening” clips. Bare stop still depends on generalization, so restoring this model does not establish that bare-stop reliability is solved.

The experimental `fd3131cccfe721523e76248df6fedbf50e62abd0d58c084d32c242c0c0acbc8d` model is retained as research evidence, not promoted as an accepted final model. It added 400 explicit bare-stop Piper clips, split by whole clip into 340 training clips and 60 validation clips. All 400 hashes are unique, with no split overlap. The split is not speaker-disjoint. Existing cached examples were preserved exactly, and music and mixed negatives were regenerated. This candidate had 2,800 raw positive clips and 16,116 training examples after augmentation and music additions.

The comparison contains **432 unique synthetic positive clips**: 306 original Hey Ted validation clips, 54 stop-listening validation clips, 60 new bare-stop validation clips, and 12 separate macOS clips. The macOS run requested 18 voice, rate, and phrase conditions, but the 120 and 140 requests produced identical audio for both voices. The 180 requests differed. Duplicate PCM was counted once, giving four unique macOS clips per phrase.

| Research comparison, two hits and VAD unchanged, before energy guard | Baseline at .99 | Candidate at .99 | Candidate at .995 |
| --- | ---: | ---: | ---: |
| Hey Ted validation | 306/306 | 306/306 | 306/306 |
| Stop-listening validation | 54/54 | 54/54 | 54/54 |
| Bare-stop validation | 54/60 | 60/60 | 60/60 |
| Separate macOS audio | 12/12 | 12/12 | 12/12 |
| Candidates in 30-minute negative replay | 32 | 29 | 23 |

**These background events are neural gate candidates, not confirmed false wakes or measured audible self-interruptions.** In particular, 23 describes the experimental candidate at .995, not the current baseline plus energy guard. Whisper, playback, and the new energy floor were not simulated. The negative stream kept continuous model and VAD state across 10 minutes of speech, 10 minutes of music, and 10 minutes of mixed audio. All five thresholds received the same inference results, and the original .99 counts reproduced exactly.

The candidate improved offline bare-stop recall, but it did not meet installed hardware acceptance. Its latest bare-stop trial missed the required score pair, and the subsequent partial full run recorded an end-to-end failure and was interrupted after an observed Hey Ted confirmation failure. It did not produce a completed interruption check or reach the ten-reply series. The original model and .99 playback threshold were therefore restored. This is a return to the previously tested model, not proof that it is universally more accurate than the candidate. The final confirmation and energy code were tested separately in the recorded current-build trials below.

The 60 new validation clips select the training epoch, so they are not an untouched final test set. The separate macOS clips are synthetic and do not establish Sebastian's natural voice accuracy. Individual microphone-window replays reset openWakeWord, whose initial feature buffer contains random noise. Early replay triggers can vary and do not represent continuous daemon history. This caveat does not alter the continuous negative-stream comparison.

Reproduction and provenance are in [the model summary](/Users/vahallo/ted-ops/voice/FULL-1027/wake-candidate/SUMMARY.json), [PCM audit](/Users/vahallo/ted-ops/voice/FULL-1027/wake-candidate/heldout-macos-audit.json), [threshold curve](/Users/vahallo/ted-ops/voice/FULL-1027/wake-candidate/threshold-summary.json), and [training instructions](/Users/vahallo/ted-ops/voice/FULL-1027/wake-candidate/README.md). Candidate recommendations and its 2,800-positive metadata are historical research artifacts. They do not describe the restored source or runtime. Failed installed evidence remains in [bare-stop-verified.json](/Users/vahallo/ted-ops/voice/FULL-1027/bare-stop-verified.json) and [the partial full run](/Users/vahallo/ted-ops/voice/FULL-1027/hardware-final.json).

## Main inbox blocker and unapplied proposal

The observed held receiver was session `212864a8-1156-4929-8107-379dcd7e380c`, selected through the normal Fresh Ted lifecycle. Its transcript recorded the hold at `2026-10-27T19:22:53.937Z`: the sender had not attested its permission mode, while the receiver bypassed prompts. The message was not delivered to Claude. The marker and evidence are in [main-inbox-held.json](/Users/vahallo/ted-ops/voice/FULL-1027/main-inbox-held.json).

Receiver-code inspection confirms this policy. An honest `prompting` sender is also held because its permission class differs from the receiver's. The adapter does not claim bypass authority to defeat the check. Desktop-session identity and transcript checks ruled out account 2 transcript relocation as the cause.

The concrete proposal is [main-inbox-policy-proposal.patch](/Users/vahallo/ted-ops/voice/FULL-1027/main-inbox-policy-proposal.patch), with [scope and validation details](/Users/vahallo/ted-ops/voice/FULL-1027/main-inbox-policy-proposal.json). It adds `--settings '{"crossSessionInbound":"accept"}'` only to normal main Ted launches through the existing `fresh_ted.Driver.start` path. Isolated test launches receive no override. Patch applicability and four main/test, start/resume combinations were checked without applying it.

This process-scoped setting accepts **all authenticated local peer messages into that main process**, not only voice. Claude exposes no voice-sender allowlist for it. Activation would occur through the next normal Fresh Ted lifecycle after approval. Removing the flag rolls back future launches; an existing process keeps its launch policy until its lifecycle ends.

**The proposal remains unapplied.** [BRIEF.md](/Users/vahallo/ted-ops/voice/FULL-1027/BRIEF.md) says, “Do not change Claude, Stripe, ElevenLabs, or any billing settings.” This exception requires explicit approval. Main delivery must then be retested for an accepted user marker, its matching final answer, and spoken playback. Overall acceptance also requires a passing Hey Ted interruption and ten long replies with zero self-triggers.

## Hardware measurements and their limits

The final build uses the original wake model, the .99 two-hit playback gate, and the -45 dBFS energy floor. The Mac mini speaker supplied the external phrases while the Jabra played a 108-word, approximately 35.6-second local reply. Both devices' routes were verified.

| Current interruption trial | Result | Detection to native pause | Stimulus dispatch to native pause | Real follow-up |
| --- | --- | ---: | ---: | --- |
| Hey Ted, stop | Fail | 0.502 ms | 1348.425 ms | Not verified |
| Ted, stop | Pass | 0.49 ms | 1588.278 ms | account2 |

A follow-up pass requires an actual main or account 2 reply between submission and rendering. Queued-action notices and uncertain-delivery notices cannot satisfy it. Native timing uses monotonic clocks and the player.pause acknowledgment. It is not an independently measured physical sound-to-silence result. The stimulus timestamp is process dispatch, not measured acoustic onset. These tests do not establish accuracy at every room position.

The latest long-reply run completed 3 of the required ten trials before the Jabra disappeared from the system. It reconnected about 27 seconds later. The source of the loud rejected candidates was not established, and a quiet-room condition was not confirmed. [Reconstructed partial results](/Users/vahallo/ted-ops/voice/FULL-1027/reconstructed-self-trigger.json) preserve the three completed trials from raw events, and [disconnect evidence](/Users/vahallo/ted-ops/voice/FULL-1027/hardware-disconnect.json) records removal and subsequent recovery. Its result was **fail**, with one failed trial and two unwanted pauses, recorded as four stop events. The fixture includes quoted wake phrases. Provisional pauses count as self-trigger events even when Whisper rejects them and playback resumes.

Earlier failures remain recorded. The preceding -50 dBFS build completed ten trials, with one unwanted pause that generated two stop events. Its qualifying frames were -49.84 dBFS. The -45 dBFS selection rejects that observed pair and preserves the weakest qualifying frame in the prior live true interruptions, -36.35 dBFS. That is an observed 8.65 dB margin, not a guarantee for softer or more distant speech. See [energy calibration](/Users/vahallo/ted-ops/voice/FULL-1027/energy-calibration.json), [prior full run](/Users/vahallo/ted-ops/voice/FULL-1027/baseline-final.json), and [its build manifest](/Users/vahallo/ted-ops/voice/FULL-1027/baseline50-build.json). Historical passes were not substituted for current results.

## What to say when testing

1. **Speech and fallback:** “Hey Ted, reply exactly, the Jabra voice loop is working.” Expect Jabra playback. While main admission is blocked, allow approximately 20 seconds for fallback.
2. **Read-only context:** “Hey Ted, what are we working on today?” Fallback can consult the four roots. This does not establish main Ted delivery.
3. **Main Ted, after approval and verification:** “Hey Ted, what did we just discuss in the main conversation?” Confirm the marked request and final answer in the pinned transcript, then listen for the reply.
4. **Action handoff:** “Hey Ted, create a local test note in ted-state saying voice routing works.” A definitely unsent request should be queued. A sent but held request should say receipt is unconfirmed and saved for review. It must not claim completion or resend automatically.
5. **Interruption:** During a long reply, say “Hey Ted, stop,” wait for the listening tone, and say “Reply exactly, the follow-up was handled.” Repeat with “Ted, stop.” The final hardware evidence below determines each phrase's current status.
6. **Durable pause:** “Hey Ted, stop listening.” This closes listening persistently. Resume through the existing local resume control before another test.

## Billing and handoff

Account 2 still requires Max OAuth, the first-party provider, and disabled extra usage. API credentials and provider overrides are stripped from its environment. It never switches to API billing. Whisper, Piper generation, embedding, training, and threshold comparison ran locally.

ElevenLabs remains limited to the existing approval, expiring October 29 at 8:11 p.m. Pacific, with the existing daily cap and disabled-overage guard. This work has not changed Claude, Stripe, ElevenLabs, or billing settings, and it has not added a routine.

Source is `~/ted-ops/ted-board/jobs/card-c-hey-ted-voice-1022/worktree/voice`, on `feat/hey-ted-voice-1022`. Runtime is `~/ted-ops/voice/app`, and the service is `co.ted.voice` on the Mac mini. October 26 capture and routing repairs were preserved. The final unit result is 140 tests, with 137 passing and 3 native tests skipped. Final verification belongs below.

## Verification and handoff

- **Current hardware:** [full run](/Users/vahallo/ted-ops/voice/FULL-1027/final-hardware.json) and [bare stop](/Users/vahallo/ted-ops/voice/FULL-1027/final-bare-stop.json). The earlier trials remain linked above, including failures.
- **Source checks:** 140 tests: 137 passed and 3 optional native tests skipped. Ruff and `git diff --check` passed. See [unit log](/Users/vahallo/ted-ops/voice/FULL-1027/unit-tests.log) and [Ruff log](/Users/vahallo/ted-ops/voice/FULL-1027/ruff.log).
- **Install and health:** Installed with `install.py`; service health is verified, with fresh Jabra capture and playback readiness. See [install log](/Users/vahallo/ted-ops/voice/FULL-1027/install-final.log) and [health snapshot](/Users/vahallo/ted-ops/voice/FULL-1027/service-health.json).
- **Parity and billing:** [Source/runtime parity](/Users/vahallo/ted-ops/voice/FULL-1027/parity.json) includes the model and native build hashes. The ElevenLabs approval hash is unchanged. No Claude, Stripe, ElevenLabs, or billing settings were changed.
- **Cleanup:** The action queue contains 0 entries. Task-created private microphone recordings were removed, and diagnostic markers are absent at handoff. Compact hashes and measurements remain. See [cleanup record](/Users/vahallo/ted-ops/voice/FULL-1027/private-diagnostic-cleanup.json).
- **Acceptance:** [acceptance.json](/Users/vahallo/ted-ops/voice/FULL-1027/acceptance.json) records **overall false**: main Ted receipt and its spoken final answer remain blocked, the latest Hey Ted interruption did not confirm or handle its follow-up, and the ten-reply test stopped after three trials with unwanted pauses.
- **Source commit:** The local job-branch commit is recorded in [commit.json](/Users/vahallo/ted-ops/voice/FULL-1027/commit.json). No shared-remote push was performed.

Two items remain: the specific main-inbox policy exception described above, and a stable, quiet-room repeat of Hey Ted interruption and ten long replies. The separate Samantha-voice option was added but has not been run. After approval, the policy change must be applied through the normal Fresh Ted lifecycle and verified with a matching main transcript marker, final reply, and spoken playback.
