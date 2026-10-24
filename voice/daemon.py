#!/usr/bin/env python3
"""Always-on mini voice service. Native audio supplies echo-cancelled PCM."""

import argparse
import fcntl
import os
import signal
import time
from pathlib import Path

from core import Pause
from loop import VoiceLoop
from runtime import Audio, Whisper, logger
from session import SessionBridge


def main():
    os.umask(0o077)
    p = argparse.ArgumentParser()
    p.add_argument("--home", type=Path, default=Path.home() / "ted-ops/voice")
    a = p.parse_args()
    home = a.home
    home.mkdir(parents=True, exist_ok=True)
    emit = logger(home)
    with (home / "service.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0
        import numpy as np
        import webrtcvad
        from openwakeword.model import Model

        wake = Model(
            wakeword_models=[str(home / "models/hey_ted.onnx")], inference_framework="onnx"
        )
        vad = webrtcvad.Vad(2)
        whisper = Whisper(
            "/opt/homebrew/bin/whisper-cli",
            Path.home() / ".cache/whisper/ggml-medium.en.bin",
            Path.home() / ".cache/whisper/ggml-small.en.bin",
        )
        bridge = SessionBridge()
        audio = None
        loop = None
        stopping = False

        def stop(*_):
            nonlocal stopping
            stopping = True

        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        emit("service_started")
        try:
            while not stopping:
                if Pause(home).paused:
                    if audio:
                        audio.close()
                        audio = None
                        loop = None
                        emit("capture_closed_for_pause")
                    time.sleep(0.25)
                    continue
                if audio is None:
                    audio = Audio(home / "bin/TedVoiceAudio", emit)
                    wake.reset()
                    loop = VoiceLoop(
                        home,
                        audio,
                        whisper,
                        bridge,
                        emit,
                        verifier=Whisper(
                            "/opt/homebrew/bin/whisper-cli",
                            Path.home() / ".cache/whisper/ggml-small.en.bin",
                        ),
                    )
                try:
                    frames = audio.pump()
                    for pcm in frames:
                        sample = np.frombuffer(pcm, dtype=np.int16)
                        score = float(next(iter(wake.predict(sample).values())))
                        voiced = any(
                            vad.is_speech(pcm[i : i + 640], 16000) for i in range(0, len(pcm), 640)
                        )
                        loop.feed(pcm, score, voiced)
                    loop.tick()
                except RuntimeError:
                    audio.close()
                    audio = None
                    if loop and loop.future:
                        loop.future.cancel()
                    emit("audio_retry")
                    for _ in range(40):
                        if stopping:
                            break
                        time.sleep(0.25)
        finally:
            if audio:
                audio.close()
            emit("service_stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
