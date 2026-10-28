This experimental candidate improved offline bare-stop detection, but it failed installed room trials and was rolled back. The final service uses the original model with the confirmation and playback-energy fixes. Research artifacts remain in `~/ted-ops/voice/FULL-1027/wake-candidate`; final selection and hardware evidence are in `~/ted-ops/voice/FULL-1027/REPORT.md`.

| Streaming validation, .99 and two consecutive hits with VAD | Old | Candidate |
| --- | ---: | ---: |
| Hey Ted, original validation clips | 306/306 | 306/306 |
| Ted stop listening, original validation clips | 54/54 | 54/54 |
| Bare Ted stop, new validation clips | 54/60 | 60/60 |
| Separate macOS audio clips, 18 requested conditions | 12/12 unique | 12/12 unique |
| Gate candidates on continuous 30-minute background stream | 32 | 29 |
| Static original validation negatives above .99 | 0/509 | 0/509 |

The known physical bare-stop candidate triggers at 2.32 seconds with both models. The suspected ambient diagnostic ending `16cddc45d6f1437389a4297ca064f0cb.wav` produces no two-hit/VAD trigger with either model. Other physical windows are unlabelled and are reported descriptively in `comparison.json`.

The 400 new Piper clips contain four punctuation forms, four length scales, two noise scales, and varied synthetic speaker pairs. They split into 340 training clips and 60 whole-clip validation clips, with 400 unique waveform hashes and no split overlap. Original cached arrays are preserved exactly as prefixes. The original trainer regenerates its 3,000 music and mixed examples. Total training examples are 16,116. The trainer's original `positive_clips: 2400` field describes its source corpus, while `embedding.json` records the 400 appended bare-stop clips.

The candidate is `models/hey_ted_candidate.onnx`. The preserved original is `baseline-old.onnx`. Corrected promotion metadata is `models/training.json`, with 2,800 raw positive clips, including the explicit 340/60 bare-stop split, provenance, and .99 streaming metrics. Its existing selected loss and threshold metrics are preserved. `SUMMARY.json` provides hashes and concise metrics. `comparison.json` contains individual trials and continuous background triggers. `generation.json`, `embedding.json`, and `training-run.json` record the local commands, source hashes, split, and timings. Both reproducibility scripts pass Ruff and Python compilation.

The macOS generator passed all requested rates to `say`, but both Daniel and Samantha produced identical PCM for the 120 and 140 requests, while 180 produced distinct PCM. Thus, 18 requested voice, rate, and phrase conditions contain 12 unique audio clips, with four unique clips per phrase. `heldout-macos-audit.json` records the commands, durations, PCM hashes, and duplicate groups. The evidence does not assume why those rates collapsed.

To reproduce in a new, isolated output directory, use the existing job virtual environment and set `TED_WAKE_CANDIDATE_HOME` to that directory. Copy the preserved original to its `baseline-old.onnx` first. `TED_WAKE_JOB_HOME` can override the original job directory. Then run these stages in order:

```sh
python pipeline.py generate
python pipeline.py embed
python pipeline.py train
python compare.py
```

Run them using `runtime/venv/bin/python` from the original job, which has the local Piper, PyTorch, openWakeWord, and ONNX dependencies. The pipeline invokes the existing trainer with `--reuse` after explicitly appending new features. Passing `--reuse` alone would ignore the new WAVs. Comparison uses one continuous model and VAD state across all 1,800 background seconds, including condition boundaries. Each positive and diagnostic clip starts with a fresh model state, so those trials do not reproduce full daemon history.

These are offline candidate-detection results. They do not measure Whisper acceptance, audible pauses, or stop latency. The 60 new validation clips select the epoch, so they are not an untouched final test set. The 12 unique macOS clips are separate from training, but are synthetic, and do not establish natural user accuracy. Installed acoustic bare-stop and ten-reply self-trigger trials remain necessary before acceptance. Generated WAVs, private microphone recordings, and data arrays should stay outside the job branch.
