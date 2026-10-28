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

    def test_reused_pid_is_rejected_before_inbox_delivery(self):
        import socket
        from unittest.mock import Mock

        with tempfile.TemporaryDirectory() as d:
            socket_path = str(Path(d) / "inbox.sock")
            with socket.socket(socket.AF_UNIX) as inbox:
                inbox.bind(socket_path)
                bridge = SessionBridge.__new__(SessionBridge)
                bridge.transport = Mock()
                bridge.transport.registry.return_value = {
                    "procStart": "old process",
                    "messagingSocketPath": socket_path,
                }
                with (
                    patch.object(bridge, "current_id", return_value="a"),
                    patch.object(
                        bridge,
                        "agents",
                        return_value=[
                            {
                                "sessionId": "a",
                                "pid": 123,
                                "cwd": str(Path.home() / "Claude Code - Fictora"),
                            }
                        ],
                    ),
                    patch(
                        "session.subprocess.run",
                        return_value=Mock(returncode=0, stdout="new process\n"),
                    ),
                ):
                    with self.assertRaisesRegex(Offline, "process identity"):
                        bridge.live()
                bridge.transport.send.assert_not_called()

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

    def test_cursor_speaks_only_final_message_and_ignores_meta_hook_context(self):
        from core import ReplyCursor

        cursor = ReplyCursor("voice:abc")
        cursor.feed(dict(type="user", message=dict(content="[voice] voice:abc hello")))
        cursor.feed(dict(type="user", isMeta=True, message=dict(content="injected voice card")))
        cursor.feed(dict(type="assistant", message=dict(id="progress", content="I will check.")))
        final = dict(
            type="assistant",
            message=dict(id="final", content="All checks pass.", stop_reason="end_turn"),
        )
        self.assertEqual(cursor.feed(final), "All checks pass.")
        self.assertIsNone(cursor.feed(final))

    def test_cursor_requires_exact_marker_token(self):
        from core import ReplyCursor

        cursor = ReplyCursor("voice:abc")
        cursor.feed(dict(type="user", message=dict(content="[voice] voice:abcdef hello")))
        self.assertFalse(cursor.seen)

    def test_corrupt_json_rows_are_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t"
            p.write_text("[]\nnull\n{}\n")
            self.assertEqual(JsonlTail(p, 0).read(), [{}])

    def test_meta_notice_with_marker_cannot_acknowledge_delivery(self):
        import json

        from core import ReplyCursor

        with tempfile.TemporaryDirectory() as d:
            bridge = SessionBridge.__new__(SessionBridge)
            bridge.transcripts = Path(d)
            path = bridge.transcripts / "main.jsonl"
            meta = dict(type="user", isMeta=True, message=dict(content="held voice:abc"))
            path.write_text(json.dumps(meta) + "\n")
            self.assertFalse(bridge.acknowledged("main", "voice:abc"))
            cursor = ReplyCursor("voice:abc")
            cursor.feed(meta)
            self.assertFalse(cursor.seen)
            with path.open("a") as stream:
                stream.write(
                    json.dumps(dict(type="user", message=dict(content="[voice] voice:abc"))) + "\n"
                )
            self.assertTrue(bridge.acknowledged("main", "voice:abc"))


if __name__ == "__main__":
    unittest.main()
