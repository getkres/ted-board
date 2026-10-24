import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from loop import VoiceLoop


class LoopTests(unittest.TestCase):
    def make(self, home):
        audio = Mock(playing=False, echo_clean=True)
        loop = VoiceLoop(Path(home), audio, Mock(), Mock(), lambda *a, **k: None, Mock())
        return loop, audio

    def test_verified_pause_is_durable_and_stops_audio(self):
        with tempfile.TemporaryDirectory() as d:
            loop, audio = self.make(d)
            loop.accept_transcript("Ted, stop listening.")
            self.assertTrue((Path(d) / "paused").exists())
            audio.stop.assert_called_once()

    def test_unverified_wake_cannot_reach_live_ted(self):
        with tempfile.TemporaryDirectory() as d:
            loop, audio = self.make(d)
            loop.accept_transcript("hey dad what time is it")
            loop.bridge.deliver.assert_not_called()

    def test_verified_command_is_tagged_by_bridge_and_tone_follows_delivery(self):
        with tempfile.TemporaryDirectory() as d:
            loop, audio = self.make(d)
            loop.accept_transcript("hey Ted what is open")
            loop.bridge.deliver.assert_called_once_with("what is open")
            self.assertEqual(loop.state, "waiting")

    def test_barge_in_stops_playback_and_cancels_old_reply(self):
        with tempfile.TemporaryDirectory() as d:
            loop, audio = self.make(d)
            audio.playing = True
            loop.request = {"old": True}
            loop.state = "speaking"
            loop.begin_confirmed(0.99, [b"\x00" * 2560], 0)
            audio.stop.assert_called_once()
            self.assertIsNone(loop.request)
            self.assertEqual(loop.state, "listening")

    def test_rollover_during_speech_render_cannot_play_stale_reply(self):
        from session import Offline

        with tempfile.TemporaryDirectory() as d:
            loop, audio = self.make(d)
            loop.request = {"session_id": "old"}
            loop.state = "rendering"
            p = Path(d) / "speech-old.aiff"
            p.touch()
            loop.future = Mock()
            loop.future.done.return_value = True
            loop.future.result.return_value = p
            loop.future_kind = "speech"
            loop.bridge.assert_current = Mock(side_effect=Offline("rolled over"))
            loop.tick()
            audio.play.assert_not_called()
            self.assertFalse(p.exists())

    def test_unconfirmed_submission_never_plays_sent_tone(self):
        with tempfile.TemporaryDirectory() as d:
            loop, audio = self.make(d)
            loop.chime = Mock()
            loop.accept_transcript("hey Ted what is open")
            loop.chime.assert_not_called()

    def test_model_warmup_scores_cannot_wake_on_silence(self):
        with tempfile.TemporaryDirectory() as d:
            loop, audio = self.make(d)
            for _ in range(40):
                loop.feed(b"\x00" * 2560, 0.999, False)
            self.assertEqual(loop.state, "idle")
            audio.stop.assert_not_called()

    def test_candidate_is_verified_before_chime_or_playback_interrupt(self):
        with tempfile.TemporaryDirectory() as d:
            loop, audio = self.make(d)
            audio.playing = True
            loop.feed(b"\x00" * 2560, 0.999, True)
            loop.feed(b"\x00" * 2560, 0.999, True)
            audio.stop.assert_not_called()
            self.assertNotEqual(loop.state, "listening")

    def test_false_candidate_preserves_current_playback_and_request(self):
        from concurrent.futures import Future

        with tempfile.TemporaryDirectory() as d:
            loop, audio = self.make(d)
            loop.state = "speaking"
            audio.playing = True
            loop.request = {"old": True}
            loop.candidate = {"score": 0.999, "started": 0, "preroll": [], "extra": []}
            loop.verify_future = Future()
            loop.verify_future.set_result("Hey dad, get ready.")
            loop.tick()
            audio.stop.assert_not_called()
            self.assertEqual(loop.request, {"old": True})

    def test_confirmed_candidate_starts_listening(self):
        from concurrent.futures import Future

        with tempfile.TemporaryDirectory() as d:
            loop, audio = self.make(d)
            loop.candidate = {"score": 0.999, "started": 0, "preroll": [], "extra": []}
            loop.verify_future = Future()
            loop.verify_future.set_result("Hey Ted.")
            loop.tick()
            audio.stop.assert_called_once()
            self.assertEqual(loop.state, "listening")

    def test_confirmed_pause_does_not_play_finished_old_render(self):
        from concurrent.futures import Future

        with tempfile.TemporaryDirectory() as d:
            loop, audio = self.make(d)
            loop.candidate = {"score": 0.999, "started": 0, "preroll": [], "extra": []}
            loop.verify_future = Future()
            loop.verify_future.set_result("Ted, stop listening.")
            loop.future = Future()
            loop.future.set_result(Path(d) / "old.aiff")
            loop.future_kind = "speech"
            loop.tick()
            audio.play.assert_not_called()
            self.assertTrue(loop.pause.paused)

    def test_missing_speech_does_not_send(self):
        with tempfile.TemporaryDirectory() as d:
            loop, audio = self.make(d)
            loop.accept_transcript("Hey Ted")
            loop.bridge.deliver.assert_not_called()


if __name__ == "__main__":
    unittest.main()
