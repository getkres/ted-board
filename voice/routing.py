"""Main Ted inbox routing, read-only fallback, and durable action handoff."""

import fcntl
import json
import os
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from account2 import Account2Bridge
from core import speech_text
from session import DeliveryUncertain, Offline, SessionBridge


def asks_for_action(text):
    """Only clearly informational requests bypass the conservative action queue."""
    lowered = text.strip().lower()
    # These explicit requests can begin like questions, but still ask Ted to act.
    if re.match(
        r"^(?:how about (?:(?:you|we)\b|[a-z]+ing\b)|"
        r"why (?:don't|do not) you\b|"
        r"what (?:i|we) (?:need|want) is for you to\b)",
        lowered,
    ):
        return True
    verbs = (
        r"fix|change|update|delete|remove|create|build|deploy|publish|send|email|"
        r"message|buy|pay|purchase|cancel|schedule|install|restart|start|stop|commit|"
        r"push|merge|approve|write|edit|move|rename|add|book|order|run|launch"
    )
    if re.search(r"\b(?:can|could|would|will) you\b", lowered) or re.search(
        r"(?:^|[.!?;,]\s*|\b(?:and|then|also)\s+)(?:please\s+)?(?:" + verbs + r")\b", lowered
    ):
        return True
    return not bool(
        re.match(
            r"^(what\b|what's\b|where\b|when\b|who\b|why\b|how\b|"
            r"is\b|are\b|do we\b|does\b|did\b|tell me\b|show me\b|"
            r"give me (?:a |the )?(?:status|summary|update)\b|summarize\b|"
            r"explain\b|describe\b|reply (?:exactly|briefly)\b|answer (?:briefly|concisely)\b|say\b)",
            lowered,
        )
    )


