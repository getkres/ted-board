"""Bounded local audio, transcription, playback, and private offline storage."""

import json
import logging
import math
import os
import subprocess
import time
import uuid
import wave
from logging.handlers import RotatingFileHandler
from pathlib import Path

from core import speech_text

VOICE_ID = "G0yjIg3xY8gEJZkHpjVm"


class CaptureDiagnostics:
    """Five-second aggregate health only, with no audio or text retention."""

    def __init__(self, emit, now=None):
        self.emit = emit
        self.started = time.monotonic() if now is None else now
        self.samples = self.power = self.peak = self.voiced = self.vad_frames = 0
        self.max_score = 0.0

    def feed(self, pcm, score, vad):
        samples = memoryview(pcm).cast("h")
        self.samples += len(samples)
        self.power += sum(s * s for s in samples)
        self.peak = max(self.peak, max((abs(s) for s in samples), default=0))
        self.voiced += sum(vad)
        self.vad_frames += len(vad)
        self.max_score = max(self.max_score, score)

    def tick(self, now=None):
        now = time.monotonic() if now is None else now
        if now - self.started < 5:
            return
        rms = math.sqrt(self.power / self.samples) / 32768 if self.samples else 0
        self.emit(
            "audio_debug",
            window_seconds=round(now - self.started, 3),
            samples=self.samples,
            audio_seconds=round(self.samples / 16000, 3),
            rms=round(rms, 7),
            rms_dbfs=round(20 * math.log10(max(rms, 1e-6)), 3),
            peak=round(self.peak / 32768, 7),
            vad_voiced_ratio=round(self.voiced / self.vad_frames, 5) if self.vad_frames else 0,
            max_wake_score=round(self.max_score, 6),
        )
        self.started = now
        self.samples = self.power = self.peak = self.voiced = self.vad_frames = 0
        self.max_score = 0.0


def logger(home):
    log = logging.getLogger("ted.voice")
    log.setLevel(logging.INFO)
    home = Path(home)
    (home / "logs").mkdir(parents=True, exist_ok=True)
    if not log.handlers:
        h = RotatingFileHandler(home / "logs/events.jsonl", maxBytes=2_000_000, backupCount=4)
        h.setFormatter(logging.Formatter("%(message)s"))
        log.addHandler(h)

    def emit(event, **fields):
        log.info(json.dumps(dict(at=time.time(), event=event, **fields)))

    return emit


class Whisper:
    def __init__(self, binary, model, fallback=None):
        self.binary = Path(binary)
        self.model = Path(model)
        self.fallback = fallback

    def transcribe(self, path):
        if not self.binary.exists():
            raise RuntimeError("whisper unavailable")
        model = self.model if self.model.exists() else self.fallback
        if not model or not Path(model).exists():
            raise RuntimeError("whisper model unavailable")
        try:
            r = subprocess.run(
                [
                    str(self.binary),
                    "-m",
                    str(model),
                    "-f",
                    str(path),
                    "-nt",
                    "-np",
                    "-t",
                    "6",
                    "--no-prints",
                ],
                capture_output=True,
                text=True,
                timeout=45,
            )
        except (OSError, subprocess.TimeoutExpired):
            raise RuntimeError("whisper failed") from None
        if r.returncode:
            raise RuntimeError("whisper failed")
        text = r.stdout.strip()
        return text if text and not text.startswith("[") else ""


class PendingQueue:
    def __init__(self, home):
        self.path = Path(home) / "pending"
        self.path.mkdir(parents=True, exist_ok=True, mode=0o700)

    def add(self, text, reason="ted offline"):
        rid = uuid.uuid4().hex
        path = self.path / (rid + ".json")
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(
                dict(
                    id=rid,
                    at=time.time(),
                    text=text,
                    reason=reason,
                    delivery="not confirmed; never automatically resend",
                ),
                f,
            )
        for p in sorted(self.path.glob("*.json"), key=lambda p: p.stat().st_mtime)[:-100]:
            p.unlink()
        return rid


