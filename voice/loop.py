"""Voice state machine. Audio capture and wake inference keep running during speech."""

import json
import math
import os
import re
import shutil
import time
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from core import (
    Endpoint,
    Pause,
    PlaybackGate,
    speech_text,
    spoken_echo,
    wake_command,
    wake_retry_plausible,
)
from runtime import PendingQueue, render, render_local, write_pcm
from session import Offline


class VoiceLoop:
    def __init__(
        self,
        home,
        audio,
        whisper,
        bridge,
        emit,
        executor=None,
        verifier=None,
        verify_executor=None,
        debug=False,
    ):
        self.home = Path(home)
        self.audio = audio
        self.whisper = whisper
        self.bridge = bridge
        self.emit = emit
        self.debug = debug
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
        self.energy_recent = deque(maxlen=4)
        self.barge_min_rms = 10 ** (-45 / 20)
        self.future = None
        self.request = None
        self.last_poll = 0
        self.generation = 0
        self.future_kind = None
        self.trigger_time = 0
        self.last_trigger = -100
        self.cancelled_futures = []
        self.spoken_text = ""
        self.awaiting_followup = False
        self.followup_rearmed = False
        self.confirmed_stop_prefix = None
        self.fixture = None
        self.stop_scan_future = None
        self.stop_scan = None
        self.last_stop_scan = -100
        self.stop_scan_voice = 0
        self.stop_scan_silence = 0

    def playback_snapshot(self):
        position = getattr(self.audio, "playback_position_seconds", None)
        duration = getattr(self.audio, "playback_duration_seconds", None)
        path = getattr(self.audio, "play_path", None)
        play_id = getattr(self.audio, "play_id", None)
        if (type(position) not in (int, float) or type(duration) not in (int, float)
                or not math.isfinite(position) or not math.isfinite(duration)
                or position < 0 or duration <= 0):
            return None
        return dict(position=position, duration=duration,
                    path=Path(path) if isinstance(path, (str, Path)) else None,
                    play_id=play_id if isinstance(play_id, str) else None)

    def estimated_spoken_text(self, playback, lookback=2.7):
        """A bounded fallback only; unknown progress never vetoes an entire reply."""
        if not playback:
            return ""
        words = self.spoken_text.split()
        rate = len(words) / playback["duration"]
        end = min(len(words), math.ceil(playback["position"] * rate) + 2)
        start = max(0, math.floor((playback["position"] - lookback) * rate) - 2)
        return " ".join(words[start:end])

    def verification_context(self, candidate):
        playback = candidate.get("playback")
        if not playback:
            return None
        playback = dict(playback)
        stopped = getattr(self.audio, "last_stop", None)
        stopped_monotonic = None
        if (isinstance(stopped, dict) and stopped.get("stop_id") == candidate.get("trigger_id")
                and stopped.get("play_id") == playback["play_id"]
                and type(stopped.get("position_seconds")) in (float, int)):
            playback["position"] = stopped["position_seconds"]
            stopped_monotonic = stopped.get("stopped_monotonic")
        lookback = min(2.4, len(candidate["preroll"]) * 0.08) + 0.3
        if type(stopped_monotonic) in (float, int):
            window_end = candidate.get("capture_ends_monotonic", candidate["started"])
            window_start = window_end - len(candidate["preroll"]) * 0.08
            lookback = min(lookback, max(0, stopped_monotonic - window_start + 0.3))
        if lookback == 0:
            return dict(path=playback["path"], start=playback["position"], seconds=0,
                        fallback_text="", source_silent=True,
                        wake_confirmation=bool(candidate.get("barge_in") and candidate.get("score", 0) >= self.gate.barge_threshold))
        start = max(0, playback["position"] - lookback)
        if not playback["path"] or playback["position"] <= start:
            return None
        return dict(path=playback["path"], start=start, seconds=playback["position"] - start,
                    fallback_text=self.estimated_spoken_text(playback, lookback),
                    wake_confirmation=bool(candidate.get("barge_in") and candidate.get("score", 0) >= self.gate.barge_threshold))

    def record_verification(self, path, result):
        """Explicit short-lived diagnostics only, never ordinary transcript logs."""
        if (not self.debug or not (self.home / "diagnostics-enabled").is_file()
                or not (self.home / "diagnostic-wake-capture").is_file()):
            return None
        directory = self.home / "diagnostics/verification"
        try:
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            stem = str(time.time_ns()) + "-" + uuid.uuid4().hex
            capture = directory / (stem + ".wav")
            metadata = directory / (stem + ".json")
            fd = os.open(capture, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as output, Path(path).open("rb") as original:
                shutil.copyfileobj(original, output)
            fd = os.open(metadata, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as output:
                json.dump(dict(at=time.time(), transcript=result["text"],
                               initial_transcript=result.get("initial_text"),
                               confirmation_retry=result.get("confirmation_retry", False),
                               source_transcript=result["spoken_text"], echo_method=result["echo_method"],
                               capture_wav=str(capture)), output)
            for old in sorted(directory.glob("*.json"))[:-5]:
                old.with_suffix(".wav").unlink(missing_ok=True)
                old.unlink(missing_ok=True)
            return metadata
        except OSError:
            return None

    def verify_frames(self, frames, playback=None):
        path = self.home / "tmp" / ("verify-" + uuid.uuid4().hex + ".wav")
        write_pcm(path, b"".join(frames))

        def verify():
            source = None
            try:
                if playback and not playback.get("source_silent"):
                    source = self.home / "tmp" / ("echo-source-" + uuid.uuid4().hex + Path(playback["path"]).suffix)
                    try:
                        fd = os.open(source, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                        with os.fdopen(fd, "wb") as output, Path(playback["path"]).open("rb") as original:
                            shutil.copyfileobj(original, output)
                    except OSError:
                        source.unlink(missing_ok=True)
                        source = None
                text = self.verifier.transcribe(path)
                initial_text = text
                confirmation_retry = False
                if playback and playback.get("wake_confirmation") and wake_retry_plausible(text):
                    try:
                        text = self.verifier.confirm_wake(path)
                        confirmation_retry = True
                    except (OSError, RuntimeError):
                        pass
                spoken = playback["fallback_text"] if playback else ""
                method = ("playback_silent" if playback.get("source_silent") else "estimated_window") if playback else "unavailable"
                if source:
                    try:
                        spoken = self.verifier.transcribe_segment(source, playback["start"], playback["seconds"])
                        method = "audio_slice"
                    except (OSError, RuntimeError, ValueError):
                        pass
                result = dict(text=text, spoken_text=spoken, echo_method=method,
                              initial_text=initial_text, confirmation_retry=confirmation_retry)
                diagnostic = self.record_verification(path, result)
                if diagnostic:
                    result["diagnostic_path"] = str(diagnostic)
                return result if playback or diagnostic else text
            finally:
                path.unlink(missing_ok=True)
                if source:
                    source.unlink(missing_ok=True)

        future = self.verify_executor.submit(verify)
        future.add_done_callback(lambda _: path.unlink(missing_ok=True))
        return future

    def submit_candidate(self, candidate):
        frames = candidate["preroll"] + candidate["extra"]
        candidate["submitted_frames"] = len(frames)
        candidate["submitted_monotonic"] = time.monotonic()
        context = self.verification_context(candidate)
        return self.verify_frames(frames, context) if context else self.verify_frames(frames)

    def close(self):
        """Release workers when capture stops, and delete abandoned private audio."""
        def discard_speech(future):
            try:
                Path(future.result()).unlink(missing_ok=True)
            except Exception:
                pass

        pending = [(self.future, self.future_kind)] + self.cancelled_futures
        pending += [(self.verify_future, None), (self.stop_scan_future, None)]
        for future, kind in pending:
            if future is not None:
                if kind == "speech":
                    future.add_done_callback(discard_speech)
                future.cancel()
        for executor in {self.executor, self.verify_executor}:
            executor.shutdown(wait=False, cancel_futures=True)

    def chime(self, name):
        path = self.home / "tones" / (name + ".wav")
        if path.exists():
            self.audio.play(path)

    def begin(self, score):
        now = time.monotonic()
        if self.candidate or now - self.last_candidate < 2:
            return
        self.last_candidate = now
        playing = self.audio.playing
        playback = self.playback_snapshot() if playing else None
        self.candidate = dict(
            score=score, started=now, trigger_at=time.time(), trigger_id=uuid.uuid4().hex,
            preroll=list(self.preroll), extra=[], barge_in=playing,
            spoken_text=self.estimated_spoken_text(playback), provisional=playing, playback=playback,
            generation=self.generation, rechecks=0, capture_ends_monotonic=now,
        )
        self.emit("wake_candidate", score=round(score, 5), barge_in=playing,
                  trigger_id=self.candidate["trigger_id"], trigger_monotonic=now,
                  trigger_at=self.candidate["trigger_at"], source="wake_model")
        if playing:
            # Silence promptly, but accept no request until Whisper confirms.
            # pause() preserves the scheduled audio so false candidates can resume.
            self.audio.pause(self.candidate["trigger_id"], now, self.candidate["trigger_at"])
            # The wake model can fire before the phrase finishes. The same
            # eight-frame tail used at idle completes Whisper's confirmation
            # window, while playback is already silent.

    def begin_confirmed(self, score, frames, started, candidate=None):
        now = time.monotonic()
        self.last_trigger = now
        self.trigger_time = started
        self.generation += 1
        self.request = None
        if self.future:
            self.future.cancel()
            self.cancelled_futures.append((self.future, self.future_kind))
            self.future = None
        self.was_playing = bool(candidate.get("barge_in")) if candidate else self.audio.playing
        if candidate:
            self.audio.stop(candidate.get("trigger_id"), started, candidate.get("trigger_at"))
        else:
            self.audio.stop()
        if self.fixture and self.was_playing:
            self.emit("diagnostic_fixture_interrupted", trial_id=self.fixture,
                      interrupted_at=time.time(), interrupted_monotonic=now)
            self.fixture = None
        self.frames = frames
        self.endpoint = Endpoint(heard=True)
        self.state = "listening"
        self.awaiting_followup = True
        self.followup_rearmed = False
        prefix = candidate.get("confirmed_stop_prefix") if candidate else None
        self.confirmed_stop_prefix = (self.generation, prefix) if prefix else None
        self.chime("listen")
        self.emit("wake", score=round(score, 5), barge_in=self.was_playing,
                  trigger_id=candidate.get("trigger_id") if candidate else None,
                  trigger_monotonic=started,
                  trigger_at=candidate.get("trigger_at") if candidate else None,
                  confirmed_monotonic=now, confirmed_at=time.time())

    def feed(self, pcm, score, voiced):
        self.preroll.append(pcm)
        self.voiced_recent.append(voiced)
        samples = memoryview(pcm)[:len(pcm) // 2 * 2].cast("h")
        rms = math.sqrt(sum(sample * sample for sample in samples) / len(samples)) / 32768 if samples else 0
        self.energy_recent.append(rms)
        recent_rms = max(self.energy_recent)
        barge_energy = recent_rms >= self.barge_min_rms
        if self.debug and score >= 0.9:
            self.emit(
                "wake_score_debug",
                score=round(score, 6),
                voiced=voiced,
                recent_voice=any(self.voiced_recent),
                recent_rms_dbfs=round(20 * math.log10(max(recent_rms, 1e-6)), 2),
                barge_energy=barge_energy,
                gate_hits=self.gate.count,
                playing=self.audio.playing,
                state=self.state,
            )
        if self.candidate:
            candidate = self.candidate
            candidate["extra"].append(pcm)
            late = candidate.get("late_wake")
            if late:
                late["extra"].append(pcm)
            if len(candidate["extra"]) >= 8 and self.verify_future is None:
                self.verify_future = self.submit_candidate(candidate)
            # One newly observed high-score wake can arrive while the earlier
            # snapshot is being verified. Require a score reset and the same
            # playback threshold, even though provisional pause is now silent.
            if (candidate.get("barge_in") and not candidate.get("rechecks", 0)
                    and self.verify_future is not None and not late):
                above_threshold = score >= self.gate.barge_threshold
                if not above_threshold:
                    candidate["late_hits"] = 0
                    candidate["late_reset"] = candidate.get("late_reset", 0) + 1
                    if candidate["late_reset"] >= 2:
                        candidate["late_armed"] = True
                else:
                    candidate["late_reset"] = 0
                    if candidate.get("late_armed") and any(self.voiced_recent) and barge_energy and self.audio.echo_clean:
                        candidate["late_hits"] = candidate.get("late_hits", 0) + 1
                        if candidate["late_hits"] >= self.gate.hits:
                            candidate["late_wake"] = dict(preroll=list(self.preroll), extra=[],
                                                          score=score, observed_monotonic=time.monotonic())
                    else:
                        candidate["late_hits"] = 0
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
                self.future.add_done_callback(lambda _, path=capture: path.unlink(missing_ok=True))
                self.future_kind = "transcript"
            return
        self.was_playing = self.audio.playing
        # Only a verified duplex Jabra route enables hardware AEC barge-in.
        gated_playback = self.audio.playing or bool(self.candidate and self.candidate.get("barge_in"))
        if self.gate.accept(
            score if any(self.voiced_recent) and (not gated_playback or barge_energy) else 0,
            gated_playback, self.audio.echo_clean
        ):
            self.begin(score)
        # The baseline model targets Hey Ted and Ted stop listening. A bounded
        # verifier also covers bare stop when the wake score misses it.
        if self.state == "speaking" and self.audio.playing and self.audio.echo_clean and not self.candidate:
            if voiced:
                self.stop_scan_voice += 1
                self.stop_scan_silence = 0
            elif self.stop_scan_voice:
                self.stop_scan_silence += 1
        else:
            self.stop_scan_voice = self.stop_scan_silence = 0
        if (self.state == "speaking" and self.audio.playing and self.audio.echo_clean
                and not self.candidate and self.stop_scan_future is None
                and barge_energy
                and self.stop_scan_voice >= 2
                and (self.stop_scan_silence >= 2 or self.stop_scan_voice >= 25)
                and len(self.preroll) >= 10
                and time.monotonic() - self.last_stop_scan >= 0.8):
            self.last_stop_scan = time.monotonic()
            playback = self.playback_snapshot()
            self.stop_scan = dict(preroll=list(self.preroll), spoken_text=self.estimated_spoken_text(playback),
                                  started=self.last_stop_scan, started_at=time.time(), extra=[],
                                  generation=self.generation, playback=playback)
            context = self.verification_context(self.stop_scan)
            self.stop_scan_future = self.verify_frames(self.stop_scan["preroll"], context) if context else self.verify_frames(self.stop_scan["preroll"])
            self.stop_scan_voice = self.stop_scan_silence = 0
        elif self.stop_scan:
            self.stop_scan["extra"].append(pcm)

    def accept_transcript(self, text):
        context = self.confirmed_stop_prefix
        self.confirmed_stop_prefix = None
        if context and self.awaiting_followup and context[0] == self.generation:
            prefix = context[1]
            pattern = r"^\s*" + r"\b[\s,.!:;]*".join(re.escape(word) for word in prefix) + r"\b[\s,.!:;]*"
            match = re.match(pattern, text, re.I)
            if match:
                # This is the same captured stop that already passed model,
                # Whisper, and echo checks, not a global recognition alias.
                text = "Ted, stop " + text[match.end():].strip()
                self.emit("confirmed_stop_prefix_removed", words=len(prefix))
        command = wake_command(text)
        if command == "__pause__":
            self.audio.stop()
            self.pause.stop()
            self.state = "paused"
            self.request = None
            self.emit("paused")
            return
        if command == "__interrupt__" or (command == "" and self.awaiting_followup and not self.followup_rearmed):
            self.audio.stop()
            self.frames = []
            self.endpoint = Endpoint()
            self.state = "listening"
            self.awaiting_followup = True
            self.followup_rearmed = True
            self.emit("followup_listening")
            return
        if command is None and self.awaiting_followup:
            command = text.strip()
        if not command:
            self.state = "idle"
            self.awaiting_followup = False
            self.emit("wake_rejected")
            return
        self.awaiting_followup = False
        try:
            self.request = self.bridge.deliver(command)
            self.state = "waiting"
            self.sent_at = time.monotonic()
            self.delivery_announced = False
            self.emit("submitted", seconds=round(self.sent_at - self.trigger_time, 3))
        except (Offline, OSError, RuntimeError):
            self.queue.add(command)
            self.emit("offline_queued", board_posted=False)
            self.state = "rendering"
            self.future = self.executor.submit(
                render_local,
                "Ted could not answer. Your request is saved locally for review.",
                self.home / "tmp" / ("notice-" + uuid.uuid4().hex + ".aiff"),
            )
            self.future_kind = "speech"

    def tick(self):
        retry = getattr(self.bridge, "tick", None)
        if callable(retry):
            retry()
        if self.stop_scan_future and self.stop_scan_future.done():
            scan, future = self.stop_scan, self.stop_scan_future
            self.stop_scan = self.stop_scan_future = None
            try:
                result = future.result()
                text = result["text"] if isinstance(result, dict) else result
                spoken = result["spoken_text"] if isinstance(result, dict) else scan["spoken_text"]
            except Exception:
                text = ""
            if (scan["generation"] == self.generation and not self.candidate
                    and self.state == "speaking" and self.audio.playing
                    and re.match(r"^(?:hey[ ,.!]*)?ted\b[ ,.!:]*stop\b", text.strip(), re.I)
                    and not spoken_echo(text, spoken)):
                now = time.monotonic()
                candidate = dict(score=0, started=now, trigger_at=time.time(),
                                 trigger_id=uuid.uuid4().hex, barge_in=True)
                self.emit("wake_candidate", score=None, barge_in=True, source="whisper_stop_scan",
                          trigger_id=candidate["trigger_id"], trigger_monotonic=now,
                          trigger_at=candidate["trigger_at"],
                          scan_started_monotonic=scan["started"], scan_started_at=scan["started_at"])
                self.begin_confirmed(0, scan["preroll"] + scan["extra"], now, candidate)
        if self.verify_future and self.verify_future.done():
            future = self.verify_future
            candidate = self.candidate
            self.verify_future = None
            self.candidate = None
            try:
                result = future.result()
                text = result["text"] if isinstance(result, dict) else result
                spoken = result["spoken_text"] if isinstance(result, dict) else candidate.get("spoken_text", "")
                command = wake_command(text)
                echo = spoken_echo(text, spoken) or (
                    isinstance(result, dict) and spoken_echo(result.get("initial_text", ""), spoken)
                )
                if self.debug:
                    self.emit(
                        "wake_verification_debug",
                        words=len(text.split()),
                        wake_prefix=command is not None,
                        contains_wake=bool(re.search(r"\bhey[ ,.!]*ted\b", text, re.I)),
                        audio_seconds=round(
                            candidate.get("submitted_frames", len(candidate["preroll"]) + len(candidate["extra"])) * 0.08, 3
                        ),
                        submitted_monotonic=candidate.get("submitted_monotonic"),
                        echo_method=result.get("echo_method", "unavailable") if isinstance(result, dict) else "estimated_window",
                        confirmation_retry=result.get("confirmation_retry", False) if isinstance(result, dict) else False,
                    )
            except Exception:
                command = None
                echo = False
            if command is None or echo:
                late = candidate.get("late_wake")
                if (late and not candidate.get("rechecks", 0)
                        and candidate.get("generation", self.generation) == self.generation):
                    candidate.update(preroll=late["preroll"], extra=late["extra"], rechecks=1, late_wake=None,
                                     capture_ends_monotonic=late["observed_monotonic"])
                    self.candidate = candidate
                    if len(candidate["extra"]) >= 8:
                        self.verify_future = self.submit_candidate(candidate)
                    self.emit("wake_verification_recheck", trigger_id=candidate.get("trigger_id"),
                              new_signal_monotonic=late["observed_monotonic"],
                              score=round(late["score"], 5), already_paused=True)
                    return
                self.emit("wake_candidate_rejected", score=round(candidate["score"], 5),
                          trigger_id=candidate.get("trigger_id"), reason="echo" if echo else "unconfirmed")
                if candidate.get("provisional"):
                    self.audio.resume(candidate.get("trigger_id"))
            elif command == "__pause__":
                self.accept_transcript(text)
                return
            else:
                if (command == "__interrupt__" and isinstance(result, dict)
                        and result.get("confirmation_retry") and candidate.get("barge_in")
                        and candidate["score"] >= self.gate.barge_threshold
                        and wake_retry_plausible(result.get("initial_text", ""))):
                    candidate["confirmed_stop_prefix"] = tuple(re.findall(r"[a-z]+", result["initial_text"].lower()))
                self.begin_confirmed(
                    candidate["score"],
                    candidate["preroll"] + candidate["extra"],
                    candidate["started"],
                    candidate,
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
                self.emit("speech_rendered", renderer="elevenlabs" if Path(value).suffix == ".mp3" else "local")
                self.audio.play(value)
                self.state = "speaking"
                self.emit("speech_started", seconds=round(time.monotonic() - self.trigger_time, 3))
        if self.state == "speaking" and not self.audio.playing and not self.candidate:
            if self.fixture:
                self.emit("diagnostic_fixture_completed", trial_id=self.fixture,
                          completed_at=time.time(), completed_monotonic=time.monotonic())
                self.fixture = None
            self.state = "idle"
            self.spoken_text = ""
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
            except (Offline, OSError) as exc:
                self.queue.add(self.request.get("text", ""), reason="reply unavailable; do not resend automatically")
                self.request = None
                self.state = "rendering"
                self.emit("reply_cancelled", reason=str(exc) if isinstance(exc, Offline) else "reply unavailable")
                self.future = self.executor.submit(
                    render_local,
                    "Ted could not answer. Your request is saved locally for review.",
                    self.home / "tmp" / ("notice-" + uuid.uuid4().hex + ".aiff"),
                )
                self.future_kind = "speech"
                return
            if self.request.get("accepted") and not self.delivery_announced:
                self.delivery_announced = True
                self.chime("sent")
                self.emit("delivered", seconds=round(time.monotonic() - self.trigger_time, 3))
            if reply:
                self.state = "rendering"
                self.spoken_text = speech_text(reply)
                self.future = self.executor.submit(render, reply, self.home)
                self.future_kind = "speech"
                self.emit("reply_received", seconds=round(time.monotonic() - self.sent_at, 3))
        self.diagnostic_fixture()

    def diagnostic_fixture(self):
        """Explicit local acceptance fixtures use normal playback and echo guards."""
        if self.state != "idle" or self.candidate or not (self.home / "diagnostics-enabled").is_file():
            return
        for request in sorted((self.home / "diagnostics").glob("*.request.json")):
            try:
                row = json.loads(request.read_text())
                path = Path(row["path"]).resolve(strict=True)
                path.relative_to((self.home / "tmp").resolve(strict=True))
                trial = row["trial_id"]
                if not path.is_file() or not isinstance(trial, str) or not trial or not isinstance(row.get("text"), str):
                    raise ValueError("invalid fixture")
            except (OSError, ValueError, KeyError, TypeError):
                self.emit("diagnostic_fixture_rejected")
                request.unlink(missing_ok=True)
                continue
            request.unlink(missing_ok=True)
            self.fixture = trial
            self.spoken_text = row["text"]
            self.audio.play(path)
            self.state = "speaking"
            self.emit("diagnostic_fixture_started", trial_id=trial, path=str(path),
                      started_at=time.time(), started_monotonic=time.monotonic())
            return
