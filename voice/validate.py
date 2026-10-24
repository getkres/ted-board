#!/usr/bin/env python3
"""Score held-out wake clips or a fixed-duration virtual background input.
No transcript delivery or paid calls occur in this command.
"""

import argparse
import json
import tempfile
import time
from collections import deque
from pathlib import Path

import numpy as np
import scipy.signal
import soundfile as sf
import webrtcvad
from openwakeword.model import Model

from core import PlaybackGate, wake_command
from runtime import Whisper, write_pcm

p = argparse.ArgumentParser()
p.add_argument("--model", type=Path, required=True)
p.add_argument("--clips", type=Path)
p.add_argument("--background", type=Path)
p.add_argument("--music", type=Path)
p.add_argument("--seconds", type=int, default=1800)
p.add_argument("--output", type=Path, required=True)
p.add_argument("--verify", action="store_true")
a = p.parse_args()
m = Model(wakeword_models=[str(a.model)], inference_framework="onnx")


def read(path):
    x, sr = sf.read(path, dtype="float32")
    if x.ndim > 1:
        x = x.mean(axis=1)
    if sr != 16000:
        x = scipy.signal.resample_poly(x, 16000, sr)
    return x


def score(x):
    m.reset()
    gate = PlaybackGate(0.95, 0.99, 2)
    events = []
    candidates = []
    peak = 0
    vad = webrtcvad.Vad(2)
    recent = deque(maxlen=4)
    last = -100
    x = (np.clip(x, -1, 1) * 32767).astype(np.int16)
    for i in range(0, len(x) - 1279, 1280):
        s = float(next(iter(m.predict(x[i : i + 1280]).values())))
        peak = max(peak, s)
        pcm = x[i : i + 1280].tobytes()
        recent.append(any(vad.is_speech(pcm[j : j + 640], 16000) for j in range(0, 2560, 640)))
        if gate.accept(s if any(recent) else 0) and i / 16000 - last >= 2:
            row = dict(seconds=round(i / 16000, 3), score=round(s, 6))
            candidates.append(row)
            last = i / 16000
            accepted = True
            if a.verify:
                with tempfile.TemporaryDirectory(prefix="ted-verify-") as tmp:
                    path = Path(tmp) / "candidate.wav"
                    write_pcm(path, x[max(0, i - 37120) : i + 11520].tobytes())
                    t = time.monotonic()
                    text = Whisper(
                        "/opt/homebrew/bin/whisper-cli",
                        Path.home() / ".cache/whisper/ggml-small.en.bin",
                    ).transcribe(path)
                    accepted = wake_command(text) is not None
                    row["verification_seconds"] = round(time.monotonic() - t, 3)
                    row["accepted"] = accepted
            if accepted:
                events.append(row)
    return dict(
        peak=round(peak, 6),
        triggers=events,
        candidates=candidates,
        verification_enabled=a.verify,
        duration_seconds=len(x) / 16000,
    )


started = time.monotonic()
result = {}
if a.clips:
    result["clips"] = {f.name: score(read(f)) for f in sorted(a.clips.glob("*.wav"))}
if a.background:
    files = sorted(a.background.rglob("*.flac"))
    # These speakers were excluded from classifier training.
    speakers = sorted({f.parent.parent.name for f in files})
    heldout = set(speakers[int(len(speakers) * 0.7) :])
    files = [f for f in files if f.parent.parent.name in heldout]
    speech = []
    n = 0
    for f in files:
        x = read(f)
        speech.append(x)
        n += len(x)
        if n >= a.seconds * 16000:
            break
    x = np.concatenate(speech)
    if len(x) < a.seconds * 16000:
        x = np.tile(x, int(np.ceil(a.seconds * 16000 / len(x))))
    x = x[: a.seconds * 16000]
    if a.music:
        music = read(a.music)
        music = np.tile(music, int(np.ceil(len(x) / len(music))))[: len(x)]
        # First ten minutes speech, next ten minutes music, final ten minutes mixed.
        third = len(x) // 3
        x[third : 2 * third] = music[third : 2 * third] * 0.7
        x[2 * third :] = x[2 * third :] * 0.65 + music[2 * third :] * 0.3
    result["background"] = score(x)
    result["background"]["heldout_speakers"] = sorted(heldout)
    result["background"]["conditions"] = (
        "virtual file input, 10 minutes speech, 10 minutes music, and 10 minutes mixed"
    )
result["processing_seconds"] = round(time.monotonic() - started, 3)
a.output.write_text(json.dumps(result, indent=2))
print(json.dumps(result), flush=True)