def render_local(text, path):
    try:
        r = subprocess.run(
            ["/usr/bin/say", "-v", "Daniel", "-o", str(path), speech_text(text)],
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError("local speech failed") from None
    if r.returncode:
        raise RuntimeError("local speech failed")
    return Path(path)


def subscription_safe(data, characters):
    # Current ElevenLabs API: zero disables usage-based billing. Unknown means hold.
    return (
        data.get("status") == "active"
        and type(data.get("max_credit_limit_extension")) is int
        and data["max_credit_limit_extension"] == 0
        and type(data.get("character_limit")) is int
        and type(data.get("character_count")) is int
        and data["character_limit"] - data["character_count"] >= characters * 3
    )


def credits_available(characters):
    try:
        import shlex
        import urllib.request

        key = None
        for line in (Path.home() / "ted-ops/keys.env").read_text().splitlines():
            bits = shlex.split(line, comments=True)
            if bits and bits[0] == "export":
                bits = bits[1:]
            if len(bits) == 1 and bits[0].startswith("ELEVENLABS_API_KEY="):
                key = bits[0].split("=", 1)[1]
        if not key or "$" in key:
            return False
        req = urllib.request.Request(
            "https://api.elevenlabs.io/v1/user/subscription", headers={"xi-api-key": key}
        )
        with urllib.request.urlopen(req, timeout=8) as response:
            data = json.load(response)
        return subscription_safe(data, characters)
    except Exception:
        return False


def reserve_usage(home, characters, cap):
    import fcntl

    if type(cap) is not int or cap < characters * 3:
        return False
    counter = home / "elevenlabs-usage.json"
    with (home / "elevenlabs-usage.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            usage = json.loads(counter.read_text()) if counter.exists() else {}
        except (OSError, ValueError):
            return False
        if not isinstance(usage, dict):
            return False
        today = time.strftime("%Y-%m-%d")
        used = usage.get("characters", 0) if usage.get("day") == today else 0
        if type(used) is not int or used < 0 or used + characters * 3 > cap:
            return False
        tmp = home / ("usage-" + uuid.uuid4().hex + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump(dict(day=today, characters=used + characters * 3), stream)
        tmp.replace(counter)
        return True


def approval_active(auth, characters, now=None):
    """Accept the installed ISO marker and legacy Unix expiries without network I/O."""
    from datetime import datetime
    from math import isfinite

    if not isinstance(auth, dict):
        return False
    expiry = auth.get("expires_at")
    if isinstance(expiry, str):
        try:
            stamp = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                return False
            expiry = stamp.timestamp()
        except (ValueError, OverflowError):
            return False
    if type(expiry) not in (int, float) or not isfinite(expiry):
        return False
    return (
        auth.get("approved") is True
        and auth.get("voice_id") == VOICE_ID
        and expiry > (time.time() if now is None else now)
        and type(auth.get("max_characters")) is int
        and auth["max_characters"] >= characters
    )


def render(text, home):
    home = Path(home)
    text = speech_text(text)
    # Creating this review artifact is a separate, explicit card approval action.
    approval = home / "elevenlabs-approved.json"
    allowed = False
    try:
        auth = json.loads(approval.read_text())
        allowed = approval_active(auth, len(text))
    except (OSError, ValueError, TypeError):
        pass
    if allowed and not credits_available(len(text)):
        allowed = False
    if not allowed:
        return render_local(text, home / "tmp" / ("speech-" + uuid.uuid4().hex + ".aiff"))
    # Reserve the helper's three possible attempts before any paid request.
    if not reserve_usage(home, len(text), auth.get("daily_character_cap", 0)):
        return render_local(text, home / "tmp" / ("speech-" + uuid.uuid4().hex + ".aiff"))
    output = home / "tmp" / ("speech-" + uuid.uuid4().hex + ".mp3")
    helper = Path.home() / "ted-screenshots/fictora-official/ted-voice/tools/tts.sh"
    try:
        r = subprocess.run(
            [str(helper), VOICE_ID, text, str(output)], capture_output=True, timeout=60
        )
    except (OSError, subprocess.TimeoutExpired):
        r = None
    if r is None or r.returncode:
        output.unlink(missing_ok=True)
        return render_local(text, home / "tmp" / ("speech-" + uuid.uuid4().hex + ".aiff"))
    return output


def write_pcm(path, pcm):
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(16000)
        f.writeframes(pcm)


class Audio:
    def __init__(self, helper, emit, output_only=False, debug=False):
        self.emit = emit
        self.playing = False
        self.echo_clean = False
        self.last_done = 0
        self.process = subprocess.Popen(
            [str(helper)]
            + (["--output-only"] if output_only else [])
            + (["--debug-audio"] if debug else []),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )
        self.buffer = b""
        self.events = b""
        self.play_path = None

    def command(self, row):
        if self.process.poll() is not None:
            raise RuntimeError("audio device unavailable")
        self.process.stdin.write((json.dumps(row) + "\n").encode())

    def play(self, path):
        self.play_path = Path(path)
        self.playing = True
        self.command(dict(op="play", path=str(path)))

    def stop(self):
        self.command(dict(op="stop"))
        self.playing = False
        self.last_done = time.monotonic()
        if self.play_path and self.play_path.name.startswith("speech-"):
            self.play_path.unlink(missing_ok=True)
        self.play_path = None

    def pump(self):
        import select

        ready, _, _ = select.select([self.process.stdout, self.process.stderr], [], [], 0.03)
        for stream in ready:
            data = os.read(stream.fileno(), 32768)
            if stream is self.process.stdout:
                self.buffer += data
            else:
                self.events += data
                while b"\n" in self.events:
                    line, self.events = self.events.split(b"\n", 1)
                    try:
                        row = json.loads(line)
                    except ValueError:
                        continue
                    name = row.get("event", "audio_event")
                    if name == "audio_ready":
                        self.echo_clean = bool(row.get("echo_cancelled"))
                    if name in ("playback_done", "playback_failed"):
                        self.playing = False
                        self.last_done = time.monotonic()
                        if self.play_path and self.play_path.name.startswith("speech-"):
                            self.play_path.unlink(missing_ok=True)
                    self.emit(name, **{key: value for key, value in row.items() if key != "event"})
        if self.process.poll() is not None:
            raise RuntimeError("audio helper stopped")
        frames = []
        while len(self.buffer) >= 2560:
            frames.append(self.buffer[:2560])
            self.buffer = self.buffer[2560:]
        return frames

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            if stream:
                stream.close()
