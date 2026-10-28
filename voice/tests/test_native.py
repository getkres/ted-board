"""Native hardware checks. Capture additionally requires TED_NATIVE_CAPTURE=1.

The capture check plays a synthetic clip through TED_NATIVE_TEST_SPEAKER (88 on
the mini), transcribes the microphone PCM locally, and deletes its temporary WAV.
Stop the regular voice service before running it to avoid sending the test phrase.
"""

import json
import os
import re
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from runtime import Audio, Whisper, write_pcm


@unittest.skipUnless(os.environ.get("TED_NATIVE_HELPER"), "native helper not selected")
class NativeTests(unittest.TestCase):
    def test_provisional_stop_has_native_timestamps_and_resumes_same_playback(self):
        events = []
        audio = Audio(Path(os.environ["TED_NATIVE_HELPER"]),
                      lambda event, **fields: events.append(dict(event=event, **fields)),
                      output_only=True)
        try:
            deadline = time.monotonic() + 5
            while not any(r["event"] == "audio_ready" for r in events) and time.monotonic() < deadline:
                audio.pump()
            with tempfile.TemporaryDirectory(prefix="ted-native-stop-") as directory:
                path = Path(directory) / "long.wav"
                write_pcm(path, b"\x00\x00" * 16000 * 5)
                audio.play(path)
                deadline = time.monotonic() + 5
                while not any(r["event"] == "playback_started" for r in events) and time.monotonic() < deadline:
                    audio.pump()
                trigger = time.monotonic()
                audio.pause("native-test", trigger, time.time())
                deadline = time.monotonic() + 2
                while not any(r["event"] == "playback_stopped" for r in events) and time.monotonic() < deadline:
                    audio.pump()
                stopped = next(r for r in events if r["event"] == "playback_stopped")
                self.assertEqual(stopped["stop_id"], "native-test")
                self.assertEqual(stopped["play_id"], audio.play_id)
                self.assertGreaterEqual(stopped["stopped_monotonic"], trigger)
                self.assertLess(stopped["stopped_monotonic"] - trigger, 0.3)
                self.assertTrue(stopped["provisional"])
                self.assertTrue(path.exists())
                audio.resume("native-test")
                deadline = time.monotonic() + 2
                while not any(r["event"] == "playback_resumed" for r in events) and time.monotonic() < deadline:
                    audio.pump()
                resumed = next(r for r in events if r["event"] == "playback_resumed")
                self.assertEqual(resumed["play_id"], stopped["play_id"])
                audio.stop()
        finally:
            audio.close()

    def test_two_chimes_keep_the_duplex_helper_alive(self):
        events = []
        a = Audio(
            Path(os.environ["TED_NATIVE_HELPER"]),
            lambda event, **kw: events.append(event),
            output_only=True,
        )
        try:
            deadline = time.monotonic() + 5
            while not events and time.monotonic() < deadline:
                a.pump()
            for name in ["listen", "sent"]:
                events.clear()
                a.play(Path(os.environ["TED_VOICE_HOME"]) / "tones" / (name + ".wav"))
                deadline = time.monotonic() + 5
                while "playback_done" not in events and time.monotonic() < deadline:
                    a.pump()
                self.assertIn("playback_done", events)
                self.assertIsNone(a.process.poll())
        finally:
            a.close()

    @unittest.skipUnless(os.environ.get("TED_NATIVE_CAPTURE") == "1", "capture not selected")
    def test_jabra_capture_preserves_intelligible_speech_and_explicit_routes(self):
        helper = Path(os.environ["TED_NATIVE_HELPER"])
        devices = json.loads(subprocess.check_output([str(helper), "--devices"]))["devices"]
        input_id = next(d["id"] for d in devices if "jabra" in d["name"].lower() and d["input"])
        output_id = next(d["id"] for d in devices if "jabra" in d["name"].lower() and d["output"])
        events, frames = [], []
        audio = Audio(helper, lambda event, **kw: events.append(dict(event=event, **kw)), debug=True)
        speaker = None
        try:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                frames.extend(audio.pump())
                if frames and any(row["event"] == "audio_ready" for row in events):
                    break
            self.assertTrue(frames, "the selected Jabra must deliver PCM before playback")
            ready = next(row for row in events if row["event"] == "audio_ready")
            # Let the input pipeline settle before the first wake word.
            settle = time.monotonic() + 1
            while time.monotonic() < settle:
                audio.pump()
            frames.clear()
            speaker = subprocess.Popen(
                [
                    "/usr/bin/say",
                    "-a",
                    os.environ.get("TED_NATIVE_TEST_SPEAKER", "88"),
                    "-v",
                    "Daniel",
                    "-r",
                    "140",
                    "Hey Ted. Reply with the Jabra voice loop is working.",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            deadline = time.monotonic() + 15
            completed = None
            while time.monotonic() < deadline:
                frames.extend(audio.pump())
                if speaker.poll() is not None:
                    completed = completed or time.monotonic()
                    if time.monotonic() - completed >= 1:
                        break
            self.assertEqual(speaker.poll(), 0, "synthetic speaker playback must finish")
            with tempfile.TemporaryDirectory(prefix="ted-native-capture-") as directory:
                capture = Path(directory) / "capture.wav"
                write_pcm(capture, b"".join(frames))
                text = Whisper(
                    "/opt/homebrew/bin/whisper-cli",
                    Path.home() / ".cache/whisper/ggml-small.en.bin",
                ).transcribe(capture)
            normalized = re.sub(r"[^a-z ]", "", text.lower())
            self.assertIn("hey ted", normalized, "the microphone must preserve both wake words")
            self.assertIn("voice loop is working", normalized, "captured speech must be intelligible")
            self.assertEqual(ready["input_id"], input_id)
            self.assertEqual(ready["output_id"], output_id)
            self.assertEqual(ready["output_au_device"], output_id)
            self.assertTrue(ready["echo_cancelled"])
            self.assertEqual(ready["echo_cancellation"], "jabra_usb_hardware")
            capture_ready = next(row for row in events if row["event"] == "capture_audio_ready")
            self.assertEqual(capture_ready["input_id"], input_id)
            self.assertEqual(capture_ready["microphone_permission"], 3)
            self.assertTrue(capture_ready["input_device_uid"])
        finally:
            if speaker and speaker.poll() is None:
                speaker.terminate()
                speaker.wait(timeout=5)
            if speaker and speaker.stderr:
                speaker.stderr.close()
            audio.close()


if __name__ == "__main__":
    unittest.main()
