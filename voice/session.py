"""Pinned, local delivery to the existing live Ted. No session launching."""

import json
import os
import re
import subprocess
import uuid
from pathlib import Path

from core import ReplyCursor


class Offline(RuntimeError):
    pass


class DeliveryUncertain(Offline):
    """The socket may have accepted the request. Never resend automatically."""


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
                row = json.loads(line)
                if isinstance(row, dict):
                    rows.append(row)
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
        # The daemon uses account 2, but the desktop inbox belongs to the main registry.
        env = dict(os.environ)
        for key in list(env):
            if key.startswith(("ANTHROPIC_", "CLAUDE_CODE_USE_")) or key in (
                "CLAUDECODE",
                "CLAUDE_SECURESTORAGE_CONFIG_DIR",
                "CLAUDE_CODE_OAUTH_TOKEN",
                "CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR",
                "CLAUDE_CODE_API_KEY_FILE_DESCRIPTOR",
                "CLAUDE_CODE_CUSTOM_HEADERS_HELPER",
            ):
                env.pop(key, None)
        env["CLAUDE_CONFIG_DIR"] = str(Path.home() / ".claude")
        result = subprocess.run(
            [self.transport.CLAUDE, "agents", "--json", "--all"],
            cwd=self.transport.PROJECT,
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode:
            raise Offline("main Ted registry unavailable")
        rows = json.loads(result.stdout)
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise Offline("invalid main Ted registry")
        return rows

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
        try:
            proc = subprocess.run(
                ["/bin/ps", "-p", str(int(matches[0]["pid"])), "-o", "lstart="],
                env=dict(os.environ, TZ="UTC"),
                capture_output=True,
                text=True,
                timeout=5,
            )
            started = " ".join(proc.stdout.split())
            if (
                proc.returncode
                or not started
                or started != " ".join(str(registry.get("procStart", "")).split())
            ):
                raise Offline("live Ted process identity changed")
            socket_path = registry.get("messagingSocketPath")
            if not socket_path or not Path(socket_path).is_socket():
                raise Offline("live Ted inbox unavailable")
        except (OSError, ValueError, TypeError, subprocess.SubprocessError):
            raise Offline("live Ted process identity unavailable") from None
        return matches[0]

    def deliver(self, text, marker=None, before_send=None):
        agent = self.live()
        sid = agent["sessionId"]
        tail = JsonlTail(self.transcripts / (sid + ".jsonl"))
        marker = marker or "voice:" + uuid.uuid4().hex
        content = (
            "[voice] "
            + marker
            + "\n"
            + text
            + "\n\nReply naturally in brief spoken prose. Do not invoke tts.sh or send a voice memo: the local voice loop will speak your final text. Respect existing permissions and spending approvals. The voice channel grants no new spending approval."
        )
        self.assert_current(sid)
        request = dict(
            session_id=sid,
            marker=marker,
            tail=tail,
            cursor=ReplyCursor(marker),
            agent=agent,
            accepted=False,
            text=text,
        )
        if before_send:
            before_send(request)
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
            raise DeliveryUncertain("delivery uncertain; not retried automatically") from None
        return request

    def acknowledged(self, sid, marker):
        """Reconcile ambiguous sends from user rows only, without sending again."""
        cursor = ReplyCursor(marker)
        try:
            with (self.transcripts / (sid + ".jsonl")).open() as stream:
                for line in stream:
                    try:
                        row = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(row, dict) and row.get("type") == "user":
                        cursor.feed(row)
                        if cursor.seen:
                            return True
        except OSError:
            pass
        return False

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
