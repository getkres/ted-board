import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from loop import VoiceLoop

SPEECH_PCM = (1000).to_bytes(2, "little", signed=True) * 1280  # -30.3 dBFS
QUIET_PCM = (50).to_bytes(2, "little", signed=True) * 1280  # -56.3 dBFS


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

    def test_candidate_pauses_playback_but_waits_for_confirmation_before_listening(self):
        with tempfile.TemporaryDirectory() as d:
            loop, audio = self.make(d)
            audio.playing = True
            loop.feed(SPEECH_PCM, 0.999, True)
            loop.feed(SPEECH_PCM, 0.999, True)
            audio.pause.assert_called_once()
            audio.stop.assert_not_called()
            self.assertNotEqual(loop.state, "listening")

    def test_quiet_voiced_model_peak_cannot_pause_playback(self):
        with tempfile.TemporaryDirectory() as d:
            loop, audio = self.make(d)
            audio.playing = True
            for _ in range(8):
                loop.feed(QUIET_PCM, 0.999, True)
            self.assertTrue(loop.candidate is None)
            audio.pause.assert_not_called()

    def test_borderline_noise_is_rejected_while_softer_true_voice_still_wakes(self):
        borderline = (106).to_bytes(2, "little", signed=True) * 1280  # -49.8 dBFS
        softer_voice = (500).to_bytes(2, "little", signed=True) * 1280  # -36.3 dBFS
        with tempfile.TemporaryDirectory() as d:
            loop, audio = self.make(d)
            audio.playing = True
            for _ in range(2):
                loop.feed(borderline, 0.999, True)
            audio.pause.assert_not_called()
            self.assertTrue(loop.candidate is None)
            for _ in range(2):
                loop.feed(softer_voice, 0.999, True)
            audio.pause.assert_called_once()

    def test_recent_speech_energy_preserves_wake_across_a_short_quiet_gap(self):
        with tempfile.TemporaryDirectory() as d:
            loop, audio = self.make(d)
            audio.playing = True
            loop.feed(SPEECH_PCM, 0, True)
            loop.feed(QUIET_PCM, 0.999, True)
            loop.feed(QUIET_PCM, 0.999, True)
            audio.pause.assert_called_once()

    def test_playback_energy_floor_does_not_change_idle_wake_admission(self):
        with tempfile.TemporaryDirectory() as d:
            loop, audio = self.make(d)
            loop.feed(QUIET_PCM, 0.999, True)
            loop.feed(QUIET_PCM, 0.999, True)
            self.assertIsNotNone(loop.candidate)
            audio.pause.assert_not_called()

    def test_quiet_model_peak_cannot_recheck_a_provisionally_paused_candidate(self):
        from concurrent.futures import Future

        with tempfile.TemporaryDirectory() as d:
            loop, audio = self.make(d)
            audio.playing = True
            first = Future()
            loop.verify_frames = lambda frames: first
            loop.begin(0.999)
            audio.playing = False
            for _ in range(10):
                loop.feed(QUIET_PCM, 0, False)
            for _ in range(2):
                loop.feed(QUIET_PCM, 0.999, True)
            first.set_result("Unrelated words.")
            loop.tick()
            self.assertTrue(loop.candidate is None)
            audio.resume.assert_called_once()

    def test_moderate_playback_scores_do_not_pause_but_strong_pair_does(self):
        with tempfile.TemporaryDirectory() as d:
            loop, audio = self.make(d)
            audio.playing = True
            for _ in range(4):
                loop.feed(SPEECH_PCM, 0.98, True)
            audio.pause.assert_not_called()
            self.assertIsNone(loop.candidate)
            loop.feed(SPEECH_PCM, 0.992, True)
            audio.pause.assert_not_called()
            loop.feed(SPEECH_PCM, 0.992, True)
            audio.pause.assert_called_once()

    def test_confirmation_retry_uses_configured_playback_threshold(self):
        with tempfile.TemporaryDirectory() as d:
            loop, audio = self.make(d)
            audio.playing = True
            loop.gate.barge_threshold = 0.998
            audio.play_path = Path(d) / "tmp/source.wav"
            audio.play_id = "source"
            audio.playback_position_seconds = 5
            audio.playback_duration_seconds = 40
            loop.begin(0.997)
            self.assertFalse(loop.verification_context(loop.candidate)["wake_confirmation"])
            loop.candidate["score"] = 0.999
            self.assertTrue(loop.verification_context(loop.candidate)["wake_confirmation"])

    def test_barge_verification_includes_post_trigger_context_after_immediate_pause(self):
        from concurrent.futures import Future

        with tempfile.TemporaryDirectory() as d:
            loop, audio = self.make(d)
            loop.state = "speaking"
            audio.playing = True
            loop.preroll.append(b"before")
            captures = []
            loop.verify_frames = lambda frames: captures.append(list(frames)) or Future()
            loop.begin(0.999)
            audio.pause.assert_called_once()
            self.assertEqual(len(captures), 0, "the trigger can precede the end of the wake phrase")
            for _ in range(7):
                loop.feed(b"after", 0, True)
            self.assertEqual(len(captures), 0)
            loop.feed(b"last", 0, True)
            self.assertEqual(captures, [[b"before"] + [b"after"] * 7 + [b"last"]])
            self.assertNotEqual(loop.state, "listening")

    def test_current_spoken_text_cannot_confirm_a_wake_and_resumes_provisional_pause(self):
        from concurrent.futures import Future

        with tempfile.TemporaryDirectory() as d:
            loop, audio = self.make(d)
            loop.state = "speaking"
            audio.playing = True
            loop.spoken_text = "Ted, there are three orders today."
            loop.begin(0.999)
            loop.verify_future = Future()
            loop.verify_future.set_result(dict(text="Hey Ted, there are three orders today.",
                                              spoken_text="Ted, there are three orders today.",
                                              echo_method="audio_slice"))
            loop.tick()
            self.assertEqual(loop.state, "speaking")
            audio.resume.assert_called_once()
            self.assertIsNone(loop.candidate)
            self.assertIsNone(loop.request)

    def test_external_stop_matching_a_future_phrase_is_not_current_playback_echo(self):
        from concurrent.futures import Future

        with tempfile.TemporaryDirectory() as d:
            loop, audio = self.make(d)
            loop.state = "speaking"
            audio.playing = True
            loop.spoken_text = "Opening words. " * 30 + "Hey Ted and Ted stop are quoted later."
            loop.begin(0.999)
            loop.verify_future = Future()
            loop.verify_future.set_result(dict(text="Hey Ted, stop.",
                                              spoken_text="Opening words. Opening words.",
                                              echo_method="audio_slice"))
            loop.tick()
            self.assertEqual(loop.state, "listening")
            audio.resume.assert_not_called()

    def test_vocabulary_spelling_change_cannot_erase_an_unprompted_source_echo_match(self):
        from concurrent.futures import Future

        with tempfile.TemporaryDirectory() as d:
            loop, audio = self.make(d)
            loop.state = "speaking"
            audio.playing = True
            loop.begin(0.999)
            loop.verify_future = Future()
            loop.verify_future.set_result(dict(text="Ted, stop.", initial_text="Third storm.",
                                              spoken_text="Third storm.", confirmation_retry=True,
                                              echo_method="audio_slice"))
            loop.tick()
            self.assertEqual(loop.state, "speaking")
            audio.resume.assert_called_once()

    def test_late_microphone_window_after_pause_cannot_be_vetoed_by_old_source_audio(self):
        from concurrent.futures import ThreadPoolExecutor

        class Verifier:
            def transcribe(self, path):
                return "Hey Ted, stop."

            def transcribe_segment(self, *args):
                raise AssertionError("source audio does not overlap the late microphone window")

        with tempfile.TemporaryDirectory() as d:
            loop, audio = self.make(d)
            source = Path(d) / "tmp/source.wav"
            source.write_bytes(b"old source audio")
            audio.playing = True
            audio.play_path = source
            audio.play_id = "original"
            audio.playback_position_seconds = 5
            audio.playback_duration_seconds = 40
            loop.spoken_text = "Hey Ted, stop."
            loop.preroll.extend([b"before"] * 30)
            loop.begin(0.999)
            loop.candidate["capture_ends_monotonic"] = 104
            audio.last_stop = dict(stop_id=loop.candidate["trigger_id"], play_id="original",
                                   position_seconds=5, stopped_monotonic=100)
            context = loop.verification_context(loop.candidate)
            self.assertTrue(context["source_silent"])
            self.assertEqual(context["seconds"], 0)
            self.assertEqual(context["fallback_text"], "")
            loop.verifier = Verifier()
            with ThreadPoolExecutor(max_workers=1) as worker:
                loop.verify_executor = worker
                result = loop.verify_frames([b"\x00" * 2560], context).result(timeout=2)
            self.assertEqual(result["text"], "Hey Ted, stop.")
            self.assertEqual(result["spoken_text"], "")
            self.assertEqual(result["echo_method"], "playback_silent")

    def test_verification_uses_matching_native_pause_cursor_and_original_playback_id(self):
        with tempfile.TemporaryDirectory() as d:
            loop, audio = self.make(d)
            source = Path(d) / "tmp/source.wav"
            source.touch()
            audio.playing = True
            audio.play_path = source
            audio.play_id = "original"
            audio.playback_position_seconds = 4.8
            audio.playback_duration_seconds = 40
            loop.preroll.extend([b"frame"] * 30)
            loop.begin(0.999)
            audio.last_stop = dict(stop_id=loop.candidate["trigger_id"], play_id="original",
                                   position_seconds=5.0, duration_seconds=40)
            context = loop.verification_context(loop.candidate)
            self.assertEqual(context["path"], source)
            self.assertTrue(context["wake_confirmation"])
            self.assertAlmostEqual(context["start"], 2.3)
            self.assertAlmostEqual(context["seconds"], 2.7)
            audio.last_stop["play_id"] = "replacement"
            context = loop.verification_context(loop.candidate)
            self.assertAlmostEqual(context["start"], 2.1)

    def test_source_slice_is_verified_in_worker_and_private_copy_is_deleted(self):
        from concurrent.futures import ThreadPoolExecutor

        class Verifier:
            def transcribe(self, path):
                return "Hey Ted, stop."

            def transcribe_segment(self, path, start, seconds):
                self.source = Path(path)
                self.bounds = (start, seconds)
                if self.source.read_bytes() != b"original audio":
                    raise AssertionError("wrong source playback")
                return "The opening words are playing now."

        with tempfile.TemporaryDirectory() as d:
            loop, audio = self.make(d)
            source = Path(d) / "tmp/source.wav"
            source.write_bytes(b"original audio")
            loop.verifier = Verifier()
            with ThreadPoolExecutor(max_workers=1) as worker:
                loop.verify_executor = worker
                result = loop.verify_frames([b"\x00" * 2560],
                                            dict(path=source, start=2.3, seconds=2.7,
                                                 fallback_text="future Ted stop")).result(timeout=2)
            self.assertEqual(result["text"], "Hey Ted, stop.")
            self.assertEqual(result["spoken_text"], "The opening words are playing now.")
            self.assertEqual(loop.verifier.bounds, (2.3, 2.7))
            self.assertFalse(loop.verifier.source.exists())
            self.assertTrue(source.exists())

    def test_private_wake_diagnostics_require_both_markers_and_are_private_and_bounded(self):
        import json

        with tempfile.TemporaryDirectory() as d:
            loop, audio = self.make(d)
            loop.debug = True
            capture = Path(d) / "tmp/capture.wav"
            capture.write_bytes(b"private microphone PCM")
            result = dict(text="Actual recognition here", spoken_text="Current source words", echo_method="audio_slice")
            (Path(d) / "diagnostics-enabled").touch()
            self.assertIsNone(loop.record_verification(capture, result))
            (Path(d) / "diagnostic-wake-capture").touch()
            for _ in range(7):
                metadata = loop.record_verification(capture, result)
            records = list((Path(d) / "diagnostics/verification").glob("*.json"))
            self.assertEqual(len(records), 5)
            self.assertEqual(len(list((Path(d) / "diagnostics/verification").glob("*.wav"))), 5)
            row = json.loads(metadata.read_text())
            wav = Path(row["capture_wav"])
            self.assertEqual(row["transcript"], "Actual recognition here")
            self.assertEqual(wav.read_bytes(), b"private microphone PCM")
            self.assertEqual(metadata.stat().st_mode & 0o777, 0o600)
            self.assertEqual(wav.stat().st_mode & 0o777, 0o600)
            loop.debug = False
            self.assertIsNone(loop.record_verification(capture, result))

    def test_strong_playback_candidate_can_retry_whisper_with_wake_vocabulary(self):
        from concurrent.futures import ThreadPoolExecutor

        class Verifier:
            retries = 0
            text = "Third storm."

            def transcribe(self, path):
                return self.text

            def confirm_wake(self, path):
                self.retries += 1
                return "Ted, stop."

            def transcribe_segment(self, path, start, seconds):
                return "The microphone keeps listening."

        with tempfile.TemporaryDirectory() as d:
            loop, audio = self.make(d)
            source = Path(d) / "tmp/source.wav"
            source.write_bytes(b"source audio")
            loop.verifier = Verifier()
            context = dict(path=source, start=2.3, seconds=2.7, fallback_text="", wake_confirmation=True)
            with ThreadPoolExecutor(max_workers=1) as worker:
                loop.verify_executor = worker
                confirmed = loop.verify_frames([b"\x00" * 2560], context).result(timeout=2)
                context["wake_confirmation"] = False
                unchanged = loop.verify_frames([b"\x00" * 2560], context).result(timeout=2)
                loop.verifier.text = "Fed, stop."
                context["wake_confirmation"] = True
                fed_confirmed = loop.verify_frames([b"\x00" * 2560], context).result(timeout=2)
                context["wake_confirmation"] = False
                fed_unchanged = loop.verify_frames([b"\x00" * 2560], context).result(timeout=2)
                loop.verifier.text = "Th head, stop."
                context["wake_confirmation"] = True
                room_confirmed = loop.verify_frames([b"\x00" * 2560], context).result(timeout=2)
                context["wake_confirmation"] = False
                room_unchanged = loop.verify_frames([b"\x00" * 2560], context).result(timeout=2)
            self.assertEqual(confirmed["text"], "Ted, stop.")
            self.assertEqual(confirmed["initial_text"], "Third storm.")
            self.assertEqual(unchanged["text"], "Third storm.")
            self.assertEqual(fed_confirmed["text"], "Ted, stop.")
            self.assertEqual(fed_confirmed["initial_text"], "Fed, stop.")
            self.assertEqual(fed_unchanged["text"], "Fed, stop.")
            self.assertEqual(room_confirmed["text"], "Ted, stop.")
            self.assertEqual(room_confirmed["initial_text"], "Th head, stop.")
            self.assertEqual(room_unchanged["text"], "Th head, stop.")
            self.assertEqual(loop.verifier.retries, 3)

    def test_non_speech_and_unrelated_words_cannot_be_prompted_into_a_wake(self):
        from concurrent.futures import ThreadPoolExecutor

        class Verifier:
            text = ""
            retries = 0

            def transcribe(self, path):
                return self.text

            def confirm_wake(self, path):
                self.retries += 1
                return "Hey Ted, stop."

            def transcribe_segment(self, path, start, seconds):
                return "The room should remain quiet."

        with tempfile.TemporaryDirectory() as d:
            loop, audio = self.make(d)
            source = Path(d) / "tmp/source.wav"
            source.write_bytes(b"source audio")
            loop.verifier = Verifier()
            context = dict(path=source, start=2.3, seconds=2.7, fallback_text="", wake_confirmation=True)
            with ThreadPoolExecutor(max_workers=1) as worker:
                loop.verify_executor = worker
                for text in ["(eerie music)", "", "you", "the storm"]:
                    loop.verifier.text = text
                    result = loop.verify_frames([b"\x00" * 2560], context).result(timeout=2)
                    self.assertEqual(result["text"], text)
            self.assertEqual(loop.verifier.retries, 0)

    def test_new_strong_wake_while_verification_is_pending_gets_one_bounded_recheck(self):
        from concurrent.futures import Future

        with tempfile.TemporaryDirectory() as d:
            loop, audio = self.make(d)
            loop.state = "speaking"
            audio.playing = True
            futures, captures = [], []

            def verify(frames):
                captures.append(list(frames))
                future = Future()
                futures.append(future)
                return future

            loop.verify_frames = verify
            loop.begin(0.999)
            audio.playing = False
            for _ in range(10):
                loop.feed(b"old", 0, False)
            for _ in range(2):
                loop.feed(b"new wake", 0.997, True)
            futures[0].set_result("Unrelated old words.")
            loop.tick()
            self.assertIsNotNone(loop.candidate)
            audio.resume.assert_not_called()
            self.assertEqual(len(futures), 1)
            for _ in range(8):
                loop.feed(b"new request", 0, True)
            self.assertEqual(len(futures), 2)
            self.assertIn(b"new wake", captures[1])
            self.assertEqual(captures[1][-8:], [b"new request"] * 8)
            # A third strong burst cannot create unbounded verification work.
            for _ in range(2):
                loop.feed(b"reset", 0, False)
            for _ in range(2):
                loop.feed(b"third wake", 0.999, True)
            futures[1].set_result("Still unrelated words.")
            loop.tick()
            self.assertEqual(len(futures), 2)
            self.assertIsNone(loop.candidate)
            audio.resume.assert_called_once()
            loop.bridge.deliver.assert_not_called()

    def test_provisional_pause_does_not_lower_late_wake_threshold_to_idle_threshold(self):
        from concurrent.futures import Future

        with tempfile.TemporaryDirectory() as d:
            loop, audio = self.make(d)
            loop.state = "speaking"
            audio.playing = True
            first = Future()
            captures = []
            loop.verify_frames = lambda frames: captures.append(list(frames)) or first
            loop.begin(0.999)
            audio.playing = False
            for _ in range(10):
                loop.feed(b"wait", 0, False)
            for _ in range(2):
                loop.feed(SPEECH_PCM, 0.98, True)
            first.set_result("Unrelated old words.")
            loop.tick()
            self.assertEqual(len(captures), 1)
            self.assertIsNone(loop.candidate)
            audio.resume.assert_called_once()

    def test_vad_silence_cannot_reset_a_continuously_high_model_score_for_recheck(self):
        from concurrent.futures import Future

        with tempfile.TemporaryDirectory() as d:
            loop, audio = self.make(d)
            audio.playing = True
            first = Future()
            loop.verify_frames = lambda frames: first
            loop.begin(0.999)
            audio.playing = False
            for _ in range(10):
                loop.feed(b"silent saturated score", 0.999, False)
            for _ in range(2):
                loop.feed(b"new voice saturated score", 0.999, True)
            first.set_result("Unrelated words.")
            loop.tick()
            self.assertIsNone(loop.candidate)
            audio.resume.assert_called_once()

    def test_verification_debug_reports_submitted_audio_not_later_buffered_audio(self):
        from concurrent.futures import Future

        with tempfile.TemporaryDirectory() as d:
            loop, audio = self.make(d)
            audio.playing = True
            loop.debug = True
            events = []
            loop.emit = lambda event, **fields: events.append(dict(event=event, **fields))
            first = Future()
            loop.verify_frames = lambda frames: first
            loop.preroll.extend([b"before"] * 30)
            loop.begin(0.999)
            audio.playing = False
            for _ in range(8):
                loop.feed(b"submitted", 0, False)
            for _ in range(20):
                loop.feed(b"buffered during inference", 0, False)
            first.set_result("Hey Ted, stop.")
            loop.tick()
            debug = next(row for row in events if row["event"] == "wake_verification_debug")
            self.assertEqual(debug["audio_seconds"], 3.04)
            self.assertIn("submitted_monotonic", debug)

    def test_bare_stop_keeps_listening_until_a_followup_request(self):
        with tempfile.TemporaryDirectory() as d:
            loop, audio = self.make(d)
            loop.accept_transcript("Ted, stop.")
            self.assertEqual(loop.state, "listening")
            self.assertFalse(loop.pause.paused)
            loop.accept_transcript("What is open today?")
            loop.bridge.deliver.assert_called_once_with("What is open today?")

    def test_confirmed_ambiguous_stop_prefix_is_removed_before_routing_followup(self):
        from concurrent.futures import Future

        from routing import asks_for_action

        for prefix in ["Fed, stop.", "Third storm.", "Th head, stop."]:
            with self.subTest(prefix=prefix), tempfile.TemporaryDirectory() as d:
                loop, audio = self.make(d)
                audio.playing = True
                loop.begin(0.999)
                loop.verify_future = Future()
                loop.verify_future.set_result(dict(text="Ted, stop.", initial_text=prefix,
                                                  confirmation_retry=True, spoken_text="Current reply words.",
                                                  echo_method="audio_slice"))
                loop.tick()
                full = prefix + " Reply exactly, the follow up was handled."
                self.assertTrue(asks_for_action(full), "the unstripped prefix would incorrectly queue an action")
                loop.accept_transcript(full)
                loop.bridge.deliver.assert_called_once_with("Reply exactly, the follow up was handled.")
                self.assertFalse(asks_for_action(loop.bridge.deliver.call_args.args[0]))

    def test_confirmed_ambiguous_prefix_alone_rearms_followup_without_submission(self):
        from concurrent.futures import Future

        for prefix in ["Fed, stop.", "Third storm.", "Th head, stop."]:
            with self.subTest(prefix=prefix), tempfile.TemporaryDirectory() as d:
                loop, audio = self.make(d)
                audio.playing = True
                loop.begin(0.999)
                loop.verify_future = Future()
                loop.verify_future.set_result(dict(text="Ted, stop.", initial_text=prefix,
                                                  confirmation_retry=True, spoken_text="Current reply words.",
                                                  echo_method="audio_slice"))
                loop.tick()
                loop.accept_transcript(prefix)
                self.assertEqual(loop.state, "listening")
                self.assertFalse(loop.pause.paused)
                loop.bridge.deliver.assert_not_called()
                loop.accept_transcript("What is open today?")
                loop.bridge.deliver.assert_called_once_with("What is open today?")

    def test_unconfirmed_ambiguous_prefix_is_not_a_global_alias(self):
        for prefix in ["Fed, stop.", "Third storm.", "Th head, stop."]:
            with self.subTest(prefix=prefix), tempfile.TemporaryDirectory() as d:
                loop, audio = self.make(d)
                loop.accept_transcript(prefix)
                loop.bridge.deliver.assert_not_called()
                self.assertEqual(loop.state, "idle")

    def test_generic_wake_does_not_grant_ambiguous_stop_prefix_rewriting(self):
        with tempfile.TemporaryDirectory() as d:
            loop, audio = self.make(d)
            loop.begin_confirmed(0.999, [], 0)
            text = "Fed, stop. Reply exactly, the follow up was handled."
            loop.accept_transcript(text)
            loop.bridge.deliver.assert_called_once_with(text)

    def test_diagnostic_fixture_is_opt_in_and_cannot_play_outside_tmp(self):
        import json

        with tempfile.TemporaryDirectory() as d:
            loop, audio = self.make(d)
            home = Path(d)
            (home / "diagnostics").mkdir()
            outside = home / "outside.wav"
            outside.touch()
            request = home / "diagnostics/trial.request.json"
            request.write_text(json.dumps(dict(trial_id="trial", path=str(outside), text="test")))
            loop.tick()
            self.assertEqual(loop.state, "idle")
            (home / "diagnostics-enabled").touch()
            loop.tick()
            self.assertEqual(loop.state, "idle")
            audio.play.assert_not_called()
            fixture = home / "tmp/fixture.wav"
            fixture.touch()
            request.write_text(json.dumps(dict(trial_id="trial", path=str(fixture), text="test")))
            loop.tick()
            self.assertEqual(loop.state, "speaking")
            self.assertEqual(loop.spoken_text, "test")
            audio.play.assert_called_once_with(fixture.resolve())

    def test_bare_stop_scan_interrupts_without_sending_stop_to_ted(self):
        from concurrent.futures import Future

        with tempfile.TemporaryDirectory() as d:
            loop, audio = self.make(d)
            events = []
            loop.emit = lambda event, **fields: events.append(dict(event=event, **fields))
            loop.state = "speaking"
            audio.playing = True
            loop.stop_scan = dict(preroll=[], extra=[], spoken_text="Three orders today.",
                                  started=0, started_at=0, generation=loop.generation)
            loop.stop_scan_future = Future()
            loop.stop_scan_future.set_result("Ted, stop.")
            loop.tick()
            self.assertEqual(loop.state, "listening")
            loop.bridge.deliver.assert_not_called()
            self.assertTrue(any(e.get("source") == "whisper_stop_scan" for e in events))

    def test_confirmed_wake_keeps_a_followup_without_repeating_wake_words(self):
        with tempfile.TemporaryDirectory() as d:
            loop, audio = self.make(d)
            loop.begin_confirmed(0.999, [], 0)
            loop.accept_transcript("How many orders today?")
            self.assertEqual(loop.state, "waiting")
            loop.bridge.deliver.assert_called_once_with("How many orders today?")

    def test_stale_stop_scan_cannot_interrupt_a_later_reply(self):
        from concurrent.futures import Future

        with tempfile.TemporaryDirectory() as d:
            loop, audio = self.make(d)
            loop.state = "speaking"
            audio.playing = True
            loop.generation = 2
            loop.stop_scan = dict(preroll=[], extra=[], spoken_text="Old reply.",
                                  started=0, started_at=0, generation=1)
            loop.stop_scan_future = Future()
            loop.stop_scan_future.set_result("Ted, stop.")
            loop.tick()
            self.assertEqual(loop.state, "speaking")
            audio.stop.assert_not_called()

    def test_bare_stop_scan_captures_end_of_phrase_before_verification(self):
        with tempfile.TemporaryDirectory() as d:
            loop, audio = self.make(d)
            loop.state = "speaking"
            audio.playing = True
            loop.verify_frames = Mock()
            for _ in range(12):
                loop.feed(b"\x00" * 2560, 0, False)
            for _ in range(8):
                loop.feed(b"\x01" * 2560, 0, True)
            self.assertEqual(loop.verify_frames.call_count, 0)
            for _ in range(3):
                loop.feed(b"\x00" * 2560, 0, False)
            loop.verify_frames.assert_called_once()

    def test_a_second_confirmed_interrupt_cannot_leave_audio_paused_during_cooldown(self):
        import time

        with tempfile.TemporaryDirectory() as d:
            loop, audio = self.make(d)
            loop.last_trigger = time.monotonic()
            loop.state = "speaking"
            loop.begin_confirmed(0.999, [], time.monotonic(), dict(barge_in=True, trigger_id="second", trigger_at=0))
            self.assertEqual(loop.state, "listening")

    def test_closing_loop_cancels_queued_verification_and_deletes_private_wav(self):
        import threading
        from concurrent.futures import ThreadPoolExecutor

        with tempfile.TemporaryDirectory() as d:
            loop, audio = self.make(d)
            release = threading.Event()
            worker = ThreadPoolExecutor(max_workers=1)
            blocker = worker.submit(release.wait)
            loop.verify_executor = worker
            try:
                loop.verify_future = loop.verify_frames([b"\x00" * 2560])
                self.assertEqual(len(list((Path(d) / "tmp").glob("verify-*.wav"))), 1)
                loop.close()
                self.assertTrue(loop.verify_future.cancelled())
                self.assertEqual(list((Path(d) / "tmp").glob("verify-*.wav")), [])
            finally:
                release.set()
                blocker.result(timeout=2)
                worker.shutdown()

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

    def test_failed_reply_is_saved_and_speaks_a_local_notice_without_posting(self):
        from session import Offline

        with tempfile.TemporaryDirectory() as d:
            loop, audio = self.make(d)
            loop.accept_transcript("Hey Ted, hello")
            loop.request = {"session_id": "test", "text": "hello"}
            loop.bridge.poll.side_effect = Offline("account 2 Max login unavailable")
            loop.tick()
            self.assertEqual(loop.state, "rendering")
            pending = list((Path(d) / "pending").glob("*.json"))
            self.assertEqual(len(pending), 1)
            self.assertIn("hello", pending[0].read_text())
            self.assertEqual(loop.executor.submit.call_args.args[0].__name__, "render_local")
            loop.bridge.transport.call.assert_not_called()

    def test_completed_speech_records_the_actual_renderer(self):
        from concurrent.futures import Future

        with tempfile.TemporaryDirectory() as d:
            loop, audio = self.make(d)
            events = []
            loop.emit = lambda event, **fields: events.append((event, fields))
            loop.state = "rendering"
            loop.future = Future()
            loop.future.set_result(Path(d) / "approved-brian.mp3")
            loop.future_kind = "speech"
            loop.tick()
            self.assertIn(("speech_rendered", {"renderer": "elevenlabs"}), events)

    def test_delivery_failure_is_local_and_cannot_post_private_speech(self):
        from session import Offline

        with tempfile.TemporaryDirectory() as d:
            loop, audio = self.make(d)
            loop.bridge.deliver.side_effect = Offline("previous request in progress")
            loop.accept_transcript("Hey Ted, private request")
            loop.bridge.transport.call.assert_not_called()
            self.assertEqual(loop.executor.submit.call_args.args[0].__name__, "render_local")


if __name__ == "__main__":
    unittest.main()
