"""Pinned, local delivery to the existing live Ted. No session launching."""

import json
import re
import uuid
from pathlib import Path

from core import ReplyCursor


class Offline(RuntimeError):
    pass


class JsonlTail:
    def __init__(self, path, offset=None):
        self.path = Path(path)
        st = self.path.stat()
        self.inode = st.st_ino
        self.offset = st.st_size if offset is None else offset

    def read(self):
        st = self.path.stat()
        if st.st_ino != self.inode or st.st_size < self.offset:
            raise Offline("transcript changed")
        with self.path.open("rb") as f:
            f.seek(self.offset)
            data = f.read()
        complete, _, _ = data.rpartition(b"\n")
        if b"\n" not in data:
            return []
        self.offset += len(complete) + 1
        rows = []
        for line in complete.splitlines():
            try:
                rows.append(json.loads(line))
            except (ValueError, UnicodeDecodeError):
                continue
        return rows


class SessionBridge:
    def __init__(self, board=None):
        self.board = Path(board or Path.home() / "ted-ops/ted-board")
        self.current = self.board / "frontdoor/fresh/current.json"
        self.transcripts = Path.home() / ".claude/projects/-Users-vahallo-Claude-Code---Fictora"
        # This is the installed, reviewed runtime transport, not a new implementation.
        import sys

        sys.path.insert(0, str(self.board))
        import fresh_ted

        self.transport = fresh_ted

    def agents(self):
        return self.transport.agents()

    def current_id(self):
        try:
            sid = json.loads(self.current.read_text())["session_id"]
        except (OSError, ValueError, KeyError):
            raise Offline("current Ted unavailable") from None
        if not re.fullmatch(r"[a-f0-9-]{36}", sid):
            raise Offline("invalid session identity")
        return sid

    def assert_current(self, sid):
        if self.current_id() != sid:
            raise Offline("Ted rolled over")

    def live(self):
        sid = self.current_id()
        try:
            rows = self.agents()
        except Exception:
            raise Offline("Ted registry unavailable") from None
        matches = [
            r
            for r in rows
            if r.get("sessionId") == sid
            and r.get("pid")
            and r.get("cwd") == str(Path.home() / "Claude Code - Fictora")
            and r.get("state") not in ("failed", "exited")
        ]
        if len(matches) != 1:
            raise Offline("live Ted inbox unavailable")
        try:
            registry = self.transport.registry(matches[0])
        except Exception:
            raise Offline("live Ted registry changed") from None
        if registry.get("waitingFor") == "permission prompt":
            raise Offline("live Ted needs permission review")
        return matches[0]

    def deliver(self, text):
        agent = self.live()
        sid = agent["sessionId"]
        tail = JsonlTail(self.transcripts / (sid + ".jsonl"))
        rid = uuid.uuid4().hex
        marker = "voice:" + rid
        content = (
            "[voice] "
            + marker
            + "\n"
            + text
            + "\n\nReply naturally in brief spoken prose. Do not invoke tts.sh or send a voice memo: the local voice loop will speak your final text. The voice channel does not authorize spending, external messages, or database writes."
        )
        self.assert_current(sid)
        try:
            self.transport.send(
                agent,
                dict(
                    type="user",
                    message=dict(role="user", content=content),
                    uuid=str(uuid.uuid4()),
                    priority="now",
                    **{"from": "hey-ted-voice"},
                ),
            )
        except Exception:
            raise Offline("delivery uncertain; not retried automatically") from None
        return dict(
            session_id=sid,
            marker=marker,
            tail=tail,
            cursor=ReplyCursor(marker),
            agent=agent,
            accepted=False,
            text=text,
        )

    def poll(self, request):
        self.assert_current(request["session_id"])
        for row in request["tail"].read():
            reply = request["cursor"].feed(row)
            if reply:
                request["accepted"] = request["cursor"].seen
                return reply
        request["accepted"] = request["cursor"].seen
        if request["cursor"].cancelled:
            raise Offline("another user took the conversation")
        return None
