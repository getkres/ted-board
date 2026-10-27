import tempfile
import unittest
from pathlib import Path

from runtime import PendingQueue, Whisper


class RuntimeTests(unittest.TestCase):
    def test_wake_vocabulary_prompt_is_scoped_to_confirmation_not_request_transcription(self):
        from unittest.mock import Mock, patch

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "source.wav"
            path.touch()
            whisper = Whisper(path, path)
            with patch("runtime.subprocess.run", return_value=Mock(returncode=0, stdout="Ted, stop.")) as run:
                whisper.confirm_wake(path)
                prompted = run.call_args.args[0]
                whisper.transcribe(path)
                plain = run.call_args.args[0]
            self.assertIn("--prompt", prompted)
            self.assertIn("Ted, stop.", prompted[prompted.index("--prompt") + 1])
            self.assertNotIn("--prompt", plain)

    def test_source_segment_physically_crops_audio_before_whisper_can_read_future_words(self):
        import struct
        import wave
        from unittest.mock import Mock, patch

        from runtime import write_pcm

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "source.wav"
            write_pcm(path, struct.pack("<h", 100) * 32000 + struct.pack("<h", 200) * 32000
                      + struct.pack("<h", 300) * 32000)
            whisper = Whisper(path, path)
            observed = []

            def recognize(args, **kwargs):
                with wave.open(args[args.index("-f") + 1], "rb") as cropped:
                    frames = cropped.readframes(cropped.getnframes())
                    observed.append((cropped.getnframes(), struct.unpack("<h", frames[:2])[0],
                                     struct.unpack("<h", frames[-2:])[0]))
                return Mock(returncode=0, stdout="current words")

            with patch("runtime.subprocess.run", side_effect=recognize):
                self.assertEqual(whisper.transcribe_segment(path, 2.3, 2.7), "current words")
            self.assertEqual(observed, [(43200, 200, 300)])

    def test_offline_queue_is_private_bounded_and_unique(self):
        with tempfile.TemporaryDirectory() as d:
            q = PendingQueue(Path(d))
            for i in range(105):
                q.add("request " + str(i))
            rows = list((Path(d) / "pending").glob("*.json"))
            self.assertEqual(len(rows), 100)
            self.assertEqual(rows[0].stat().st_mode & 0o777, 0o600)

    def test_whisper_failure_does_not_deliver_noise(self):
        w = Whisper(Path("/missing"), Path("/missing"))
        with self.assertRaises(RuntimeError):
            w.transcribe(Path("/unused"))


if __name__ == "__main__":
    unittest.main()


class CreditTests(unittest.TestCase):
    def test_overage_or_unknown_billing_never_allows_paid_voice(self):
        from runtime import subscription_safe

        self.assertFalse(
            subscription_safe(
                dict(
                    status="active",
                    character_limit=10000,
                    character_count=0,
                    max_credit_limit_extension="unlimited",
                ),
                100,
            )
        )
        self.assertFalse(
            subscription_safe(dict(status="active", character_limit=10000, character_count=0), 100)
        )
        self.assertFalse(
            subscription_safe(
                dict(
                    status="active",
                    character_limit=10000,
                    character_count=9990,
                    max_credit_limit_extension=0,
                ),
                100,
            )
        )
        self.assertTrue(
            subscription_safe(
                dict(
                    status="active",
                    character_limit=10000,
                    character_count=0,
                    max_credit_limit_extension=0,
                ),
                100,
            )
        )


