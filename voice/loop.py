"""Voice state machine. Audio capture and wake inference keep running during speech."""

import time
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from core import Endpoint, Pause, PlaybackGate, wake_command
from runtime import PendingQueue, render, write_pcm
from session import Offline


class VoiceLoop:
    def __init__(
        self, home, audio, whisper, bridge, emit, executor=None, verifier=None, verify_executor=None
    ):
        self.home = Path(home)
        self.audio = audio
        self.whisper = whisper
        self.bridge = bridge
        self.emit = emit
        self.executor = executor or ThreadPoolExecutor(max_workers=1)
        self.verifier = verifier or whisper
        self.verify_executor = verify_executor or ThreadPoolExecutor(max_workers=1)
        self.candidate = None
        self.verify_future = None
        self.last_candidate = -100
        self.pause = Pause(home)
        self.queue = PendingQueue(home)
        (self.home / "tmp").mkdir(parents=True, exist_ok=True, mode=0o700)
        self.state = "idle"
        self.preroll = deque(maxlen=30)
        self.frames = []
        self.endpoint = None
        self.gate = PlaybackGate(0.95, 0.99, 2)
        self.voiced_recent = deque(maxlen=4)
        self.future = None
        self.request = None
        self.last_poll = 0
        self.generation = 0
        self.future_kind = None
        self.trigger_time = 0
        self.last_trigger = -100
        self.cancelled_futures = []

    def chime(self, name):
        path = self.home / "tones" / (name + ".wav")
        if path.exists():
            self.audio.play(path)

    def begin(self, score):
        now = time.monotonic()
        if self.candidate or now - self.last_candidate < 2:
            return
        self.last_candidate = now
        self.candidate = dict(score=score, started=now, preroll=list(self.preroll), extra=[])
        self.emit("wake_candidate", score=round(score, 5), barge_in=self.audio.playing)

    def begin_confirmed(self, score, frames, started):
        now = time.monotonic()
        if now - self.last_trigger < 2:
            return
        self.last_trigger = now
        self.trigger_time = started
        self.generation += 1
        self.request = None
        if self.future:
            self.future.cancel()
            self.cancelled_futures.append((self.future, self.future_kind))
            self.future = None
        self.was_playing = self.audio.playing
        self.audio.stop()
        self.frames = frames
        self.endpoint = Endpoint(heard=True)
        self.state = "listening"
        self.chime("listen")
        self.emit("wake", score=round(score, 5), barge_in=self.was_playing)

    def feed(self, pcm, score, voiced):
        self.preroll.append(pcm)
        self.voiced_recent.append(voiced)
        if self.candidate:
            self.candidate["extra"].append(pcm)
            if len(self.candidate["extra"]) >= 8 and self.verify_future is None:
                path = self.home / "tmp" / ("verify-" + uuid.uuid4().hex + ".wav")
                write_pcm(path, b"".join(self.candidate["preroll"] + self.candidate["extra"]))

                def verify():
                    try:
                        return self.verifier.transcribe(path)
                    finally:
                        path.unlink(missing_ok=True)

                self.verify_future = self.verify_executor.submit(verify)
        if self.state == "listening":
            self.frames.append(pcm)
            if self.endpoint.feed(voiced, 0.08):
                capture = self.home / "tmp" / ("capture-" + uuid.uuid4().hex + ".wav")
                write_pcm(capture, b"".join(self.frames))
                self.frames = []
                self.state = "transcribing"

                def transcribe():
                    t = time.monotonic()
                    try:
                        return self.whisper.transcribe(capture), time.monotonic() - t
                    finally:
                        capture.unlink(missing_ok=True)

                self.future = self.executor.submit(transcribe)
                self.future_kind = "transcript"
            return
        self.was_playing = self.audio.playing
        # AEC residual is the only barge-in input. Without AEC, playback is muted to wake detection.
        if self.gate.accept(
            score if any(self.voiced_recent) else 0, self.audio.playing, self.audio.echo_clean
        ):
            self.begin(score)

    def accept_transcript(self, text):
        command = wake_command(text)
        if command == "__pause__":
            self.audio.stop()
            self.pause.stop()
            self.state = "paused"
            self.request = None
            self.emit("paused")
            return
        if not command:
            self.state = "idle"
            self.emit("wake_rejected")
            return
        try:
            self.request = self.bridge.deliver(command)
            self.state = "waiting"
            self.sent_at = time.monotonic()
            self.delivery_announced = False
            self.emit("submitted", seconds=round(self.sent_at - self.trigger_time, 3))
        except (Offline, OSError, RuntimeError):
            self.queue.add(command)
            posted = False
            try:
                result = self.bridge.transport.call(
                    "ted_reply",
                    card_id="c-hey-ted-voice-1022",
                    text=("[voice, ted offline] " + command).replace(chr(0x2014), ", ")[:1900],
                )
                posted = result.get("ok") is True
            except Exception:
                pass
            self.emit("offline_queued", board_posted=posted)
            self.state = "rendering"
            self.future = self.executor.submit(
                render,
                "Ted is offline. Your request is on the board."
                if posted
                else "Ted is offline. Your request is saved locally, and the board is unavailable.",
                self.home,
            )
            self.future_kind = "speech"
            # Publish only a status, never private speech, and never create database rows here.
            try:
                from live_status import update

                update(
                    "c-hey-ted-voice-1022",
                    "blocked",
                    "voice request saved locally because live ted is offline",
                )
            except Exception:
                self.emit("board_status_pending")

    def tick(self):
        if self.verify_future and self.verify_future.done():
            future = self.verify_future
            candidate = self.candidate
            self.verify_future = None
            self.candidate = None
            try:
                text = future.result()
                command = wake_command(text)
            except Exception:
                command = None
            if command is None:
                self.emit("wake_candidate_rejected", score=round(candidate["score"], 5))
            elif command == "__pause__":
                self.accept_transcript(text)
                return
            else:
                self.begin_confirmed(
                    candidate["score"],
                    candidate["preroll"] + candidate["extra"],
                    candidate["started"],
                )
        for future, kind in self.cancelled_futures[:]:
            if future.done():
                try:
                    value = future.result()
                    if kind == "speech":
                        Path(value).unlink(missing_ok=True)
                except Exception:
                    pass
                self.cancelled_futures.remove((future, kind))
        if self.future and self.future.done():
            future = self.future
            kind = self.future_kind
            self.future = None
            try:
                value = future.result()
            except Exception:
                self.state = "idle"
                self.emit("processing_failed")
                return
            if kind == "transcript":
                text, seconds = value
                self.emit("transcribed", seconds=round(seconds, 3))
                self.accept_transcript(text)
            else:
                if self.request:
                    try:
                        self.bridge.assert_current(self.request["session_id"])
                    except Offline:
                        Path(value).unlink(missing_ok=True)
                        self.state = "idle"
                        self.emit("stale_speech_discarded")
                        return
                self.audio.play(value)
                self.state = "speaking"
                self.emit("speech_started", seconds=round(time.monotonic() - self.trigger_time, 3))
        if self.state == "speaking" and not self.audio.playing:
            self.state = "idle"
        if self.state == "waiting" and time.monotonic() - self.last_poll > 0.25:
            self.last_poll = time.monotonic()
            if time.monotonic() - self.sent_at > 180:
                self.queue.add(
                    self.request.get("text", ""),
                    reason="reply timed out; delivery may be held; do not resend automatically",
                )
                self.request = None
                self.state = "rendering"
                self.emit("reply_timeout")
                self.future = self.executor.submit(
                    render,
                    "Ted has not confirmed a reply. Your request is saved locally for review.",
                    self.home,
                )
                self.future_kind = "speech"
                return
            try:
                reply = self.bridge.poll(self.request)
            except (Offline, OSError):
                self.state = "idle"
                self.emit("reply_cancelled")
                return
            if self.request.get("accepted") and not self.delivery_announced:
                self.delivery_announced = True
                self.chime("sent")
                self.emit("delivered", seconds=round(time.monotonic() - self.trigger_time, 3))
            if reply:
                self.state = "rendering"
                self.future = self.executor.submit(render, reply, self.home)
                self.future_kind = "speech"
                self.emit("reply_received", seconds=round(time.monotonic() - self.sent_at, 3))
