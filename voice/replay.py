#!/usr/bin/env python3
"""Run the real wake, VAD, Whisper, state machine, and output with virtual input.

Ted is stubbed by default. --live uses only the existing session and preserves its
permission gate. Never substitutes a fresh model session or makes a paid call.
"""

import argparse
import json
import tempfile
import time
from pathlib import Path

import soundfile as sf
import webrtcvad
from openwakeword.model import Model

from loop import VoiceLoop
from runtime import Audio, Whisper
from session import SessionBridge

p = argparse.ArgumentParser()
p.add_argument("--home", type=Path, required=True)
p.add_argument("--input", type=Path, required=True)
p.add_argument("--output", type=Path, required=True)
p.add_argument("--live", action="store_true")
a = p.parse_args()


class StubTed:
    def deliver(self, text):
        return dict(text=text, accepted=False, session_id="virtual")

    def poll(self, request):
        request["accepted"] = True
        return "The local voice test is complete. Live Ted still needs an inbox permission review."

    def assert_current(self, sid):
        pass


rows = []
started = time.monotonic()


def emit(event, **fields):
    row = dict(event=event, wall_seconds=round(time.monotonic() - started, 3), **fields)
    rows.append(row)


model = Model(wakeword_models=[str(a.home / "models/hey_ted.onnx")], inference_framework="onnx")
vad = webrtcvad.Vad(2)
x, sr = sf.read(a.input, dtype="int16")
assert sr == 16000
with tempfile.TemporaryDirectory(prefix="ted-replay-") as tmp:
    home = Path(tmp)
    (home / "tmp").mkdir()
    (home / "tones").symlink_to(a.home / "tones")
    audio = Audio(a.home / "Ted Voice.app/Contents/MacOS/TedVoice", emit, output_only=True)
    loop = VoiceLoop(
        home,
        audio,
        Whisper("/opt/homebrew/bin/whisper-cli", Path.home() / ".cache/whisper/ggml-medium.en.bin"),
        SessionBridge() if a.live else StubTed(),
        emit,
        verifier=Whisper(
            "/opt/homebrew/bin/whisper-cli", Path.home() / ".cache/whisper/ggml-small.en.bin"
        ),
    )
    try:
        for i in range(0, len(x) - 1279, 1280):
            frame = x[i : i + 1280]
            pcm = frame.tobytes()
            score = float(next(iter(model.predict(frame).values())))
            voiced = any(vad.is_speech(pcm[j : j + 640], 16000) for j in range(0, 2560, 640))
            loop.feed(pcm, score, voiced)
            audio.pump()
            loop.tick()
            target = started + (i + 1280) / 16000
            if target > time.monotonic():
                time.sleep(target - time.monotonic())
        deadline = time.monotonic() + 190
        while time.monotonic() < deadline:
            audio.pump()
            loop.tick()
            if any(r["event"] == "speech_started" for r in rows) and loop.state == "idle":
                break
            if loop.state == "paused":
                break
            time.sleep(0.02)
    finally:
        audio.close()
        loop.executor.shutdown(wait=True, cancel_futures=True)
        loop.verify_executor.shutdown(wait=True, cancel_futures=True)
result = dict(
    mode="live" if a.live else "virtual input, stubbed Ted, actual local models and speaker output",
    events=rows,
    total_seconds=round(time.monotonic() - started, 3),
)
a.output.write_text(json.dumps(result, indent=2))
print(json.dumps(result), flush=True)