class ApprovalTests(unittest.TestCase):
    def test_approval_expiry_accepts_iso_and_unix(self):
        from runtime import VOICE_ID, approval_active

        auth = dict(approved=True, voice_id=VOICE_ID, max_characters=400)
        for expiry in [1001, "1970-01-01T00:16:41+00:00", "1970-01-01T00:16:41Z"]:
            self.assertTrue(approval_active(dict(auth, expires_at=expiry), 100, now=1000))

    def test_invalid_or_expired_approval_is_inactive(self):
        from runtime import VOICE_ID, approval_active

        auth = dict(approved=True, voice_id=VOICE_ID, max_characters=400)
        for expiry in [
            1000,
            "1970-01-01T00:16:40+00:00",
            "1970-01-01T00:16:41",
            "invalid",
            None,
            True,
        ]:
            self.assertFalse(approval_active(dict(auth, expires_at=expiry), 100, now=1000))
        self.assertFalse(approval_active([], 100, now=1000))

    def test_iso_marker_reaches_credit_guard_without_synthesis(self):
        import json
        from datetime import datetime, timedelta, timezone
        from unittest.mock import patch

        from runtime import VOICE_ID, render

        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            expiry = (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat()
            (home / "elevenlabs-approved.json").write_text(
                json.dumps(
                    dict(approved=True, voice_id=VOICE_ID, max_characters=400, expires_at=expiry)
                )
            )
            with (
                patch("runtime.credits_available", return_value=False) as credits,
                patch("runtime.render_local", return_value=home / "local.aiff"),
                patch("runtime.subprocess.run") as synthesis,
            ):
                render("hello", home)
                credits.assert_called_once_with(5)
                synthesis.assert_not_called()

    def test_daily_cap_reserves_all_three_helper_attempts(self):
        import json
        import time
        from unittest.mock import Mock, patch

        from runtime import VOICE_ID, render

        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            (home / "tmp").mkdir()
            (home / "elevenlabs-approved.json").write_text(
                json.dumps(
                    dict(
                        approved=True,
                        voice_id=VOICE_ID,
                        expires_at=time.time() + 60,
                        max_characters=400,
                        daily_character_cap=6,
                    )
                )
            )
            with (
                patch("runtime.credits_available", return_value=True),
                patch("runtime.subprocess.run", return_value=Mock(returncode=0)) as paid,
                patch("runtime.render_local", return_value=home / "local.aiff"),
            ):
                render("hi", home)
                render("hi", home)
                self.assertEqual(paid.call_count, 1)
                self.assertEqual(
                    json.loads((home / "elevenlabs-usage.json").read_text())["characters"], 6
                )


class AudioDiagnosticsTests(unittest.TestCase):
    def test_native_cursor_is_correlated_and_preserved_across_pause_and_resume(self):
        import json
        from unittest.mock import Mock, patch

        from runtime import Audio

        audio = Audio.__new__(Audio)
        audio.emit = Mock()
        audio.process = Mock()
        audio.process.poll.return_value = None
        audio.buffer = audio.events = b""
        audio.play_path = None
        audio.playing = True
        audio.play_id = "current"
        rows = [dict(event="playback_started", play_id="current", position_seconds=0, duration_seconds=40),
                dict(event="playback_stopped", play_id="current", stop_id="wake", position_seconds=5, duration_seconds=40),
                dict(event="playback_resumed", play_id="current", position_seconds=5, duration_seconds=40),
                dict(event="playback_progress", play_id="old", position_seconds=30, duration_seconds=40)]
        for row in rows:
            with patch("select.select", return_value=([audio.process.stderr], [], [])), patch("os.read", return_value=(json.dumps(row) + "\n").encode()):
                audio.pump()
        self.assertEqual(audio.playback_position_seconds, 5)
        self.assertEqual(audio.playback_duration_seconds, 40)
        self.assertEqual(audio.last_stop["stop_id"], "wake")

    def test_pause_emits_correlated_stop_request_without_destroying_render(self):
        import io
        import json
        from unittest.mock import Mock, patch

        from runtime import Audio

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "speech-test.wav"
            path.touch()
            audio = Audio.__new__(Audio)
            audio.process = Mock()
            audio.process.poll.return_value = None
            audio.process.stdin = io.BytesIO()
            audio.emit = Mock()
            audio.playing = True
            audio.paused = False
            audio.play_path = path
            audio.play_id = "play-1"
            with patch("runtime.time.monotonic", return_value=12.3), patch("runtime.time.time", return_value=34.5):
                audio.pause("wake-1", 12.0, 34.2)
            row = json.loads(audio.process.stdin.getvalue())
            self.assertEqual(row["op"], "pause")
            self.assertEqual(row["stop_id"], "wake-1")
            self.assertEqual(row["trigger_monotonic"], 12.0)
            self.assertEqual(row["requested_monotonic"], 12.3)
            self.assertTrue(path.exists())
            self.assertFalse(audio.playing)
            self.assertTrue(audio.paused)

    def test_native_old_completion_cannot_clear_current_playback(self):
        import json
        from unittest.mock import Mock, patch

        from runtime import Audio

        audio = Audio.__new__(Audio)
        audio.emit = Mock()
        audio.process = Mock()
        audio.process.poll.return_value = None
        audio.buffer = audio.events = b""
        audio.play_path = None
        audio.playing = True
        audio.play_id = "new-play"
        row = dict(event="playback_done", play_id="old-play")
        with patch("select.select", return_value=([audio.process.stderr], [], [])), patch("os.read", return_value=(json.dumps(row) + "\n").encode()):
            audio.pump()
        self.assertTrue(audio.playing)

    def test_native_device_and_error_fields_reach_event_log(self):
        import json
        from unittest.mock import Mock, patch

        from runtime import Audio

        for row in [
            dict(event="audio_ready", echo_cancelled=True, input_id=99, output_id=94),
            dict(
                event="engine_start_failed",
                error_domain="com.apple.coreaudio.avfaudio",
                error_code=-10875,
            ),
        ]:
            with self.subTest(event=row["event"]):
                audio = Audio.__new__(Audio)
                audio.emit = Mock()
                audio.process = Mock()
                audio.process.poll.return_value = None
                audio.buffer = b""
                audio.events = b""
                audio.play_path = None
                audio.playing = False
                audio.echo_clean = False
                with (
                    patch("select.select", return_value=([audio.process.stderr], [], [])),
                    patch("os.read", return_value=(json.dumps(row) + "\n").encode()),
                ):
                    audio.pump()
                audio.emit.assert_called_once_with(
                    row["event"], **{k: v for k, v in row.items() if k != "event"}
                )


class CaptureHealthTests(unittest.TestCase):
    def test_energy_vad_and_score_window_resets_without_retaining_pcm(self):
        import struct

        from runtime import CaptureDiagnostics

        rows = []
        d = CaptureDiagnostics(
            lambda event, **fields: rows.append(dict(event=event, **fields)), now=0
        )
        d.feed(struct.pack("<4h", 16384, -16384, 16384, -16384), 0.75, [True, False])
        d.feed(struct.pack("<4h", 16384, -16384, 16384, -16384), 0.25, [False, False])
        d.tick(now=4.99)
        self.assertEqual(rows, [])
        d.tick(now=5)
        self.assertEqual(rows[0]["samples"], 8)
        self.assertAlmostEqual(rows[0]["rms"], 0.5)
        self.assertAlmostEqual(rows[0]["rms_dbfs"], -6.021, places=2)
        self.assertEqual(rows[0]["vad_voiced_ratio"], 0.25)
        self.assertEqual(rows[0]["max_wake_score"], 0.75)
        self.assertNotIn("pcm", rows[0])
        d.tick(now=10)
        self.assertEqual(rows[1]["samples"], 0)
        self.assertEqual(rows[1]["rms"], 0)
        self.assertEqual(rows[1]["vad_voiced_ratio"], 0)
        self.assertEqual(rows[1]["max_wake_score"], 0)
