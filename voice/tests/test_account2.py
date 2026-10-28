import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch


class Account2Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.config = self.home / ".claude-acct2"
        self.config.mkdir()
        self.context_roots = [
            self.home / part for part in ("ted-ops/ted-state", "biz", "kres", "ventures")
        ]
        for root in self.context_roots:
            root.mkdir(parents=True)
        card = self.home / "voice-card.md"
        card.write_text("TED VOICE CARD: speak like a loyal bear.\n")
        hook = self.home / "voice-hook.sh"
        hook.write_text('cat "' + str(card) + '"\n')
        (self.config / "settings.json").write_text(
            json.dumps(
                {
                    "hooks": {
                        "UserPromptSubmit": [{"hooks": [{"type": "command", "command": str(hook)}]}]
                    }
                }
            )
        )
        self.events = []
        self.usage = {"extra_usage": {"is_enabled": False}}
        self.binary = self.home / "claude"
        self.binary.write_text(
            "#!"
            + sys.executable
            + "\n"
            + """
import json, os, pathlib, sys
root = pathlib.Path(__file__).parent
args = sys.argv[1:]
with (root / "calls.jsonl").open("a") as log:
    log.write(json.dumps({"args": args, "cwd": str(pathlib.Path.cwd()), "env": {k:v for k,v in os.environ.items() if k.startswith(("ANTHROPIC_", "CLAUDE_"))}}) + "\\n")
if args[:2] == ["auth", "status"]:
    result = {"loggedIn": True, "authMethod": "claude.ai", "apiProvider": "firstParty", "subscriptionType": "max", "configDirectory": os.environ["CLAUDE_CONFIG_DIR"]}
    if (root / "bad_auth").exists(): result["authMethod"] = "api_key"
    if (root / "malformed_auth").exists(): result = []
    print(json.dumps(result))
    if (root / "fail_before_child").exists():
        pathlib.Path(__file__).unlink()
        (root / "fail_before_child").unlink()
    sys.exit(0)
if (root / "exit_before_session").exists(): sys.exit(1)
sid = args[args.index("--resume") + 1] if "--resume" in args else args[args.index("--session-id") + 1]
request = json.loads(sys.stdin.read())
if (root / "extra_rows").exists(): print("[]")
print(json.dumps({"type": "user", "session_id": sid, "message": request["message"]}))
if (root / "wrong_session").exists(): sid = "00000000-0000-0000-0000-000000000000"
error = (root / "reply_error").exists()
print(json.dumps({"type": "result", "session_id": sid, "is_error": error, "subtype": "error_during_execution" if error else "success", "result": "PRIVATE ERROR TOKEN" if error else "Jabra voice loop is working."}))
"""
        )
        self.binary.chmod(0o700)

    def bridge(self):
        import importlib.util

        self.assertIsNotNone(
            importlib.util.find_spec("account2"), "Account 2 voice bridge is missing"
        )
        from account2 import Account2Bridge

        usage = patch(
            "account2.subscription_usage", side_effect=lambda directory: self.usage, create=True
        )
        usage.start()
        self.addCleanup(usage.stop)

        with patch("account2.Path.home", return_value=self.home):
            bridge = Account2Bridge(
                self.home,
                lambda event, **fields: self.events.append((event, fields)),
                binary=self.binary,
                config_dir=self.config,
            )
        self.addCleanup(bridge.close)
        return bridge

    def finish(self, bridge, request):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            result = bridge.poll(request)
            if result:
                return result
            time.sleep(0.01)
        self.fail("CLI bridge did not complete")

    def calls(self):
        return [json.loads(row) for row in (self.home / "calls.jsonl").read_text().splitlines()]

    def test_spoken_turn_uses_account2_oauth_with_only_scoped_read_tools(self):
        bridge = self.bridge()
        with patch.dict(
            os.environ,
            {
                "ANTHROPIC_API_KEY": "secret",
                "CLAUDE_CODE_OAUTH_TOKEN": "wrong-account",
                "CLAUDE_CODE_USE_BEDROCK": "1",
                "CLAUDE_SECURESTORAGE_CONFIG_DIR": "wrong-account",
            },
        ):
            request = bridge.deliver("Say the test phrase.")
            self.assertFalse(request["accepted"])
            self.assertEqual(self.finish(bridge, request), "Jabra voice loop is working.")
        calls = self.calls()
        self.assertEqual(len(calls), 2)
        generation = calls[1]
        self.assertEqual(generation["env"]["CLAUDE_CONFIG_DIR"], str(self.config))
        self.assertNotIn("ANTHROPIC_API_KEY", generation["env"])
        self.assertNotIn("CLAUDE_CODE_OAUTH_TOKEN", generation["env"])
        self.assertNotIn("CLAUDE_CODE_USE_BEDROCK", generation["env"])
        self.assertNotIn("CLAUDE_SECURESTORAGE_CONFIG_DIR", generation["env"])
        args = generation["args"]
        self.assertEqual(set(args[args.index("--tools") + 1].split(",")), {"Read", "Grep", "Glob"})
        self.assertIn("--restricted", args)
        self.assertEqual(Path(generation["cwd"]).resolve(), self.context_roots[0].resolve())
        self.assertEqual(
            args[args.index("--add-dir") + 1 : args.index("--add-dir") + 4],
            [str(root) for root in self.context_roots[1:]],
        )
        self.assertEqual(args[args.index("--permission-mode") + 1], "dontAsk")
        prompt = args[args.index("--system-prompt") + 1]
        self.assertIn("TED VOICE CARD: speak like a loyal bear.", prompt)
        self.assertIn("cannot execute actions", prompt)
        self.assertIn("--strict-mcp-config", args)
        self.assertIn("--safe-mode", args)
        self.assertEqual(args[args.index("--permission-prompts") + 1], "none")
        self.assertTrue(request["accepted"])

    def test_missing_voice_card_fails_closed_without_generation(self):
        from session import Offline

        (self.home / "voice-card.md").unlink()
        bridge = self.bridge()
        with self.assertRaisesRegex(Offline, "voice card"):
            self.finish(bridge, bridge.deliver("What is the status?"))
        self.assertEqual(len(self.calls()), 1)

    def test_voice_card_hook_is_read_without_running_it(self):
        hook = self.home / "voice-hook.sh"
        hook.write_text(hook.read_text() + 'touch "' + str(self.home / "hook-executed") + '"\n')
        bridge = self.bridge()
        self.finish(bridge, bridge.deliver("What is the status?"))
        self.assertFalse((self.home / "hook-executed").exists())

    def test_old_unscoped_session_is_not_resumed_with_restored_directories(self):
        previous = "11111111-1111-4111-8111-111111111111"
        (self.home / "claude-voice-session.json").write_text(
            json.dumps(
                {
                    "session_id": previous,
                    "launched": True,
                }
            )
        )
        bridge = self.bridge()
        request = bridge.deliver("What is the status?")
        self.finish(bridge, request)
        self.assertNotEqual(request["session_id"], previous)
        args = self.calls()[-1]["args"]
        self.assertIn("--session-id", args)
        self.assertEqual(args[args.index("--system-prompt-snapshot") + 1], "off")

    def test_restart_resumes_the_same_private_voice_conversation(self):
        first = self.bridge()
        request = first.deliver("First request")
        self.finish(first, request)
        first.close()
        second = self.bridge()
        resumed = second.deliver("Second request")
        self.finish(second, resumed)
        self.assertEqual(resumed["session_id"], request["session_id"])
        args = self.calls()[-1]["args"]
        self.assertEqual(args[args.index("--resume") + 1], request["session_id"])
        self.assertEqual((self.home / "claude-voice-session.json").stat().st_mode & 0o777, 0o600)

    def test_non_max_oauth_authentication_never_starts_generation(self):
        from session import Offline

        (self.home / "bad_auth").touch()
        bridge = self.bridge()
        with self.assertRaisesRegex(Offline, "account 2 Max"):
            self.finish(bridge, bridge.deliver("hello"))
        self.assertEqual(len(self.calls()), 1)

    def test_different_session_result_cannot_be_spoken(self):
        from session import Offline

        (self.home / "wrong_session").touch()
        bridge = self.bridge()
        with self.assertRaisesRegex(Offline, "session"):
            self.finish(bridge, bridge.deliver("hello"))

    def test_cli_error_is_fixed_safe_reason_and_never_retried(self):
        from session import Offline

        (self.home / "reply_error").touch()
        bridge = self.bridge()
        with self.assertRaisesRegex(Offline, "reply failed"):
            self.finish(bridge, bridge.deliver("hello"))
        self.assertEqual(len(self.calls()), 2)
        self.assertNotIn("PRIVATE ERROR TOKEN", json.dumps(self.events))

    def test_malformed_auth_fails_closed_without_generation(self):
        from session import Offline

        (self.home / "malformed_auth").touch()
        bridge = self.bridge()
        with self.assertRaisesRegex(Offline, "account 2 Max"):
            self.finish(bridge, bridge.deliver("hello"))
        self.assertEqual(len(self.calls()), 1)

    def test_unrelated_stream_rows_do_not_crash_capture_loop(self):
        (self.home / "extra_rows").touch()
        bridge = self.bridge()
        self.assertEqual(
            self.finish(bridge, bridge.deliver("hello")), "Jabra voice loop is working."
        )

    def test_failed_first_child_launch_keeps_next_distinct_request_startable(self):
        from session import Offline

        script = self.binary.read_text()
        (self.home / "fail_before_child").touch()
        bridge = self.bridge()
        with self.assertRaises(Offline):
            self.finish(bridge, bridge.deliver("First request"))
        self.assertFalse(
            json.loads((self.home / "claude-voice-session.json").read_text())["launched"]
        )
        self.binary.write_text(script)
        self.binary.chmod(0o700)
        self.finish(bridge, bridge.deliver("Different request"))
        self.assertIn("--session-id", self.calls()[-1]["args"])

    def test_failed_later_child_launch_preserves_existing_conversation(self):
        from session import Offline

        bridge = self.bridge()
        first = bridge.deliver("First request")
        self.finish(bridge, first)
        (self.home / "fail_before_child").touch()
        with self.assertRaises(Offline):
            self.finish(bridge, bridge.deliver("Different request"))
        state = json.loads((self.home / "claude-voice-session.json").read_text())
        self.assertTrue(state["launched"])
        self.assertEqual(state["session_id"], first["session_id"])

    def test_extra_usage_enabled_or_unknown_never_starts_generation(self):
        from session import Offline

        for usage in (
            {"extra_usage": {"is_enabled": True}},
            {},
            {"extra_usage": {"is_enabled": None}},
        ):
            with self.subTest(usage=usage):
                self.usage = usage
                bridge = self.bridge()
                before = len(self.calls()) if (self.home / "calls.jsonl").exists() else 0
                with self.assertRaisesRegex(Offline, "extra usage"):
                    self.finish(bridge, bridge.deliver("hello"))
                self.assertEqual(len(self.calls()), before + 1)

    def test_close_kills_and_reaps_a_child_that_ignores_termination(self):
        import subprocess
        from unittest.mock import Mock

        bridge = self.bridge()
        child = Mock()
        child.poll.return_value = None
        child.wait.side_effect = [subprocess.TimeoutExpired("claude", 2), 0]
        bridge.process = child
        bridge.close()
        child.terminate.assert_called_once()
        child.kill.assert_called_once()
        self.assertEqual(child.wait.call_count, 2)

    def test_first_child_exit_before_session_does_not_poison_future_resume(self):
        from session import Offline

        bridge = self.bridge()
        failure = self.home / "exit_before_session"
        failure.touch()
        request = bridge.deliver("What is the status?")
        with self.assertRaises(Offline):
            request["future"].result(timeout=5)
        state = json.loads((self.home / "claude-voice-session.json").read_text())
        self.assertFalse(state["launched"])
        failure.unlink()
        fresh = bridge.deliver("What is the status now?")
        self.assertEqual(fresh["future"].result(timeout=5), "Jabra voice loop is working.")
        calls = [
            json.loads(line)["args"]
            for line in (self.home / "calls.jsonl").read_text().splitlines()
        ]
        turns = [args for args in calls if "-p" in args]
        self.assertIn("--session-id", turns[-1])
        self.assertNotIn("--resume", turns[-1])


if __name__ == "__main__":
    unittest.main()