class RoutedBridge:
    def __init__(self, home, emit=None, *, main=None, fallback=None, clock=None, executor=None):
        self.home = Path(home)
        self.home.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.emit = emit or (lambda *args, **kwargs: None)
        self.clock = clock or time.monotonic
        self.main = main or SessionBridge()
        self.fallback = fallback or Account2Bridge(home, self.emit)
        self.executor = executor or ThreadPoolExecutor(max_workers=1)
        self.closed = False
        self.identity = "routed:" + uuid.uuid4().hex
        self.path = self.home / "main-voice-queue.json"
        self.lock = threading.RLock()
        self.queue_lock = (self.home / "main-voice-queue.lock").open("a")
        os.chmod(self.queue_lock.name, 0o600)
        try:
            fcntl.flock(self.queue_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.queue_lock.close()
            self.fallback.close()
            self.executor.shutdown(wait=False, cancel_futures=True)
            raise Offline("another voice router owns the action queue") from None
        self.requests = {}
        self.next_retry = 0
        try:
            self.queue = json.loads(self.path.read_text()) if self.path.exists() else []
            if not isinstance(self.queue, list):
                raise ValueError()
            markers = set()
            for entry in self.queue:
                if (
                    not isinstance(entry, dict)
                    or not isinstance(entry.get("text"), str)
                    or not isinstance(entry.get("marker"), str)
                    or not re.fullmatch(r"voice:[a-f0-9]{32}", entry["marker"])
                    or entry["marker"] in markers
                    or entry.get("state")
                    not in ("pending", "dispatching", "uncertain", "delivered")
                ):
                    raise ValueError()
                markers.add(entry["marker"])
                # A crash after recording intent might have occurred after socket send.
                if entry["state"] == "dispatching":
                    entry["state"] = "uncertain"
            if self.queue:
                self._save()
        except (OSError, ValueError, TypeError):
            self.close()
            raise Offline("invalid main voice action queue; preserved for review") from None

    def _save(self):
        with self.lock:
            temporary = self.path.with_name("main-voice-" + uuid.uuid4().hex + ".tmp")
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                with os.fdopen(fd, "w") as stream:
                    json.dump(self.queue, stream)
                    stream.flush()
                    os.fsync(stream.fileno())
                temporary.replace(self.path)
                directory = os.open(self.home, os.O_RDONLY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            finally:
                temporary.unlink(missing_ok=True)

    def assert_current(self, sid):
        if self.closed:
            raise Offline("voice router changed")
        if sid == self.identity:
            return
        if isinstance(sid, str) and sid.startswith("main-reply:"):
            request = self.requests.get(sid[len("main-reply:") :])
            if request and request["main_request"]:
                self.main.assert_current(request["main_request"]["session_id"])
                return
        raise Offline("voice router changed")

    def _request(self, text, marker=None, entry=None):
        request = dict(
            session_id=self.identity,
            marker=marker or "voice:" + uuid.uuid4().hex,
            text=text,
            accepted=False,
            started=self.clock(),
            route="main",
            main_request=None,
            submit_future=None,
            poll_future=None,
            main_delivered=False,
            socket_sent=False,
            ack_future=None,
            ack_signature=None,
            uncertain=False,
            next_attempt=0,
            entry=entry,
            reason="main Ted busy or unavailable",
            done=False,
        )
        self.requests[request["marker"]] = request
        return request

    def deliver(self, text):
        self.assert_current(self.identity)
        request = self._request(text)
        if asks_for_action(text):
            entry = dict(marker=request["marker"], text=text, state="pending")
            with self.lock:
                self.queue.append(entry)
                self._save()
            request["entry"] = entry
        self._submit(request)
        return request

    def _submit(self, request):
        if request["submit_future"] or request["socket_sent"] or request["uncertain"]:
            return
        request["next_attempt"] = self.clock() + 3

        def before_send(main_request):
            with self.lock:
                if self.closed:
                    raise Offline("voice router closed before dispatch")
                entry = request["entry"]
                if entry is not None:
                    entry.update(state="dispatching", session_id=main_request["session_id"])
                    self._save()

        request["submit_future"] = self.executor.submit(
            self.main.deliver, request["text"], marker=request["marker"], before_send=before_send
        )

    def _collect(self, request):
        if self.closed:
            return
        future = request["submit_future"]
        if not future or not future.done():
            return
        request["submit_future"] = None
        try:
            request["main_request"] = future.result()
            request["socket_sent"] = True
            if request["main_request"].get("accepted"):
                self._acknowledge(request)
            self.emit(
                "voice_main_submitted",
                marker=request["marker"],
                session_id=request["main_request"]["session_id"],
            )
        except (Offline, OSError, RuntimeError) as exc:
            request["reason"] = str(exc)
            entry = request["entry"]
            if isinstance(exc, DeliveryUncertain) or (entry and entry["state"] == "dispatching"):
                request["uncertain"] = True
                if entry is not None:
                    with self.lock:
                        entry["state"] = "uncertain"
                        self._save()
                self.emit("voice_main_delivery_uncertain", marker=request["marker"])

    def _acknowledge(self, request):
        if request["main_delivered"] or self.closed:
            return
        request["main_delivered"] = True
        request["accepted"] = True
        request["uncertain"] = False
        entry = request["entry"]
        if entry is not None:
            with self.lock:
                entry["state"] = "delivered"
                self._save()
            self.emit(
                "voice_action_delivered", marker=request["marker"], session_id=entry["session_id"]
            )

    def _check_ack(self, entry, previous_signature):
        # File metadata and transcript scanning stay off the audio pump. Scan a
        # transcript only when it has changed since the previous unsuccessful check.
        transcripts = getattr(self.main, "transcripts", None)
        if transcripts is None:
            return previous_signature, False
        try:
            stat = (Path(transcripts) / (entry["session_id"] + ".jsonl")).stat()
        except OSError:
            return previous_signature, False
        signature = (stat.st_ino, stat.st_size, stat.st_mtime_ns)
        if signature == previous_signature:
            return signature, False
        return signature, self.main.acknowledged(entry["session_id"], entry["marker"])

    def _collect_ack(self, request):
        future = request["ack_future"]
        if self.closed or not future or not future.done():
            return
        request["ack_future"] = None
        try:
            signature, acknowledged = future.result()
            request["ack_signature"] = signature
            if acknowledged:
                self._acknowledge(request)
        except (Offline, OSError, RuntimeError):
            pass

    def _finish(self, request, text):
        request["done"] = True
        if request["route"] == "main":
            request["session_id"] = "main-reply:" + request["marker"]
        return speech_text(text)

    def _fallback(self, request):
        entry = request["entry"]
        if (
            entry is not None
            and not request["main_delivered"]
            and (request["socket_sent"] or entry["state"] == "dispatching")
        ):
            request["uncertain"] = True
            with self.lock:
                entry["state"] = "uncertain"
                self._save()
            self.emit("voice_main_delivery_uncertain", marker=request["marker"])
        request["route"] = "fallback"
        self.emit(
            "voice_fallback_started",
            reason=request["reason"],
            action_queued=entry is not None and entry["state"] == "pending",
            main_delivered=request["main_delivered"],
        )
        if entry is not None:
            request["accepted"] = True
            if request["uncertain"]:
                return self._finish(
                    request,
                    "I couldn't confirm whether main Ted received that. "
                    "It's saved for review, and I won't send it twice.",
                )
            if request["main_delivered"]:
                return self._finish(
                    request,
                    "Main Ted already has that request. He's still working, "
                    "so check the screen for the result.",
                )
            self.emit("voice_action_queued", marker=request["marker"])
            return self._finish(
                request,
                "Main Ted isn't available. I've queued that request and "
                "will hand it over when he returns.",
            )
        request["fallback_request"] = self.fallback.deliver(request["text"])
        return None

    def poll(self, request):
        self.assert_current(request["session_id"])
        self._collect(request)
        if request["done"]:
            return None
        if request["route"] == "fallback":
            reply = self.fallback.poll(request["fallback_request"])
            request["accepted"] = request["fallback_request"]["accepted"]
            return self._finish(request, reply) if reply else None
        if self.clock() - request["started"] < 20 and self.clock() >= request["next_attempt"]:
            self._submit(request)
            self._collect(request)
        if request["main_request"]:
            if request["poll_future"] is None:
                request["poll_future"] = self.executor.submit(
                    self.main.poll, request["main_request"]
                )
            future = request["poll_future"]
            if future.done():
                request["poll_future"] = None
                try:
                    reply = future.result()
                    request["accepted"] = request["main_request"]["accepted"]
                    if request["accepted"]:
                        self._acknowledge(request)
                    if reply:
                        self.emit(
                            "voice_main_reply",
                            session_id=request["main_request"]["session_id"],
                            characters=len(reply),
                        )
                        return self._finish(request, reply)
                except (Offline, OSError, RuntimeError) as exc:
                    request["reason"] = str(exc)
        if self.clock() - request["started"] >= 20:
            return self._fallback(request)
        if self.clock() >= request["next_attempt"]:
            self._submit(request)
        return None

    def tick(self):
        if self.closed:
            return
        for request in list(self.requests.values()):
            self._collect(request)
            self._collect_ack(request)
        if self.clock() < self.next_retry:
            return
        self.next_retry = self.clock() + 5
        for entry in self.queue:
            if entry["state"] in ("dispatching", "uncertain") and entry.get("session_id"):
                request = self.requests.get(entry["marker"])
                if request is None:
                    request = self._request(entry["text"], entry["marker"], entry)
                    request.update(done=True, uncertain=True, socket_sent=True)
                if request["ack_future"] is None and not request["main_delivered"]:
                    request["ack_future"] = self.executor.submit(
                        self._check_ack, dict(entry), request["ack_signature"]
                    )
                    self._collect_ack(request)
        for entry in self.queue:
            if entry["state"] != "pending":
                continue
            request = self.requests.get(entry["marker"])
            if request is None:
                request = self._request(entry["text"], entry["marker"], entry)
                request["done"] = True
            self._submit(request)
            self._collect(request)
            # Preserve queue order and avoid overwhelming the desktop inbox.
            break

    def close(self):
        if self.closed:
            return
        with self.lock:
            self.closed = True
        self.fallback.close()
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.queue_lock.close()
