import json
import tempfile
import unittest
from concurrent.futures import Future
from pathlib import Path

from session import Offline


class ImmediateExecutor:
    def submit(self, fn, *args, **kwargs):
        result = Future()
        try:
            result.set_result(fn(*args, **kwargs))
        except BaseException as exc:
            result.set_exception(exc)
        return result

    def shutdown(self, **kwargs):
        pass


class MainInbox:
    def __init__(self, transcripts=None):
        self.online = True
        self.sent = []
        self.answer = None
        self.uncertain = False
        self.acks = set()
        self.ack_on_send = False
        self.ack_scans = 0
        self.transcripts = transcripts
        if transcripts:
            transcripts.mkdir(exist_ok=True)
            (transcripts / "main.jsonl").touch()

    def deliver(self, text, marker=None, before_send=None):
        if not self.online:
            raise Offline("main offline")
        request = dict(session_id="main", marker=marker, text=text, accepted=False)
        if before_send:
            before_send(request)
        self.sent.append(request)
        if self.ack_on_send:
            self.acknowledge(marker)
        if self.uncertain:
            from session import DeliveryUncertain

            raise DeliveryUncertain("delivery uncertain")
        return request

    def poll(self, request):
        if not self.online:
            raise Offline("main offline")
        if self.answer or request["marker"] in self.acks:
            request["accepted"] = True
        return self.answer

    def assert_current(self, sid):
        if not self.online:
            raise Offline("main offline")

    def acknowledge(self, marker):
        self.acks.add(marker)
        if self.transcripts:
            with (self.transcripts / "main.jsonl").open("a") as stream:
                stream.write(json.dumps({"type": "user", "message": {"content": marker}}) + "\n")

    def acknowledged(self, sid, marker):
        self.ack_scans += 1
        return marker in self.acks


class ReadOnlyFallback:
    def __init__(self):
        self.sent = []
        self.closed = False

    def deliver(self, text):
        self.sent.append(text)
        return dict(session_id="fallback", accepted=False)

    def poll(self, request):
        request["accepted"] = True
        return "The build is passing."

    def close(self):
        self.closed = True


