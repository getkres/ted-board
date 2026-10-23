import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from session import JsonlTail, Offline, SessionBridge


class SessionTests(unittest.TestCase):
    def test_partial_line_waits_for_newline(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t"
            p.write_bytes(b"")
            t = JsonlTail(p, 0)
            p.write_bytes(b'{"type":"user"')
            self.assertEqual(t.read(), [])
            with p.open("ab") as f:
                f.write(b"}\n")
            self.assertEqual(t.read(), [{"type": "user"}])

    def test_current_session_never_falls_back_to_another(self):
        b = SessionBridge.__new__(SessionBridge)
        b.current = Path("/unused")
        with (
            patch.object(b, "current_id", return_value="a"),
            patch.object(b, "agents", return_value=[dict(sessionId="b", pid=1)]),
        ):
            with self.assertRaises(Offline):
                b.live()

    def test_permission_blocked_live_session_is_unavailable_without_sending(self):
        from unittest.mock import Mock

        b = SessionBridge.__new__(SessionBridge)
        b.transport = Mock()
        b.transport.registry.return_value = {"waitingFor": "permission prompt"}
        with (
            patch.object(b, "current_id", return_value="a"),
            patch.object(
                b,
                "agents",
                return_value=[
                    dict(sessionId="a", pid=1, cwd=str(Path.home() / "Claude Code - Fictora"))
                ],
            ),
        ):
            with self.assertRaises(Offline):
                b.live()

    def test_rotated_transcript_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t"
            p.write_text("a\n")
            t = JsonlTail(p, 2)
            p.unlink()
            p.write_text("{}\n")
            with self.assertRaises(Offline):
                t.read()

    def test_changed_current_session_cancels_wait(self):
        b = SessionBridge.__new__(SessionBridge)
        with patch.object(b, "current_id", return_value="b"):
            with self.assertRaises(Offline):
                b.assert_current("a")


if __name__ == "__main__":
    unittest.main()
