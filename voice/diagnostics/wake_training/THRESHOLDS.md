These are historical candidate calibration results. The candidate failed installed room acceptance and was rolled back. The final service uses the original model at .99 with a playback energy guard; these curves do not evaluate that guard.

The evidence supports trying `.998` on the trained candidate. No source or runtime threshold was changed by this analysis.

| Playback threshold, two hits and VAD unchanged | .99 | .995 | .998 | .999 | .9995 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Candidate Hey Ted | 306/306 | 306/306 | 306/306 | 306/306 | 306/306 |
| Candidate stop listening | 54/54 | 54/54 | 54/54 | 54/54 | 50/54 |
| Candidate bare stop | 60/60 | 60/60 | 60/60 | 60/60 | 60/60 |
| Candidate separate macOS audio | 12/12 | 12/12 | 12/12 | 12/12 | 12/12 |
| Candidate 30-minute background gate candidates | 29 | 23 | 16 | 11 | 3 |
| Old-model background gate candidates | 32 | 27 | 20 | 16 | 10 |

The known physical bare-stop recording passes every threshold with both models. The latest early `.99429` acoustic event has no saved WAV, so this analysis makes no audio-specific claim about it.

`.998` cuts background gate candidates by about 45% while preserving every positive clip in this corpus. It sits inside the observed no-loss region and leaves more score margin than `.999`. `.9995` loses four existing stop-listening clips, so its lower background count does not justify it. This is a candidate setting for controlled acoustic testing, not an established universal optimum.

`threshold_curve.py` shares one inference per PCM frame across all five gates. The 1,800-second negative stream keeps continuous model and VAD state, with no reset at the speech, music, or mixed boundaries. Its `.99` counts exactly reproduce the original 32/29 comparison. The original `comparison.json` is unchanged. Full results are `threshold-curve.json`, and concise results are `threshold-summary.json`.

Library inspection found that openWakeWord initializes the feature buffer with random noise at reset. Early events in isolated microphone-window replays can therefore differ between runs, and do not represent continuous-daemon ambient behavior. All five thresholds within this run share that same state, and the actual known bare-stop trigger occurs later in its captured window. Positive clip and microphone-window tests reset the model; they do not replay prior daemon history.

The positive corpus comprises 420 epoch-selection validation clips and 12 separate macOS PCM clips. The macOS set has 18 requested conditions, with duplicate 120/140-rate audio counted once. Neural background candidates are not accepted Whisper requests or measured audible self-interruptions. Installed acoustic tests remain necessary with the two-hit, VAD, Whisper, and recent-source-audio echo guards intact.