class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.main = MainInbox(self.home / "transcripts")
        self.fallback = ReadOnlyFallback()
        self.now = 0
        self.events = []

    def bridge(self):
        import importlib.util

        self.assertIsNotNone(importlib.util.find_spec("routing"), "Main inbox routing is missing")
        from routing import RoutedBridge

        bridge = RoutedBridge(
            self.home,
            lambda event, **fields: self.events.append((event, fields)),
            main=self.main,
            fallback=self.fallback,
            clock=lambda: self.now,
            executor=ImmediateExecutor(),
        )
        self.addCleanup(bridge.close)
        return bridge

    def test_main_reply_uses_inbox_and_sanitizes_only_final_text(self):
        bridge = self.bridge()
        self.main.answer = (
            "# Ready\n[dashboard](https://example.com)\n```sh\nprivate command\n```\n"
            + "word " * 100
        )
        request = bridge.deliver("What is the status?")
        result = bridge.poll(request)
        self.assertEqual(len(self.main.sent), 1)
        self.assertEqual(self.fallback.sent, [])
        self.assertNotIn("https", result)
        self.assertNotIn("private command", result)
        self.assertLessEqual(len(result.split()), 60)
        self.assertTrue(result.endswith("Rest is on screen."))
        self.assertTrue(request["accepted"])

    def test_main_unavailable_waits_twenty_seconds_before_read_only_fallback(self):
        self.main.online = False
        bridge = self.bridge()
        request = bridge.deliver("What is the build status?")
        self.assertIsNone(bridge.poll(request))
        self.now = 19.9
        self.assertIsNone(bridge.poll(request))
        self.assertEqual(self.fallback.sent, [])
        self.now = 20
        bridge.poll(request)
        self.assertEqual(bridge.poll(request), "The build is passing.")
        self.assertEqual(self.fallback.sent, ["What is the build status?"])

    def test_unavailable_action_survives_restart_and_delivers_once(self):
        self.main.online = False
        first = self.bridge()
        request = first.deliver("Fix the deployment.")
        self.now = 20
        notice = first.poll(request)
        self.assertIn("queued", notice.lower())
        self.assertEqual(self.fallback.sent, [])
        self.assertEqual((self.home / "main-voice-queue.json").stat().st_mode & 0o777, 0o600)
        first.close()
        self.main.online = True
        second = self.bridge()
        second.tick()
        self.assertEqual(
            json.loads((self.home / "main-voice-queue.json").read_text())[0]["state"], "dispatching"
        )
        self.main.acknowledge(self.main.sent[0]["marker"])
        self.now += 5
        second.tick()
        second.tick()
        self.assertEqual(len(self.main.sent), 1)
        self.assertEqual(self.main.sent[0]["text"], "Fix the deployment.")
        self.assertEqual(
            json.loads((self.home / "main-voice-queue.json").read_text())[0]["state"], "delivered"
        )

    def test_main_recovers_before_deadline_without_fallback(self):
        self.main.online = False
        bridge = self.bridge()
        request = bridge.deliver("What is the build status?")
        self.main.online = True
        self.main.answer = "All checks pass."
        self.now = 5
        self.assertEqual(bridge.poll(request), "All checks pass.")
        self.assertEqual(self.fallback.sent, [])

    def test_busy_main_action_is_never_duplicated_after_fallback_timeout(self):
        bridge = self.bridge()
        request = bridge.deliver("Fix the deployment.")
        self.now = 20
        notice = bridge.poll(request).lower()
        self.assertIn("confirm", notice)
        self.assertNotIn("already has", notice)
        self.assertFalse(request["main_delivered"])
        self.assertEqual(
            json.loads((self.home / "main-voice-queue.json").read_text())[0]["state"], "uncertain"
        )
        self.main.online = False
        bridge.close()
        other = self.bridge()
        self.main.online = True
        other.tick()
        self.assertEqual(len(self.main.sent), 1)

    def test_matching_marker_after_held_timeout_marks_delivered_without_resending(self):
        bridge = self.bridge()
        request = bridge.deliver("Fix the deployment.")
        self.now = 20
        bridge.poll(request)
        self.assertFalse(request["main_delivered"])
        self.main.acknowledge(request["marker"])
        bridge.tick()
        self.assertTrue(request["main_delivered"])
        self.assertEqual(
            json.loads((self.home / "main-voice-queue.json").read_text())[0]["state"], "delivered"
        )
        self.now += 5
        bridge.tick()
        self.assertEqual(len(self.main.sent), 1)
        self.assertTrue(any(name == "voice_action_delivered" for name, fields in self.events))

    def test_acknowledged_busy_action_can_truthfully_say_main_has_it(self):
        self.main.ack_on_send = True
        bridge = self.bridge()
        request = bridge.deliver("Fix the deployment.")
        self.now = 20
        self.assertIn("already has", bridge.poll(request).lower())
        self.assertTrue(request["main_delivered"])

    def test_unchanged_transcript_is_not_fully_rescanned_for_unacknowledged_action(self):
        bridge = self.bridge()
        request = bridge.deliver("Fix the deployment.")
        self.now = 20
        bridge.poll(request)
        bridge.tick()
        scans = self.main.ack_scans
        self.assertEqual(scans, 1)
        self.now += 5
        bridge.tick()
        self.assertEqual(self.main.ack_scans, scans)
        self.main.acknowledge(request["marker"])
        self.now += 5
        bridge.tick()
        self.assertTrue(request["main_delivered"])
        self.assertEqual(self.main.ack_scans, scans + 1)

    def test_restart_reconciles_later_marker_for_uncertain_send_without_resending(self):
        first = self.bridge()
        request = first.deliver("Fix the deployment.")
        self.now = 20
        first.poll(request)
        first.close()
        self.main.acknowledge(request["marker"])
        second = self.bridge()
        second.tick()
        self.assertEqual(
            json.loads((self.home / "main-voice-queue.json").read_text())[0]["state"], "delivered"
        )
        self.assertEqual(len(self.main.sent), 1)

    def test_uncertain_send_is_not_automatically_retried_after_restart(self):
        self.main.uncertain = True
        first = self.bridge()
        request = first.deliver("Deploy the fix.")
        self.now = 20
        self.assertIn("confirm", first.poll(request).lower())
        first.close()
        second = self.bridge()
        second.tick()
        self.assertEqual(len(self.main.sent), 1)

    def test_durable_dispatch_intent_survives_failure_to_record_send_success(self):
        self.main.online = False
        first = self.bridge()
        first.deliver("Deploy the fix.")
        rows = json.loads((self.home / "main-voice-queue.json").read_text())
        rows[0].update(state="dispatching", session_id="main")
        (self.home / "main-voice-queue.json").write_text(json.dumps(rows))
        first.close()
        self.main.online = True
        second = self.bridge()
        second.tick()
        self.assertEqual(self.main.sent, [])
        self.assertEqual(
            json.loads((self.home / "main-voice-queue.json").read_text())[0]["state"], "uncertain"
        )

    def test_mixed_question_and_action_is_queued_conservatively(self):
        self.main.online = False
        bridge = self.bridge()
        request = bridge.deliver("What is broken, and can you fix it?")
        self.now = 20
        self.assertIn("queued", bridge.poll(request).lower())
        self.assertEqual(self.fallback.sent, [])

    def test_informational_fallback_does_not_redeliver_question_later(self):
        self.main.online = False
        bridge = self.bridge()
        request = bridge.deliver("Tell me the build status.")
        self.now = 20
        bridge.poll(request)
        self.assertEqual(bridge.poll(request), "The build is passing.")
        self.main.online = True
        bridge.tick()
        self.assertEqual(self.main.sent, [])

    def test_busy_main_question_falls_back_once_without_late_duplicate_speech(self):
        bridge = self.bridge()
        request = bridge.deliver("What is the build status?")
        self.now = 20
        bridge.poll(request)
        self.main.answer = "Late main reply."
        self.assertEqual(bridge.poll(request), "The build is passing.")
        self.assertIsNone(bridge.poll(request))
        self.assertEqual(len(self.main.sent), 1)

    def test_conversational_reply_requests_reach_fallback(self):
        self.main.online = False
        bridge = self.bridge()
        for text in (
            "Reply exactly, the Jabra voice loop is working.",
            "Answer briefly, what is the status?",
            "Say the test phrase.",
        ):
            with self.subTest(text=text):
                request = bridge.deliver(text)
                self.now += 20
                bridge.poll(request)
                self.assertEqual(bridge.poll(request), "The build is passing.")
        self.assertEqual(len(self.fallback.sent), 3)

    def test_sentence_boundary_action_after_question_is_queued(self):
        self.main.online = False
        bridge = self.bridge()
        for text in (
            "What's the status? Please email Bob the summary.",
            "Tell me the status. Send Bob the summary.",
            "What is the status, also email Bob.",
            "Reply to the customer email.",
        ):
            with self.subTest(text=text):
                request = bridge.deliver(text)
                self.now += 20
                self.assertIn("queued", bridge.poll(request).lower())
        self.assertEqual(self.fallback.sent, [])

    def test_clear_indirect_action_requests_are_saved_for_main(self):
        self.main.online = False
        bridge = self.bridge()
        for text in (
            "How about fixing the deployment?",
            "Why don't you restart the service?",
            "What I need is for you to delete the local test note.",
            "How about you send the report to Bob?",
        ):
            with self.subTest(text=text):
                request = bridge.deliver(text)
                self.now += 20
                notice = bridge.poll(request)
                self.assertIsNotNone(notice)
                self.assertIn("queued", notice.lower())
                entries = json.loads((self.home / "main-voice-queue.json").read_text())
                self.assertTrue(
                    any(entry["text"] == text and entry["state"] == "pending" for entry in entries)
                )
        self.assertEqual(self.fallback.sent, [])

    def test_informational_how_to_questions_stay_read_only_fallback_requests(self):
        self.main.online = False
        bridge = self.bridge()
        for text in (
            "How do I restart the service?",
            "How do I fix the deployment?",
            "How does the deployment work?",
            "How about the build status?",
        ):
            with self.subTest(text=text):
                request = bridge.deliver(text)
                self.now += 20
                bridge.poll(request)
                self.assertEqual(bridge.poll(request), "The build is passing.")
        self.assertFalse((self.home / "main-voice-queue.json").exists())

    def test_main_rollover_after_reply_before_playback_rejects_stale_speech(self):
        bridge = self.bridge()
        self.main.answer = "All checks pass."
        request = bridge.deliver("What is the status?")
        self.assertEqual(bridge.poll(request), "All checks pass.")
        self.main.online = False
        with self.assertRaises(Offline):
            bridge.assert_current(request["session_id"])

    def test_closed_router_worker_cannot_overwrite_new_owners_action_queue(self):
        import threading
        from concurrent.futures import ThreadPoolExecutor

        from routing import RoutedBridge

        entered, resume = threading.Event(), threading.Event()
        main = self.main
        original = main.deliver

        def delayed(text, **kwargs):
            entered.set()
            resume.wait(5)
            return original(text, **kwargs)

        main.deliver = delayed
        first = RoutedBridge(
            self.home, main=main, fallback=self.fallback, executor=ThreadPoolExecutor(max_workers=1)
        )
        request = first.deliver("Fix the deployment.")
        self.assertTrue(entered.wait(1))
        first.close()
        self.main = MainInbox()
        self.main.online = False
        second = self.bridge()
        second.deliver("Deploy the other project.")
        before = (self.home / "main-voice-queue.json").read_text()
        resume.set()
        try:
            request["submit_future"].result(timeout=2)
        except Offline:
            pass
        self.assertEqual(main.sent, [])
        self.assertEqual((self.home / "main-voice-queue.json").read_text(), before)

    def test_router_identity_stays_current_during_main_rollover(self):
        bridge = self.bridge()
        request = bridge.deliver("What is the build status?")
        self.main.online = False
        bridge.assert_current(request["session_id"])
        self.now = 20
        bridge.poll(request)
        self.assertEqual(bridge.poll(request), "The build is passing.")


if __name__ == "__main__":
    unittest.main()
