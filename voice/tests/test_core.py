import tempfile
import unittest
from pathlib import Path

from core import (
    Endpoint,
    Pause,
    PlaybackGate,
    ReplyCursor,
    choose_devices,
    speech_text,
    wake_command,
)


class CoreTests(unittest.TestCase):
    def test_silence_exactly_1200ms_and_no_speech_timeout(self):
        e = Endpoint()
        self.assertFalse(e.feed(True, 0.3))
        self.assertFalse(e.feed(False, 1.19))
        self.assertTrue(e.feed(False, 0.01))
        self.assertTrue(Endpoint().feed(False, 5))

    def test_continuous_speech_has_thirty_second_cap(self):
        self.assertTrue(Endpoint().feed(True, 30))

    def test_cleanup_limits_words_and_removes_code_and_links(self):
        s = speech_text(
            "# Done\n[open](https://example.com) **now**.\n```sh\nrm -rf /\n```\nhttps://example.com\n"
            + ("word " * 100)
        )
        self.assertNotIn("https", s)
        self.assertNotIn("rm -rf", s)
        self.assertLessEqual(len(s.split()), 60)
        self.assertTrue(s.endswith("Details are on your phone."))

    def test_own_playback_never_contains_either_trigger_phrase(self):
        s = speech_text("Say hey Ted, or say Ted, stop listening.")
        self.assertNotIn("hey ted", s.lower())
        self.assertNotIn("ted, stop listening", s.lower())

    def test_wake_verification_and_pause(self):
        self.assertEqual(wake_command("Hey Ted, what's open today?"), "what's open today?")
        self.assertIsNone(wake_command("hey dad, what time is it"))
        self.assertEqual(wake_command("Ted, stop listening."), "__pause__")
        self.assertEqual(wake_command("hey Ted stop listening"), "__pause__")

    def test_only_reply_after_exact_request_and_final_text(self):
        c = ReplyCursor("voice:abc")

        def a(text, **kw):
            return dict(
                type="assistant", message=dict(content=[dict(type="text", text=text)], **kw)
            )

        self.assertIsNone(c.feed(a("unrelated")))
        self.assertIsNone(
            c.feed(dict(type="user", message=dict(content="[voice] voice:abc hello")))
        )
        self.assertIsNone(
            c.feed(
                dict(
                    type="assistant",
                    message=dict(content=[dict(type="thinking", thinking="hidden")]),
                )
            )
        )
        self.assertIsNone(c.feed(a("Working.", stop_reason="tool_use")))
        self.assertIsNone(
            c.feed(dict(type="user", message=dict(content=[dict(type="tool_result", content="x")])))
        )
        self.assertEqual(
            c.feed(a("Here is your answer.", stop_reason="end_turn")), "Here is your answer."
        )

    def test_new_user_cancels_and_sidechain_is_ignored(self):
        c = ReplyCursor("voice:x")
        c.feed(dict(type="user", message=dict(content="[voice] voice:x hello")))
        c.feed(
            dict(
                type="assistant",
                isSidechain=True,
                message=dict(content=[dict(type="text", text="wrong")], stop_reason="end_turn"),
            )
        )
        c.feed(dict(type="user", message=dict(content="another question")))
        self.assertTrue(c.cancelled)
        self.assertIsNone(c.feed(dict(type="assistant", message=dict(content="wrong"))))

    def test_echo_gate_requires_clean_audio_and_stricter_barge_score(self):
        g = PlaybackGate(0.7, 0.95, 2)
        self.assertFalse(g.accept(0.99, True, False))
        self.assertFalse(g.accept(0.8, True, True))
        self.assertFalse(g.accept(0.99, True, True))
        self.assertTrue(g.accept(0.99, True, True))

    def test_pause_survives_new_instance(self):
        with tempfile.TemporaryDirectory() as d:
            Pause(Path(d)).stop()
            self.assertTrue(Pause(Path(d)).paused)
            Pause(Path(d)).resume()
            self.assertFalse(Pause(Path(d)).paused)

    def test_device_input_and_output_independently_prefer_jabra(self):
        d = [
            dict(name="default", input=True, output=True, id=1),
            dict(name="Jabra Speak2 55", input=True, output=False, id=2),
        ]
        self.assertEqual(choose_devices(d, 1, 1), (2, 1))


if __name__ == "__main__":
    unittest.main()
