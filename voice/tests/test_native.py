"""Native output integration test. Opt in with TED_NATIVE_HELPER and TED_VOICE_HOME."""

import os
import time
import unittest
from pathlib import Path

from runtime import Audio


@unittest.skipUnless(os.environ.get("TED_NATIVE_HELPER"), "native helper not selected")
class NativeTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
